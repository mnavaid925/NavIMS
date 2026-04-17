"""Shared view decorators for tenant-scoped modules.

Lifted from `vendors/decorators.py` and `warehousing/decorators.py` — the two
copies were byte-identical. Modules should import from here:

    from core.decorators import tenant_admin_required, emit_audit
"""
from functools import wraps

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .models import AuditLog


def tenant_admin_required(view_func):
    """Require the user to be a tenant admin of the active tenant.

    `@login_required` alone lets any authenticated tenant user delete/update
    tenant data. This decorator gates destructive operations behind
    `is_tenant_admin`. Superusers are allowed through.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect('accounts:login')
        if user.is_superuser or getattr(user, 'is_tenant_admin', False):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to perform this action.')
        return HttpResponseForbidden('Forbidden: tenant admin role required.')
    return _wrapped


def emit_audit(request, action, instance, changes=''):
    """Emit a `core.AuditLog` row for a tenant-scoped module action.

    Silently no-ops if `request.tenant` is unset (superuser browsing without
    a tenant context).
    """
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return None
    return AuditLog.objects.create(
        tenant=tenant,
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model_name=type(instance).__name__,
        object_id=str(instance.pk) if instance.pk is not None else '',
        changes=changes,
        ip_address=_client_ip(request),
    )


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None
