from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden

from core.models import Tenant, Subscription, Role
from .models import TenantCustomization
from .forms import (
    TenantForm,
    SubscriptionForm,
    TenantCustomizationForm,
    RoleForm,
)


# ──────────────────────────────────────────────
# Tenant views (superuser only)
# ──────────────────────────────────────────────

@login_required
def tenant_list_view(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    queryset = Tenant.objects.all()

    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            _name_slug_query(search)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    tenants = paginator.get_page(page_number)

    context = {
        'tenants': tenants,
        'search': search,
    }
    return render(request, 'administration/tenant_list.html', context)


def _name_slug_query(search):
    """Helper to build Q filter for name/slug search."""
    from django.db.models import Q
    return Q(name__icontains=search) | Q(slug__icontains=search)


@login_required
def tenant_create_view(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    if request.method == 'POST':
        form = TenantForm(request.POST)
        if form.is_valid():
            tenant = form.save()
            messages.success(request, f'Tenant "{tenant.name}" created successfully.')
            return redirect('administration:tenant_detail', pk=tenant.pk)
    else:
        form = TenantForm()

    context = {
        'form': form,
        'title': 'Create Tenant',
    }
    return render(request, 'administration/tenant_form.html', context)


@login_required
def tenant_detail_view(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    tenant = get_object_or_404(Tenant, pk=pk)
    subscription = getattr(tenant, 'subscription', None)

    context = {
        'tenant': tenant,
        'subscription': subscription,
    }
    return render(request, 'administration/tenant_detail.html', context)


@login_required
def tenant_edit_view(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    tenant = get_object_or_404(Tenant, pk=pk)

    if request.method == 'POST':
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Tenant "{tenant.name}" updated successfully.')
            return redirect('administration:tenant_detail', pk=tenant.pk)
    else:
        form = TenantForm(instance=tenant)

    context = {
        'form': form,
        'title': 'Edit Tenant',
        'tenant': tenant,
    }
    return render(request, 'administration/tenant_form.html', context)


@login_required
def tenant_delete_view(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    if request.method != 'POST':
        return HttpResponseForbidden("Only POST requests are allowed.")

    tenant = get_object_or_404(Tenant, pk=pk)
    tenant_name = tenant.name
    tenant.delete()
    messages.success(request, f'Tenant "{tenant_name}" deleted successfully.')
    return redirect('administration:tenant_list')


# ──────────────────────────────────────────────
# Subscription views
# ──────────────────────────────────────────────

@login_required
def subscription_list_view(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    subscriptions = Subscription.objects.select_related('tenant').all()

    context = {
        'subscriptions': subscriptions,
    }
    return render(request, 'administration/subscription_list.html', context)


@login_required
def subscription_edit_view(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You do not have permission to access this page.")

    subscription = get_object_or_404(Subscription, pk=pk)

    if request.method == 'POST':
        form = SubscriptionForm(request.POST, instance=subscription)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Subscription for "{subscription.tenant.name}" updated successfully.',
            )
            return redirect('administration:subscription_list')
    else:
        form = SubscriptionForm(instance=subscription)

    context = {
        'form': form,
        'subscription': subscription,
        'title': 'Edit Subscription',
    }
    return render(request, 'administration/subscription_form.html', context)


# ──────────────────────────────────────────────
# Role views (tenant-scoped)
# ──────────────────────────────────────────────

@login_required
def role_list_view(request):
    tenant = request.tenant
    roles = Role.objects.filter(tenant=tenant)

    context = {
        'roles': roles,
    }
    return render(request, 'administration/role_list.html', context)


@login_required
def role_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = RoleForm(request.POST, tenant=tenant)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'Role "{role.name}" created successfully.')
            return redirect('administration:role_list')
    else:
        form = RoleForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Role',
    }
    return render(request, 'administration/role_form.html', context)


@login_required
def role_edit_view(request, pk):
    tenant = request.tenant
    role = get_object_or_404(Role, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = RoleForm(request.POST, instance=role, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Role "{role.name}" updated successfully.')
            return redirect('administration:role_list')
    else:
        form = RoleForm(instance=role, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Role',
        'role': role,
    }
    return render(request, 'administration/role_form.html', context)


@login_required
def role_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return HttpResponseForbidden("Only POST requests are allowed.")

    role = get_object_or_404(Role, pk=pk, tenant=tenant)
    role_name = role.name
    role.delete()
    messages.success(request, f'Role "{role_name}" deleted successfully.')
    return redirect('administration:role_list')


# ──────────────────────────────────────────────
# Settings view (tenant-scoped)
# ──────────────────────────────────────────────

@login_required
def settings_view(request):
    tenant = request.tenant
    customization, created = TenantCustomization.objects.get_or_create(tenant=tenant)

    if request.method == 'POST':
        form = TenantCustomizationForm(request.POST, request.FILES, instance=customization)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings updated successfully.')
            return redirect('administration:settings')
    else:
        form = TenantCustomizationForm(instance=customization)

    context = {
        'form': form,
        'customization': customization,
    }
    return render(request, 'administration/settings.html', context)
