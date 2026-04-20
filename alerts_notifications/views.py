import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import emit_audit, tenant_admin_required

from warehousing.models import Warehouse

from .forms import AlertForm, AlertResolveForm, NotificationRuleForm
from .models import ALERT_TYPE_CHOICES, SEVERITY_CHOICES, Alert, NotificationDelivery, NotificationRule


# ═══════════════════════════════════════════════════════════════════════════
# Alert Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def alert_dashboard_view(request):
    tenant = request.tenant
    base = Alert.objects.filter(tenant=tenant, deleted_at__isnull=True)
    today = timezone.now().date()

    stats = {
        'total_open': base.filter(status__in=['new', 'acknowledged']).count(),
        'new_today': base.filter(status='new', triggered_at__date=today).count(),
        'critical_open': base.filter(severity='critical', status__in=['new', 'acknowledged']).count(),
        'resolved_total': base.filter(status='resolved').count(),
    }

    by_type_rows = (
        base.filter(status__in=['new', 'acknowledged'])
        .values('alert_type')
        .annotate(c=Count('id'))
        .order_by('-c')
    )
    type_labels = dict(ALERT_TYPE_CHOICES)
    by_type = [
        {'alert_type': r['alert_type'], 'label': type_labels.get(r['alert_type'], r['alert_type']), 'c': r['c']}
        for r in by_type_rows
    ]

    recent = (
        base.select_related('product', 'warehouse', 'purchase_order', 'shipment', 'lot_batch')
        .order_by('-triggered_at')[:10]
    )

    return render(request, 'alerts_notifications/alert_dashboard.html', {
        'stats': stats,
        'by_type': by_type,
        'recent_alerts': recent,
        'alert_type_labels': dict(ALERT_TYPE_CHOICES),
    })


