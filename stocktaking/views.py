from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from warehousing.models import Warehouse, Zone
from inventory.models import StockLevel, StockAdjustment
from .models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)
from .forms import (
    StocktakeFreezeForm, CycleCountScheduleForm,
    StockCountForm, StockCountItemFormSet, StockVarianceAdjustmentForm,
)


# ══════════════════════════════════════════════
# Stocktake Freeze CRUD
# ══════════════════════════════════════════════

@login_required
def freeze_list_view(request):
    tenant = request.tenant
    queryset = StocktakeFreeze.objects.filter(tenant=tenant).select_related('warehouse', 'frozen_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(freeze_number__icontains=q) | Q(reason__icontains=q))

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    freezes = paginator.get_page(request.GET.get('page'))

    return render(request, 'stocktaking/freeze_list.html', {
        'freezes': freezes,
        'q': q,
        'status_choices': StocktakeFreeze.STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_warehouse': warehouse_id,
    })


@login_required
def freeze_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = StocktakeFreezeForm(request.POST, tenant=tenant)
        if form.is_valid():
            freeze = form.save(commit=False)
            freeze.tenant = tenant
            freeze.frozen_by = request.user
            freeze.frozen_at = timezone.now()
            freeze.save()
            form.save_m2m()
            messages.success(request, f'Warehouse freeze "{freeze.freeze_number}" activated.')
            return redirect('stocktaking:freeze_list')
    else:
        form = StocktakeFreezeForm(tenant=tenant)
    return render(request, 'stocktaking/freeze_form.html', {'form': form, 'title': 'Freeze Warehouse'})


@login_required
def freeze_edit_view(request, pk):
    tenant = request.tenant
    freeze = get_object_or_404(StocktakeFreeze, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = StocktakeFreezeForm(request.POST, instance=freeze, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Freeze "{freeze.freeze_number}" updated.')
            return redirect('stocktaking:freeze_list')
    else:
        form = StocktakeFreezeForm(instance=freeze, tenant=tenant)
    return render(request, 'stocktaking/freeze_form.html', {
        'form': form, 'freeze': freeze, 'title': f'Edit Freeze {freeze.freeze_number}',
    })


@login_required
def freeze_release_view(request, pk):
    tenant = request.tenant
    freeze = get_object_or_404(StocktakeFreeze, pk=pk, tenant=tenant)
    if freeze.status == 'active':
        freeze.status = 'released'
        freeze.released_at = timezone.now()
        freeze.save()
        messages.success(request, f'Freeze "{freeze.freeze_number}" released.')
    else:
        messages.error(request, 'Freeze is not active.')
    return redirect('stocktaking:freeze_list')


@login_required
def freeze_delete_view(request, pk):
    tenant = request.tenant
    freeze = get_object_or_404(StocktakeFreeze, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = freeze.freeze_number
        freeze.delete()
        messages.success(request, f'Freeze "{num}" deleted.')
        return redirect('stocktaking:freeze_list')
    return redirect('stocktaking:freeze_list')


# ══════════════════════════════════════════════
# Cycle Count Schedule CRUD
# ══════════════════════════════════════════════

@login_required
def schedule_list_view(request):
    tenant = request.tenant
    queryset = CycleCountSchedule.objects.filter(tenant=tenant).select_related('warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(name__icontains=q)

    frequency = request.GET.get('frequency', '')
    if frequency:
        queryset = queryset.filter(frequency=frequency)

    active = request.GET.get('active', '')
    if active == 'active':
        queryset = queryset.filter(is_active=True)
    elif active == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    schedules = paginator.get_page(request.GET.get('page'))

    return render(request, 'stocktaking/schedule_list.html', {
        'schedules': schedules,
        'q': q,
        'frequency_choices': CycleCountSchedule.FREQUENCY_CHOICES,
        'current_frequency': frequency,
        'current_active': active,
    })


@login_required
def schedule_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = CycleCountScheduleForm(request.POST, tenant=tenant)
        if form.is_valid():
            sched = form.save(commit=False)
            sched.tenant = tenant
            sched.created_by = request.user
            sched.save()
            form.save_m2m()
            messages.success(request, f'Schedule "{sched.name}" created.')
            return redirect('stocktaking:schedule_detail', pk=sched.pk)
    else:
        form = CycleCountScheduleForm(tenant=tenant)
    return render(request, 'stocktaking/schedule_form.html', {'form': form, 'title': 'Create Cycle Count Schedule'})


@login_required
def schedule_edit_view(request, pk):
    tenant = request.tenant
    sched = get_object_or_404(CycleCountSchedule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = CycleCountScheduleForm(request.POST, instance=sched, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Schedule "{sched.name}" updated.')
            return redirect('stocktaking:schedule_detail', pk=sched.pk)
    else:
        form = CycleCountScheduleForm(instance=sched, tenant=tenant)
    return render(request, 'stocktaking/schedule_form.html', {
        'form': form, 'schedule': sched, 'title': f'Edit {sched.name}',
    })


@login_required
def schedule_detail_view(request, pk):
    tenant = request.tenant
    sched = get_object_or_404(
        CycleCountSchedule.objects.select_related('warehouse', 'created_by').prefetch_related('zones'),
        pk=pk, tenant=tenant,
    )
    recent_counts = sched.stock_counts.order_by('-created_at')[:10]
    return render(request, 'stocktaking/schedule_detail.html', {
        'schedule': sched,
        'recent_counts': recent_counts,
    })


@login_required
def schedule_delete_view(request, pk):
    tenant = request.tenant
    sched = get_object_or_404(CycleCountSchedule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        name = sched.name
        sched.delete()
        messages.success(request, f'Schedule "{name}" deleted.')
        return redirect('stocktaking:schedule_list')
    return redirect('stocktaking:schedule_list')


@login_required
def schedule_run_view(request, pk):
    """Create a new StockCount from a schedule, pre-populated with items."""
    tenant = request.tenant
    sched = get_object_or_404(CycleCountSchedule, pk=pk, tenant=tenant)

    count = StockCount.objects.create(
        tenant=tenant,
        type='cycle',
        warehouse=sched.warehouse,
        zone=sched.zones.first() if sched.zones.exists() else None,
        schedule=sched,
        status='draft',
        scheduled_date=timezone.now().date(),
        created_by=request.user,
        notes=f'Generated from schedule: {sched.name}',
    )
    _populate_count_items(count)
    sched.last_run_date = timezone.now().date()
    sched.save()
    messages.success(request, f'Count "{count.count_number}" created from schedule.')
    return redirect('stocktaking:count_detail', pk=count.pk)


# ══════════════════════════════════════════════
# Stock Count CRUD
# ══════════════════════════════════════════════

def _populate_count_items(count):
    """Snapshot StockLevel rows as count items."""
    qs = StockLevel.objects.filter(tenant=count.tenant, warehouse=count.warehouse).select_related('product')
    for sl in qs:
        if StockCountItem.objects.filter(count=count, product=sl.product).exists():
            continue
        StockCountItem.objects.create(
            tenant=count.tenant,
            count=count,
            product=sl.product,
            system_qty=sl.on_hand,
            unit_cost=sl.product.purchase_cost or Decimal('0.00'),
        )


@login_required
def count_list_view(request):
    tenant = request.tenant
    queryset = StockCount.objects.filter(tenant=tenant).select_related('warehouse', 'zone', 'assigned_to')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(count_number__icontains=q) | Q(notes__icontains=q))

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    type_filter = request.GET.get('type', '')
    if type_filter:
        queryset = queryset.filter(type=type_filter)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    counts = paginator.get_page(request.GET.get('page'))

    return render(request, 'stocktaking/count_list.html', {
        'counts': counts,
        'q': q,
        'status_choices': StockCount.STATUS_CHOICES,
        'type_choices': StockCount.TYPE_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_type': type_filter,
        'current_warehouse': warehouse_id,
    })


@login_required
def count_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = StockCountForm(request.POST, tenant=tenant)
        if form.is_valid():
            count = form.save(commit=False)
            count.tenant = tenant
            count.created_by = request.user
            count.save()
            _populate_count_items(count)
            messages.success(request, f'Count "{count.count_number}" created with {count.total_items} items.')
            return redirect('stocktaking:count_detail', pk=count.pk)
    else:
        form = StockCountForm(tenant=tenant)
    return render(request, 'stocktaking/count_form.html', {'form': form, 'title': 'Create Stock Count'})


@login_required
def count_edit_view(request, pk):
    tenant = request.tenant
    count = get_object_or_404(StockCount, pk=pk, tenant=tenant)
    if count.status not in ['draft', 'cancelled']:
        messages.error(request, 'Cannot edit a count after it has started.')
        return redirect('stocktaking:count_detail', pk=count.pk)
    if request.method == 'POST':
        form = StockCountForm(request.POST, instance=count, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Count "{count.count_number}" updated.')
            return redirect('stocktaking:count_detail', pk=count.pk)
    else:
        form = StockCountForm(instance=count, tenant=tenant)
    return render(request, 'stocktaking/count_form.html', {
        'form': form, 'count': count, 'title': f'Edit {count.count_number}',
    })


@login_required
def count_detail_view(request, pk):
    tenant = request.tenant
    count = get_object_or_404(
        StockCount.objects.select_related('warehouse', 'zone', 'schedule', 'freeze', 'assigned_to', 'counted_by', 'reviewed_by'),
        pk=pk, tenant=tenant,
    )
    items = count.items.select_related('product', 'bin_location').all()
    variance_adjustments = count.variance_adjustments.all()
    return render(request, 'stocktaking/count_detail.html', {
        'count': count,
        'items': items,
        'variance_adjustments': variance_adjustments,
    })


@login_required
def count_sheet_view(request, pk):
    """The count-sheet screen where counters enter counted quantities."""
    tenant = request.tenant
    count = get_object_or_404(StockCount, pk=pk, tenant=tenant)

    if request.method == 'POST':
        formset = StockCountItemFormSet(request.POST, instance=count, prefix='items')
        if formset.is_valid():
            items = formset.save(commit=False)
            now = timezone.now()
            for item in items:
                if item.counted_qty is not None and item.counted_at is None:
                    item.counted_at = now
                    item.counted_by = request.user
                item.save()
            if count.status == 'draft':
                count.status = 'in_progress'
                count.started_at = now
                count.save()
            messages.success(request, 'Count progress saved.')
            if 'submit_count' in request.POST and count.can_transition_to('counted'):
                count.status = 'counted'
                count.completed_at = now
                count.counted_by = request.user
                count.save()
                messages.success(request, f'Count "{count.count_number}" submitted for review.')
                return redirect('stocktaking:count_detail', pk=count.pk)
            return redirect('stocktaking:count_sheet', pk=count.pk)
    else:
        formset = StockCountItemFormSet(instance=count, prefix='items')

    items_with_forms = list(zip(count.items.select_related('product', 'bin_location').all(), formset.forms))

    return render(request, 'stocktaking/count_sheet.html', {
        'count': count,
        'formset': formset,
        'items_with_forms': items_with_forms,
    })


@login_required
def count_delete_view(request, pk):
    tenant = request.tenant
    count = get_object_or_404(StockCount, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = count.count_number
        count.delete()
        messages.success(request, f'Count "{num}" deleted.')
        return redirect('stocktaking:count_list')
    return redirect('stocktaking:count_list')


@login_required
def count_start_view(request, pk):
    tenant = request.tenant
    count = get_object_or_404(StockCount, pk=pk, tenant=tenant)
    if count.can_transition_to('in_progress'):
        count.status = 'in_progress'
        count.started_at = timezone.now()
        count.save()
        messages.success(request, f'Count "{count.count_number}" started.')
    else:
        messages.error(request, 'Cannot start count.')
    return redirect('stocktaking:count_sheet', pk=pk)


@login_required
def count_review_view(request, pk):
    tenant = request.tenant
    count = get_object_or_404(StockCount, pk=pk, tenant=tenant)
    if count.can_transition_to('reviewed'):
        count.status = 'reviewed'
        count.reviewed_at = timezone.now()
        count.reviewed_by = request.user
        count.save()
        messages.success(request, f'Count "{count.count_number}" marked as reviewed.')
    else:
        messages.error(request, 'Cannot mark as reviewed.')
    return redirect('stocktaking:count_detail', pk=pk)


@login_required
def count_cancel_view(request, pk):
    tenant = request.tenant
    count = get_object_or_404(StockCount, pk=pk, tenant=tenant)
    if count.can_transition_to('cancelled'):
        count.status = 'cancelled'
        count.save()
        messages.success(request, 'Count cancelled.')
    else:
        messages.error(request, 'Cannot cancel count.')
    return redirect('stocktaking:count_detail', pk=pk)


# ══════════════════════════════════════════════
# Variance Adjustment CRUD
# ══════════════════════════════════════════════

@login_required
def adjustment_list_view(request):
    tenant = request.tenant
    queryset = StockVarianceAdjustment.objects.filter(tenant=tenant).select_related('count', 'approved_by', 'posted_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(adjustment_number__icontains=q) | Q(count__count_number__icontains=q))

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    reason = request.GET.get('reason', '')
    if reason:
        queryset = queryset.filter(reason_code=reason)

    paginator = Paginator(queryset, 20)
    adjustments = paginator.get_page(request.GET.get('page'))

    return render(request, 'stocktaking/adjustment_list.html', {
        'adjustments': adjustments,
        'q': q,
        'status_choices': StockVarianceAdjustment.STATUS_CHOICES,
        'reason_choices': StockVarianceAdjustment.REASON_CODE_CHOICES,
        'current_status': status,
        'current_reason': reason,
    })


@login_required
def adjustment_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = StockVarianceAdjustmentForm(request.POST, tenant=tenant)
        if form.is_valid():
            adj = form.save(commit=False)
            adj.tenant = tenant
            adj.created_by = request.user
            count = adj.count
            items_with_variance = count.items.exclude(counted_qty__isnull=True).exclude(counted_qty__exact=0).all()
            total_qty = 0
            total_value = Decimal('0.00')
            for item in count.items.exclude(counted_qty__isnull=True):
                if item.has_variance:
                    total_qty += item.variance
                    total_value += item.variance_value
            adj.total_variance_qty = total_qty
            adj.total_variance_value = total_value
            adj.save()
            messages.success(request, f'Variance adjustment "{adj.adjustment_number}" created.')
            return redirect('stocktaking:adjustment_detail', pk=adj.pk)
    else:
        form = StockVarianceAdjustmentForm(tenant=tenant)
    return render(request, 'stocktaking/adjustment_form.html', {
        'form': form, 'title': 'Create Variance Adjustment',
    })


@login_required
def adjustment_edit_view(request, pk):
    tenant = request.tenant
    adj = get_object_or_404(StockVarianceAdjustment, pk=pk, tenant=tenant)
    if adj.status == 'posted':
        messages.error(request, 'Cannot edit a posted adjustment.')
        return redirect('stocktaking:adjustment_detail', pk=adj.pk)
    if request.method == 'POST':
        form = StockVarianceAdjustmentForm(request.POST, instance=adj, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Adjustment "{adj.adjustment_number}" updated.')
            return redirect('stocktaking:adjustment_detail', pk=adj.pk)
    else:
        form = StockVarianceAdjustmentForm(instance=adj, tenant=tenant)
    return render(request, 'stocktaking/adjustment_form.html', {
        'form': form, 'adjustment': adj, 'title': f'Edit {adj.adjustment_number}',
    })


@login_required
def adjustment_detail_view(request, pk):
    tenant = request.tenant
    adj = get_object_or_404(
        StockVarianceAdjustment.objects.select_related('count', 'approved_by', 'posted_by', 'created_by'),
        pk=pk, tenant=tenant,
    )
    variance_items = adj.count.items.exclude(counted_qty__isnull=True).select_related('product', 'bin_location')
    return render(request, 'stocktaking/adjustment_detail.html', {
        'adjustment': adj,
        'variance_items': variance_items,
    })


@login_required
def adjustment_delete_view(request, pk):
    tenant = request.tenant
    adj = get_object_or_404(StockVarianceAdjustment, pk=pk, tenant=tenant)
    if adj.status == 'posted':
        messages.error(request, 'Cannot delete a posted adjustment.')
        return redirect('stocktaking:adjustment_detail', pk=pk)
    if request.method == 'POST':
        num = adj.adjustment_number
        adj.delete()
        messages.success(request, f'Adjustment "{num}" deleted.')
        return redirect('stocktaking:adjustment_list')
    return redirect('stocktaking:adjustment_list')


@login_required
def adjustment_approve_view(request, pk):
    tenant = request.tenant
    adj = get_object_or_404(StockVarianceAdjustment, pk=pk, tenant=tenant)
    if adj.can_transition_to('approved'):
        adj.status = 'approved'
        adj.approved_by = request.user
        adj.approved_at = timezone.now()
        adj.save()
        messages.success(request, f'Adjustment "{adj.adjustment_number}" approved.')
    else:
        messages.error(request, 'Cannot approve adjustment.')
    return redirect('stocktaking:adjustment_detail', pk=pk)


@login_required
def adjustment_reject_view(request, pk):
    tenant = request.tenant
    adj = get_object_or_404(StockVarianceAdjustment, pk=pk, tenant=tenant)
    if adj.can_transition_to('rejected'):
        adj.status = 'rejected'
        adj.save()
        messages.success(request, f'Adjustment "{adj.adjustment_number}" rejected.')
    else:
        messages.error(request, 'Cannot reject adjustment.')
    return redirect('stocktaking:adjustment_detail', pk=pk)


@login_required
def adjustment_post_view(request, pk):
    """Post variance adjustment — creates StockAdjustment entries and updates StockLevel."""
    tenant = request.tenant
    adj = get_object_or_404(StockVarianceAdjustment, pk=pk, tenant=tenant)
    if not adj.can_transition_to('posted'):
        messages.error(request, 'Cannot post adjustment in current status.')
        return redirect('stocktaking:adjustment_detail', pk=pk)

    count = adj.count
    for item in count.items.exclude(counted_qty__isnull=True):
        if not item.has_variance:
            continue
        stock, _ = StockLevel.objects.get_or_create(
            tenant=tenant,
            product=item.product,
            warehouse=count.warehouse,
            defaults={'on_hand': 0, 'allocated': 0, 'on_order': 0},
        )
        variance = item.variance
        adjustment_type = 'increase' if variance > 0 else 'decrease'
        StockAdjustment.objects.create(
            tenant=tenant,
            stock_level=stock,
            adjustment_type=adjustment_type,
            reason='count',
            quantity=abs(variance),
            notes=f'Variance from count {count.count_number} — {item.get_reason_code_display() or adj.get_reason_code_display()}',
            adjusted_by=request.user,
        )
        stock.on_hand = item.counted_qty
        stock.last_counted_at = timezone.now()
        stock.save()

    adj.status = 'posted'
    adj.posted_by = request.user
    adj.posted_at = timezone.now()
    adj.save()
    count.status = 'adjusted'
    count.adjusted_at = timezone.now()
    count.save()
    messages.success(request, f'Adjustment "{adj.adjustment_number}" posted. Stock levels updated.')
    return redirect('stocktaking:adjustment_detail', pk=pk)
