from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.utils import timezone

from catalog.models import Product
from warehousing.models import Warehouse
from .models import LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog
from .forms import (
    LotBatchForm, SerialNumberForm,
    ExpiryAlertAcknowledgeForm, TraceabilityLogForm,
)


# ──────────────────────────────────────────────
# Sub-module 1: Lot/Batch Generation
# ──────────────────────────────────────────────

@login_required
def lot_list_view(request):
    tenant = request.tenant
    queryset = LotBatch.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(lot_number__icontains=q)
            | Q(product__name__icontains=q)
            | Q(supplier_batch_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    lots = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'lots': lots,
        'q': q,
        'status_choices': LotBatch.STATUS_CHOICES,
        'current_status': status,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'lot_tracking/lot_list.html', context)


@login_required
def lot_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = LotBatchForm(request.POST, tenant=tenant)
        if form.is_valid():
            lot = form.save(commit=False)
            lot.tenant = tenant
            lot.created_by = request.user
            lot.available_quantity = lot.quantity
            lot.save()

            TraceabilityLog.objects.create(
                tenant=tenant,
                lot=lot,
                event_type='received',
                to_warehouse=lot.warehouse,
                quantity=lot.quantity,
                reference_type='Lot Creation',
                reference_number=lot.lot_number,
                performed_by=request.user,
                notes=f'Lot {lot.lot_number} created with {lot.quantity} units.',
            )

            messages.success(request, f'Lot {lot.lot_number} created successfully.')
            return redirect('lot_tracking:lot_detail', pk=lot.pk)
    else:
        form = LotBatchForm(tenant=tenant)

    context = {'form': form, 'title': 'Create Lot / Batch'}
    return render(request, 'lot_tracking/lot_form.html', context)


@login_required
def lot_detail_view(request, pk):
    tenant = request.tenant
    lot = get_object_or_404(LotBatch, pk=pk, tenant=tenant)
    serials = lot.serial_numbers.all()[:20]
    trace_logs = lot.traceability_logs.select_related('performed_by', 'from_warehouse', 'to_warehouse')[:10]
    alerts = lot.expiry_alerts.all()[:5]

    context = {
        'lot': lot,
        'serials': serials,
        'trace_logs': trace_logs,
        'alerts': alerts,
    }
    return render(request, 'lot_tracking/lot_detail.html', context)