# ═══════════════════════════════════════════════════════════════════════════
# Alert — list + detail + state transitions
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def alert_list_view(request):
    tenant = request.tenant
    qs = Alert.objects.filter(tenant=tenant, deleted_at__isnull=True).select_related(
        'product', 'warehouse', 'stock_level', 'lot_batch', 'purchase_order', 'shipment', 'acknowledged_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(alert_number__icontains=q)
            | Q(title__icontains=q)
            | Q(message__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    severity = request.GET.get('severity', '')
    if severity:
        qs = qs.filter(severity=severity)

    alert_type = request.GET.get('alert_type', '')
    if alert_type:
        qs = qs.filter(alert_type=alert_type)

    product_id = request.GET.get('product', '')
    if product_id:
        qs = qs.filter(product_id=product_id)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    # D-09: `products` context was unused by the template; dropped to save a query.
    return render(request, 'alerts_notifications/alert_list.html', {
        'alerts': page,
        'q': q,
        'current_status': status,
        'current_severity': severity,
        'current_alert_type': alert_type,
        'current_product': product_id,
        'current_warehouse': warehouse_id,
        'status_choices': Alert.STATUS_CHOICES,
        'severity_choices': SEVERITY_CHOICES,
        'alert_type_choices': ALERT_TYPE_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True).order_by('code'),
    })


@login_required
def alert_detail_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(
        Alert.objects.select_related(
            'product', 'warehouse', 'stock_level', 'lot_batch',
            'purchase_order', 'shipment', 'acknowledged_by',
        ),
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    deliveries = alert.deliveries.select_related('rule', 'recipient').order_by('-id')
    return render(request, 'alerts_notifications/alert_detail.html', {
        'alert': alert,
        'deliveries': deliveries,
        'resolve_form': AlertResolveForm(),
    })


@login_required
@tenant_admin_required
def alert_create_view(request):
    tenant = request.tenant
    # D-01: `obj.save()` dereferences `self.tenant` to auto-generate ALN-NNNNN;
    # with tenant=None the FK descriptor raises RelatedObjectDoesNotExist → 500.
    if tenant is None:
        messages.error(request, 'No tenant context — log in as a tenant admin to create alerts.')
        return redirect('alerts_notifications:alert_list')
    if request.method == 'POST':
        form = AlertForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            # D-06: uuid4 avoids float-timestamp collisions under concurrent submit.
            obj.dedup_key = f'manual:{uuid.uuid4().hex}'
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Alert "{obj.alert_number}" created.')
            return redirect('alerts_notifications:alert_detail', pk=obj.pk)
    else:
        form = AlertForm(tenant=tenant)
    return render(request, 'alerts_notifications/alert_form.html', {
        'form': form, 'title': 'New Alert',
    })


@login_required
@tenant_admin_required
def alert_edit_view(request, pk):
    """Edit a manually-created alert. Scanner-generated alerts are immutable
    because their fields are deterministic outputs of the scanner input —
    editing would desynchronise them from the dedup_key. D-03 policy fix.
    """
    tenant = request.tenant
    alert = get_object_or_404(Alert, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not alert.dedup_key.startswith('manual:'):
        messages.error(request, 'Scanner-generated alerts cannot be edited. Use Acknowledge / Resolve / Dismiss instead.')
        return redirect('alerts_notifications:alert_detail', pk=alert.pk)
    if request.method == 'POST':
        form = AlertForm(request.POST, instance=alert, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', alert)
            messages.success(request, f'Alert "{alert.alert_number}" updated.')
            return redirect('alerts_notifications:alert_detail', pk=alert.pk)
    else:
        form = AlertForm(instance=alert, tenant=tenant)
    return render(request, 'alerts_notifications/alert_form.html', {
        'form': form, 'alert': alert, 'title': f'Edit {alert.alert_number}',
    })


@login_required
@tenant_admin_required
@require_POST
def alert_acknowledge_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(Alert, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not alert.can_transition_to('acknowledged'):
        messages.error(request, f'Cannot acknowledge an alert in "{alert.get_status_display()}" state.')
        return redirect('alerts_notifications:alert_detail', pk=alert.pk)
    old = alert.status
    alert.status = 'acknowledged'
    alert.acknowledged_by = request.user
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at', 'updated_at'])
    emit_audit(request, 'acknowledge', alert, changes=f'{old}->acknowledged')
    messages.success(request, f'Alert "{alert.alert_number}" acknowledged.')
    return redirect('alerts_notifications:alert_detail', pk=alert.pk)


@login_required
@tenant_admin_required
@require_POST
def alert_resolve_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(Alert, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not alert.can_transition_to('resolved'):
        messages.error(request, f'Cannot resolve an alert in "{alert.get_status_display()}" state. Acknowledge it first.')
        return redirect('alerts_notifications:alert_detail', pk=alert.pk)
    old = alert.status
    # D-04: validate via AlertResolveForm (max_length=2000 per submission) and
    # cap aggregate alert.notes to 16 KB to prevent long-term bloat.
    resolve_form = AlertResolveForm(request.POST)
    if not resolve_form.is_valid():
        messages.error(request, 'Resolution notes rejected: ' + '; '.join(resolve_form.errors.get('notes', [])))
        return redirect('alerts_notifications:alert_detail', pk=alert.pk)
    note_text = resolve_form.cleaned_data.get('notes', '').strip()
    if note_text:
        stamp = timezone.now().strftime('%Y-%m-%d %H:%M')
        prefix = f'\n\n[{stamp} — {request.user.username}]\n' if alert.notes else ''
        combined = f'{alert.notes}{prefix}{note_text}'
        alert.notes = combined[-16384:] if len(combined) > 16384 else combined
    alert.status = 'resolved'
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['status', 'resolved_at', 'notes', 'updated_at'])
    emit_audit(request, 'resolve', alert, changes=f'{old}->resolved')
    messages.success(request, f'Alert "{alert.alert_number}" resolved.')
    return redirect('alerts_notifications:alert_detail', pk=alert.pk)


@login_required
@tenant_admin_required
@require_POST
def alert_dismiss_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(Alert, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not alert.can_transition_to('dismissed'):
        messages.error(request, f'Cannot dismiss an alert in "{alert.get_status_display()}" state.')
        return redirect('alerts_notifications:alert_detail', pk=alert.pk)
    old = alert.status
    alert.status = 'dismissed'
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['status', 'resolved_at', 'updated_at'])
    emit_audit(request, 'dismiss', alert, changes=f'{old}->dismissed')
    messages.success(request, f'Alert "{alert.alert_number}" dismissed.')
    return redirect('alerts_notifications:alert_detail', pk=alert.pk)


@login_required
@tenant_admin_required
@require_POST
def alert_delete_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(Alert, pk=pk, tenant=tenant, deleted_at__isnull=True)
    alert.deleted_at = timezone.now()
    alert.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'delete', alert)
    messages.success(request, f'Alert "{alert.alert_number}" deleted.')
    return redirect('alerts_notifications:alert_list')


@login_required
def alert_inbox_json_view(request):
    """Lightweight JSON endpoint for the topbar bell dropdown.

    Returns the current tenant's unread alerts (status=new). If no tenant
    context (e.g. superuser logged in), returns an empty payload.
    """
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return JsonResponse({'unread_count': 0, 'items': []})

    qs = (
        Alert.objects
        .filter(tenant=tenant, status='new', deleted_at__isnull=True)
        .order_by('-triggered_at')
    )
    unread_count = qs.count()
    items = []
    for a in qs[:5]:
        items.append({
            'id': a.pk,
            'alert_number': a.alert_number,
            'title': a.title,
            'severity': a.severity,
            'alert_type': a.alert_type,
            'alert_type_display': a.get_alert_type_display(),
            'triggered_at': a.triggered_at.isoformat(),
            'url': reverse('alerts_notifications:alert_detail', args=[a.pk]),
        })
    return JsonResponse({'unread_count': unread_count, 'items': items})


# ═══════════════════════════════════════════════════════════════════════════
# NotificationRule — CRUD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def rule_list_view(request):
    tenant = request.tenant
    qs = NotificationRule.objects.filter(tenant=tenant, deleted_at__isnull=True).prefetch_related('recipient_users')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))

    alert_type = request.GET.get('alert_type', '')
    if alert_type:
        qs = qs.filter(alert_type=alert_type)

    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'alerts_notifications/rule_list.html', {
        'rules': page,
        'q': q,
        'current_alert_type': alert_type,
        'current_active': active,
        'alert_type_choices': ALERT_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def rule_create_view(request):
    tenant = request.tenant
    # D-02: `obj.save()` dereferences `self.tenant` to auto-generate NR-NNNNN;
    # with tenant=None the FK descriptor raises RelatedObjectDoesNotExist → 500.
    if tenant is None:
        messages.error(request, 'No tenant context — log in as a tenant admin to create notification rules.')
        return redirect('alerts_notifications:rule_list')
    if request.method == 'POST':
        form = NotificationRuleForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.created_by = request.user
            obj.save()
            form.save_m2m()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Rule "{obj.code}" created.')
            return redirect('alerts_notifications:rule_detail', pk=obj.pk)
    else:
        form = NotificationRuleForm(tenant=tenant)
    return render(request, 'alerts_notifications/rule_form.html', {
        'form': form, 'title': 'New Notification Rule',
    })


@login_required
def rule_detail_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(
        NotificationRule.objects.prefetch_related('recipient_users'),
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    # Recent alerts that would have matched this rule.
    matching_alerts = (
        Alert.objects.filter(
            tenant=tenant, alert_type=rule.alert_type, deleted_at__isnull=True,
        )
        .order_by('-triggered_at')[:10]
    )
    recent_deliveries = rule.deliveries.select_related('alert', 'recipient').order_by('-id')[:10]
    return render(request, 'alerts_notifications/rule_detail.html', {
        'rule': rule,
        'matching_alerts': matching_alerts,
        'recent_deliveries': recent_deliveries,
    })


@login_required
@tenant_admin_required
def rule_edit_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(NotificationRule, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if request.method == 'POST':
        form = NotificationRuleForm(request.POST, instance=rule, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', rule)
            messages.success(request, f'Rule "{rule.code}" updated.')
            return redirect('alerts_notifications:rule_detail', pk=rule.pk)
    else:
        form = NotificationRuleForm(instance=rule, tenant=tenant)
    return render(request, 'alerts_notifications/rule_form.html', {
        'form': form, 'rule': rule, 'title': f'Edit {rule.code}',
    })


@login_required
@tenant_admin_required
@require_POST
def rule_delete_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(NotificationRule, pk=pk, tenant=tenant, deleted_at__isnull=True)
    rule.deleted_at = timezone.now()
    rule.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'delete', rule)
    messages.success(request, f'Rule "{rule.code}" deleted.')
    return redirect('alerts_notifications:rule_list')


@login_required
@tenant_admin_required
@require_POST
def rule_toggle_active_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(NotificationRule, pk=pk, tenant=tenant, deleted_at__isnull=True)
    rule.is_active = not rule.is_active
    rule.save(update_fields=['is_active', 'updated_at'])
    emit_audit(request, 'toggle_active', rule, changes=f'is_active={rule.is_active}')
    state = 'activated' if rule.is_active else 'deactivated'
    messages.success(request, f'Rule "{rule.code}" {state}.')
    return redirect('alerts_notifications:rule_detail', pk=rule.pk)


# ═══════════════════════════════════════════════════════════════════════════
# NotificationDelivery — read-only audit log
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def delivery_list_view(request):
    tenant = request.tenant
    qs = NotificationDelivery.objects.filter(tenant=tenant).select_related(
        'alert', 'rule', 'recipient',
    )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    channel = request.GET.get('channel', '')
    if channel:
        qs = qs.filter(channel=channel)

    alert_id = request.GET.get('alert', '')
    if alert_id:
        qs = qs.filter(alert_id=alert_id)

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'alerts_notifications/delivery_list.html', {
        'deliveries': page,
        'current_status': status,
        'current_channel': channel,
        'current_alert': alert_id,
        'status_choices': NotificationDelivery.STATUS_CHOICES,
        'channel_choices': NotificationDelivery.CHANNEL_CHOICES,
    })


@login_required
def delivery_detail_view(request, pk):
    tenant = request.tenant
    delivery = get_object_or_404(
        NotificationDelivery.objects.select_related('alert', 'rule', 'recipient'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'alerts_notifications/delivery_detail.html', {
        'delivery': delivery,
    })