@login_required
def lot_edit_view(request, pk):
    tenant = request.tenant
    lot = get_object_or_404(LotBatch, pk=pk, tenant=tenant)

    if lot.status not in ('active', 'quarantine'):
        messages.warning(request, 'Only active or quarantined lots can be edited.')
        return redirect('lot_tracking:lot_detail', pk=lot.pk)

    if request.method == 'POST':
        form = LotBatchForm(request.POST, instance=lot, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Lot {lot.lot_number} updated successfully.')
            return redirect('lot_tracking:lot_detail', pk=lot.pk)
    else:
        form = LotBatchForm(instance=lot, tenant=tenant)

    context = {'form': form, 'lot': lot, 'title': 'Edit Lot / Batch'}
    return render(request, 'lot_tracking/lot_form.html', context)


@login_required
def lot_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('lot_tracking:lot_list')

    tenant = request.tenant
    lot = get_object_or_404(LotBatch, pk=pk, tenant=tenant)

    if lot.status not in ('quarantine',):
        messages.warning(request, 'Only quarantined lots can be deleted.')
        return redirect('lot_tracking:lot_detail', pk=lot.pk)

    lot.delete()
    messages.success(request, 'Lot deleted successfully.')
    return redirect('lot_tracking:lot_list')


@login_required
def lot_transition_view(request, pk, new_status):
    if request.method != 'POST':
        return redirect('lot_tracking:lot_list')

    tenant = request.tenant
    lot = get_object_or_404(LotBatch, pk=pk, tenant=tenant)

    if not lot.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from {lot.get_status_display()} to {new_status}.')
        return redirect('lot_tracking:lot_detail', pk=lot.pk)

    old_status = lot.status
    lot.status = new_status
    lot.save()

    event_map = {
        'expired': 'expired', 'recalled': 'recalled',
        'consumed': 'sold', 'quarantine': 'adjusted', 'active': 'adjusted',
    }
    TraceabilityLog.objects.create(
        tenant=tenant,
        lot=lot,
        event_type=event_map.get(new_status, 'adjusted'),
        quantity=lot.available_quantity,
        reference_type='Status Change',
        reference_number=lot.lot_number,
        performed_by=request.user,
        notes=f'Status changed from {old_status} to {new_status}.',
    )

    messages.success(request, f'Lot status changed to {lot.get_status_display()}.')
    return redirect('lot_tracking:lot_detail', pk=lot.pk)


# ──────────────────────────────────────────────
# Sub-module 2: Serial Number Tracking
# ──────────────────────────────────────────────

@login_required
def serial_list_view(request):
    tenant = request.tenant
    queryset = SerialNumber.objects.filter(tenant=tenant).select_related('product', 'lot', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(serial_number__icontains=q)
            | Q(product__name__icontains=q)
            | Q(lot__lot_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    serials = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'serials': serials,
        'q': q,
        'status_choices': SerialNumber.STATUS_CHOICES,
        'current_status': status,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'lot_tracking/serial_list.html', context)


@login_required
def serial_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = SerialNumberForm(request.POST, tenant=tenant)
        if form.is_valid():
            serial = form.save(commit=False)
            serial.tenant = tenant
            serial.created_by = request.user
            serial.save()

            TraceabilityLog.objects.create(
                tenant=tenant,
                serial_number=serial,
                lot=serial.lot,
                event_type='received',
                to_warehouse=serial.warehouse,
                quantity=1,
                reference_type='Serial Registration',
                reference_number=serial.serial_number,
                performed_by=request.user,
                notes=f'Serial {serial.serial_number} registered.',
            )

            messages.success(request, f'Serial number {serial.serial_number} created successfully.')
            return redirect('lot_tracking:serial_detail', pk=serial.pk)
    else:
        form = SerialNumberForm(tenant=tenant)

    context = {'form': form, 'title': 'Register Serial Number'}
    return render(request, 'lot_tracking/serial_form.html', context)


@login_required
def serial_detail_view(request, pk):
    tenant = request.tenant
    serial = get_object_or_404(SerialNumber, pk=pk, tenant=tenant)
    trace_logs = serial.traceability_logs.select_related(
        'performed_by', 'from_warehouse', 'to_warehouse',
    )[:10]

    context = {
        'serial': serial,
        'trace_logs': trace_logs,
    }
    return render(request, 'lot_tracking/serial_detail.html', context)


@login_required
def serial_edit_view(request, pk):
    tenant = request.tenant
    serial = get_object_or_404(SerialNumber, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = SerialNumberForm(request.POST, instance=serial, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Serial {serial.serial_number} updated successfully.')
            return redirect('lot_tracking:serial_detail', pk=serial.pk)
    else:
        form = SerialNumberForm(instance=serial, tenant=tenant)

    context = {'form': form, 'serial': serial, 'title': 'Edit Serial Number'}
    return render(request, 'lot_tracking/serial_form.html', context)


@login_required
def serial_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('lot_tracking:serial_list')

    tenant = request.tenant
    serial = get_object_or_404(SerialNumber, pk=pk, tenant=tenant)

    if serial.status != 'available':
        messages.warning(request, 'Only available serial numbers can be deleted.')
        return redirect('lot_tracking:serial_detail', pk=serial.pk)

    serial.delete()
    messages.success(request, 'Serial number deleted successfully.')
    return redirect('lot_tracking:serial_list')


@login_required
def serial_transition_view(request, pk, new_status):
    if request.method != 'POST':
        return redirect('lot_tracking:serial_list')

    tenant = request.tenant
    serial = get_object_or_404(SerialNumber, pk=pk, tenant=tenant)

    if not serial.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from {serial.get_status_display()} to {new_status}.')
        return redirect('lot_tracking:serial_detail', pk=serial.pk)

    old_status = serial.status
    serial.status = new_status
    serial.save()

    event_map = {
        'sold': 'sold', 'returned': 'returned', 'scrapped': 'scrapped',
        'damaged': 'adjusted', 'allocated': 'adjusted', 'available': 'adjusted',
    }
    TraceabilityLog.objects.create(
        tenant=tenant,
        serial_number=serial,
        lot=serial.lot,
        event_type=event_map.get(new_status, 'adjusted'),
        quantity=1,
        reference_type='Status Change',
        reference_number=serial.serial_number,
        performed_by=request.user,
        notes=f'Status changed from {old_status} to {new_status}.',
    )

    messages.success(request, f'Serial status changed to {serial.get_status_display()}.')
    return redirect('lot_tracking:serial_detail', pk=serial.pk)


# ──────────────────────────────────────────────
# Sub-module 3: Shelf-Life & Expiry Management
# ──────────────────────────────────────────────

@login_required
def expiry_dashboard_view(request):
    tenant = request.tenant
    today = timezone.now().date()

    expired_lots = LotBatch.objects.filter(
        tenant=tenant, expiry_date__lt=today, status='active',
    ).count()

    approaching_lots = LotBatch.objects.filter(
        tenant=tenant, expiry_date__gte=today,
        expiry_date__lte=today + timezone.timedelta(days=30),
        status='active',
    ).count()

    active_lots = LotBatch.objects.filter(tenant=tenant, status='active').count()
    total_alerts = ExpiryAlert.objects.filter(tenant=tenant, is_acknowledged=False).count()

    lots_with_expiry = LotBatch.objects.filter(
        tenant=tenant, expiry_date__isnull=False, status='active',
    ).select_related('product', 'warehouse').order_by('expiry_date')[:20]

    context = {
        'expired_lots': expired_lots,
        'approaching_lots': approaching_lots,
        'active_lots': active_lots,
        'total_alerts': total_alerts,
        'lots_with_expiry': lots_with_expiry,
        'today': today,
    }
    return render(request, 'lot_tracking/expiry_dashboard.html', context)


@login_required
def expiry_alert_list_view(request):
    tenant = request.tenant
    queryset = ExpiryAlert.objects.filter(tenant=tenant).select_related('lot__product', 'lot__warehouse')

    alert_type = request.GET.get('type', '')
    if alert_type:
        queryset = queryset.filter(alert_type=alert_type)

    acknowledged = request.GET.get('acknowledged', '')
    if acknowledged == 'yes':
        queryset = queryset.filter(is_acknowledged=True)
    elif acknowledged == 'no':
        queryset = queryset.filter(is_acknowledged=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    alerts = paginator.get_page(page_number)

    context = {
        'alerts': alerts,
        'type_choices': ExpiryAlert.ALERT_TYPE_CHOICES,
        'current_type': alert_type,
        'current_acknowledged': acknowledged,
    }
    return render(request, 'lot_tracking/expiry_alert_list.html', context)


@login_required
def expiry_acknowledge_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(ExpiryAlert, pk=pk, tenant=tenant)

    if alert.is_acknowledged:
        messages.info(request, 'This alert has already been acknowledged.')
        return redirect('lot_tracking:expiry_alert_list')

    if request.method == 'POST':
        form = ExpiryAlertAcknowledgeForm(request.POST)
        if form.is_valid():
            alert.is_acknowledged = True
            alert.acknowledged_by = request.user
            alert.acknowledged_at = timezone.now()
            alert.notes = form.cleaned_data.get('notes', '')
            alert.save()
            messages.success(request, f'Alert for {alert.lot.lot_number} acknowledged.')
            return redirect('lot_tracking:expiry_alert_list')
    else:
        form = ExpiryAlertAcknowledgeForm()

    context = {'form': form, 'alert': alert}
    return render(request, 'lot_tracking/expiry_acknowledge_form.html', context)


# ──────────────────────────────────────────────
# Sub-module 4: Traceability & Genealogy
# ──────────────────────────────────────────────

@login_required
def traceability_list_view(request):
    tenant = request.tenant
    queryset = TraceabilityLog.objects.filter(tenant=tenant).select_related(
        'lot', 'serial_number', 'performed_by', 'from_warehouse', 'to_warehouse',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(log_number__icontains=q)
            | Q(lot__lot_number__icontains=q)
            | Q(serial_number__serial_number__icontains=q)
            | Q(reference_number__icontains=q)
        )

    event_type = request.GET.get('event', '')
    if event_type:
        queryset = queryset.filter(event_type=event_type)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    logs = paginator.get_page(page_number)

    context = {
        'logs': logs,
        'q': q,
        'event_choices': TraceabilityLog.EVENT_TYPE_CHOICES,
        'current_event': event_type,
    }
    return render(request, 'lot_tracking/traceability_list.html', context)


@login_required
def traceability_detail_view(request, pk):
    tenant = request.tenant
    log = get_object_or_404(TraceabilityLog, pk=pk, tenant=tenant)

    context = {'log': log}
    return render(request, 'lot_tracking/traceability_detail.html', context)


@login_required
def traceability_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = TraceabilityLogForm(request.POST, tenant=tenant)
        if form.is_valid():
            log = form.save(commit=False)
            log.tenant = tenant
            log.performed_by = request.user
            log.save()
            messages.success(request, f'Traceability log {log.log_number} created.')
            return redirect('lot_tracking:traceability_detail', pk=log.pk)
    else:
        form = TraceabilityLogForm(tenant=tenant)

    context = {'form': form, 'title': 'Create Traceability Log'}
    return render(request, 'lot_tracking/traceability_form.html', context)


@login_required
def lot_trace_view(request, pk):
    tenant = request.tenant
    lot = get_object_or_404(LotBatch, pk=pk, tenant=tenant)
    logs = TraceabilityLog.objects.filter(
        tenant=tenant, lot=lot,
    ).select_related('performed_by', 'from_warehouse', 'to_warehouse').order_by('created_at')

    context = {'lot': lot, 'logs': logs}
    return render(request, 'lot_tracking/lot_trace.html', context)


@login_required
def serial_trace_view(request, pk):
    tenant = request.tenant
    serial = get_object_or_404(SerialNumber, pk=pk, tenant=tenant)
    logs = TraceabilityLog.objects.filter(
        tenant=tenant, serial_number=serial,
    ).select_related('performed_by', 'from_warehouse', 'to_warehouse').order_by('created_at')

    context = {'serial': serial, 'logs': logs}
    return render(request, 'lot_tracking/serial_trace.html', context)
