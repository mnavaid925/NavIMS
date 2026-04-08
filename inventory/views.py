from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F
from django.utils import timezone

from catalog.models import Product
from warehousing.models import Warehouse
from .models import (
    StockLevel, StockAdjustment,
    StockStatus, StockStatusTransition,
    ValuationConfig, InventoryValuation, ValuationEntry,
    InventoryReservation,
)
from .forms import (
    StockAdjustmentForm, StockStatusTransitionForm,
    ValuationConfigForm, InventoryReservationForm,
)


# ──────────────────────────────────────────────
# Sub-module 1: Real-Time Stock Levels
# ──────────────────────────────────────────────

@login_required
def stock_level_list_view(request):
    tenant = request.tenant
    queryset = StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q)
        )

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    low_stock = request.GET.get('low_stock', '')
    if low_stock == 'yes':
        queryset = queryset.filter(reorder_point__gt=0).filter(
            on_hand__lte=F('reorder_point') + F('allocated')
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    stock_levels = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'stock_levels': stock_levels,
        'q': q,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
        'current_low_stock': low_stock,
    }
    return render(request, 'inventory/stock_level_list.html', context)


@login_required
def stock_level_detail_view(request, pk):
    tenant = request.tenant
    stock_level = get_object_or_404(StockLevel, pk=pk, tenant=tenant)
    adjustments = stock_level.adjustments.all()[:10]
    statuses = StockStatus.objects.filter(
        tenant=tenant, product=stock_level.product, warehouse=stock_level.warehouse,
    )
    reservations = InventoryReservation.objects.filter(
        tenant=tenant, product=stock_level.product, warehouse=stock_level.warehouse,
        status__in=['pending', 'confirmed'],
    )

    context = {
        'stock_level': stock_level,
        'adjustments': adjustments,
        'statuses': statuses,
        'reservations': reservations,
    }
    return render(request, 'inventory/stock_level_detail.html', context)


@login_required
def stock_adjust_view(request, pk):
    tenant = request.tenant
    stock_level = get_object_or_404(StockLevel, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST, tenant=tenant)
        if form.is_valid():
            adjustment = form.save(commit=False)
            adjustment.tenant = tenant
            adjustment.stock_level = stock_level
            adjustment.adjusted_by = request.user
            adjustment.save()
            adjustment.apply_adjustment()
            messages.success(request, f'Stock adjustment {adjustment.adjustment_number} applied successfully.')
            return redirect('inventory:stock_level_detail', pk=stock_level.pk)
    else:
        form = StockAdjustmentForm(tenant=tenant)

    context = {
        'form': form,
        'stock_level': stock_level,
        'title': 'Adjust Stock',
    }
    return render(request, 'inventory/stock_adjust_form.html', context)


@login_required
def stock_adjustment_list_view(request):
    tenant = request.tenant
    queryset = StockAdjustment.objects.filter(tenant=tenant).select_related(
        'stock_level__product', 'stock_level__warehouse', 'adjusted_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(adjustment_number__icontains=q) | Q(stock_level__product__name__icontains=q)
        )

    adj_type = request.GET.get('type', '')
    if adj_type:
        queryset = queryset.filter(adjustment_type=adj_type)

    reason = request.GET.get('reason', '')
    if reason:
        queryset = queryset.filter(reason=reason)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    adjustments = paginator.get_page(page_number)

    context = {
        'adjustments': adjustments,
        'q': q,
        'type_choices': StockAdjustment.ADJUSTMENT_TYPE_CHOICES,
        'reason_choices': StockAdjustment.REASON_CHOICES,
        'current_type': adj_type,
        'current_reason': reason,
    }
    return render(request, 'inventory/stock_adjustment_list.html', context)


@login_required
def stock_adjustment_detail_view(request, pk):
    tenant = request.tenant
    adjustment = get_object_or_404(
        StockAdjustment, pk=pk, tenant=tenant,
    )

    context = {
        'adjustment': adjustment,
    }
    return render(request, 'inventory/stock_adjustment_detail.html', context)


# ──────────────────────────────────────────────
# Sub-module 2: Stock Status Management
# ──────────────────────────────────────────────

@login_required
def stock_status_list_view(request):
    tenant = request.tenant
    queryset = StockStatus.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    stock_statuses = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'stock_statuses': stock_statuses,
        'q': q,
        'status_choices': StockStatus.STATUS_CHOICES,
        'current_status': status,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'inventory/stock_status_list.html', context)


@login_required
def stock_status_detail_view(request, pk):
    tenant = request.tenant
    stock_status = get_object_or_404(StockStatus, pk=pk, tenant=tenant)
    transitions = StockStatusTransition.objects.filter(
        tenant=tenant, product=stock_status.product, warehouse=stock_status.warehouse,
    ).select_related('transitioned_by')[:10]

    context = {
        'stock_status': stock_status,
        'transitions': transitions,
    }
    return render(request, 'inventory/stock_status_detail.html', context)


@login_required
def stock_status_transition_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = StockStatusTransitionForm(request.POST, tenant=tenant)
        if form.is_valid():
            transition = form.save(commit=False)
            transition.tenant = tenant
            transition.transitioned_by = request.user
            transition.save()
            transition.apply_transition()
            messages.success(request, f'Status transition {transition.transition_number} applied successfully.')
            return redirect('inventory:stock_status_list')
    else:
        form = StockStatusTransitionForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Change Stock Status',
    }
    return render(request, 'inventory/stock_status_transition_form.html', context)


@login_required
def stock_status_transition_list_view(request):
    tenant = request.tenant
    queryset = StockStatusTransition.objects.filter(tenant=tenant).select_related(
        'product', 'warehouse', 'transitioned_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(transition_number__icontains=q) | Q(product__name__icontains=q)
        )

    from_status = request.GET.get('from_status', '')
    if from_status:
        queryset = queryset.filter(from_status=from_status)

    to_status = request.GET.get('to_status', '')
    if to_status:
        queryset = queryset.filter(to_status=to_status)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    transitions = paginator.get_page(page_number)

    context = {
        'transitions': transitions,
        'q': q,
        'status_choices': StockStatus.STATUS_CHOICES,
        'current_from_status': from_status,
        'current_to_status': to_status,
    }
    return render(request, 'inventory/stock_status_transition_list.html', context)


# ──────────────────────────────────────────────
# Sub-module 3: Inventory Valuation
# ──────────────────────────────────────────────

@login_required
def valuation_dashboard_view(request):
    tenant = request.tenant
    config, _ = ValuationConfig.objects.get_or_create(tenant=tenant)

    valuations = InventoryValuation.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    total_value = valuations.aggregate(total=Sum('total_value'))['total'] or 0
    total_products = valuations.values('product').distinct().count()

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        valuations = valuations.filter(warehouse_id=warehouse_id)

    paginator = Paginator(valuations, 20)
    page_number = request.GET.get('page')
    valuations_page = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'config': config,
        'valuations': valuations_page,
        'total_value': total_value,
        'total_products': total_products,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'inventory/valuation_dashboard.html', context)


@login_required
def valuation_detail_view(request, pk):
    tenant = request.tenant
    valuation = get_object_or_404(InventoryValuation, pk=pk, tenant=tenant)
    cost_layers = ValuationEntry.objects.filter(
        tenant=tenant, product=valuation.product, warehouse=valuation.warehouse,
    )

    context = {
        'valuation': valuation,
        'cost_layers': cost_layers,
    }
    return render(request, 'inventory/valuation_detail.html', context)


@login_required
def valuation_config_view(request):
    tenant = request.tenant
    config, _ = ValuationConfig.objects.get_or_create(tenant=tenant)

    if request.method == 'POST':
        form = ValuationConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Valuation configuration updated successfully.')
            return redirect('inventory:valuation_dashboard')
    else:
        form = ValuationConfigForm(instance=config)

    context = {
        'form': form,
        'config': config,
        'title': 'Valuation Configuration',
    }
    return render(request, 'inventory/valuation_config_form.html', context)


@login_required
def valuation_recalculate_view(request):
    if request.method != 'POST':
        return redirect('inventory:valuation_dashboard')

    tenant = request.tenant
    config, _ = ValuationConfig.objects.get_or_create(tenant=tenant)
    today = timezone.now().date()

    # Delete old valuations for today and recalculate
    InventoryValuation.objects.filter(tenant=tenant, valuation_date=today).delete()

    stock_levels = StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    for sl in stock_levels:
        entries = ValuationEntry.objects.filter(
            tenant=tenant, product=sl.product, warehouse=sl.warehouse,
            remaining_quantity__gt=0,
        )

        total_qty = entries.aggregate(total=Sum('remaining_quantity'))['total'] or 0
        if total_qty == 0:
            continue

        if config.method == 'weighted_avg':
            total_cost = sum(e.remaining_quantity * e.unit_cost for e in entries)
            unit_cost = total_cost / total_qty if total_qty > 0 else 0
        elif config.method == 'fifo':
            sorted_entries = entries.order_by('entry_date', 'id')
            total_cost = sum(e.remaining_quantity * e.unit_cost for e in sorted_entries)
            unit_cost = total_cost / total_qty if total_qty > 0 else 0
        elif config.method == 'lifo':
            sorted_entries = entries.order_by('-entry_date', '-id')
            total_cost = sum(e.remaining_quantity * e.unit_cost for e in sorted_entries)
            unit_cost = total_cost / total_qty if total_qty > 0 else 0
        else:
            unit_cost = 0

        total_value = total_qty * unit_cost

        InventoryValuation.objects.create(
            tenant=tenant,
            product=sl.product,
            warehouse=sl.warehouse,
            valuation_date=today,
            method=config.method,
            total_quantity=total_qty,
            unit_cost=round(unit_cost, 2),
            total_value=round(total_value, 2),
        )

    config.last_calculated_at = timezone.now()
    config.save()

    messages.success(request, 'Inventory valuation recalculated successfully.')
    return redirect('inventory:valuation_dashboard')


# ──────────────────────────────────────────────
# Sub-module 4: Inventory Reservations
# ──────────────────────────────────────────────

@login_required
def reservation_list_view(request):
    tenant = request.tenant
    queryset = InventoryReservation.objects.filter(tenant=tenant).select_related(
        'product', 'warehouse', 'reserved_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(reservation_number__icontains=q)
            | Q(reference_number__icontains=q)
            | Q(product__name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    reservations = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'reservations': reservations,
        'q': q,
        'status_choices': InventoryReservation.STATUS_CHOICES,
        'current_status': status,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'inventory/reservation_list.html', context)


@login_required
def reservation_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = InventoryReservationForm(request.POST, tenant=tenant)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.tenant = tenant
            reservation.reserved_by = request.user
            reservation.save()
            messages.success(request, f'Reservation {reservation.reservation_number} created successfully.')
            return redirect('inventory:reservation_detail', pk=reservation.pk)
    else:
        form = InventoryReservationForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Reservation',
    }
    return render(request, 'inventory/reservation_form.html', context)


@login_required
def reservation_detail_view(request, pk):
    tenant = request.tenant
    reservation = get_object_or_404(InventoryReservation, pk=pk, tenant=tenant)

    context = {
        'reservation': reservation,
    }
    return render(request, 'inventory/reservation_detail.html', context)


@login_required
def reservation_edit_view(request, pk):
    tenant = request.tenant
    reservation = get_object_or_404(InventoryReservation, pk=pk, tenant=tenant)

    if reservation.status != 'pending':
        messages.warning(request, 'Only pending reservations can be edited.')
        return redirect('inventory:reservation_detail', pk=reservation.pk)

    if request.method == 'POST':
        form = InventoryReservationForm(request.POST, instance=reservation, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Reservation {reservation.reservation_number} updated successfully.')
            return redirect('inventory:reservation_detail', pk=reservation.pk)
    else:
        form = InventoryReservationForm(instance=reservation, tenant=tenant)

    context = {
        'form': form,
        'reservation': reservation,
        'title': 'Edit Reservation',
    }
    return render(request, 'inventory/reservation_form.html', context)


@login_required
def reservation_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('inventory:reservation_list')

    reservation = get_object_or_404(InventoryReservation, pk=pk, tenant=tenant)

    if reservation.status not in ('pending', 'cancelled'):
        messages.warning(request, 'Only pending or cancelled reservations can be deleted.')
        return redirect('inventory:reservation_detail', pk=reservation.pk)

    reservation.delete()
    messages.success(request, 'Reservation deleted successfully.')
    return redirect('inventory:reservation_list')


@login_required
def reservation_transition_view(request, pk, new_status):
    if request.method != 'POST':
        return redirect('inventory:reservation_list')

    tenant = request.tenant
    reservation = get_object_or_404(InventoryReservation, pk=pk, tenant=tenant)

    if not reservation.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from {reservation.get_status_display()} to {new_status}.')
        return redirect('inventory:reservation_detail', pk=reservation.pk)

    old_status = reservation.status
    reservation.status = new_status
    reservation.save()

    # Update StockLevel allocated quantity
    try:
        stock_level = StockLevel.objects.get(
            tenant=tenant, product=reservation.product, warehouse=reservation.warehouse,
        )
        if new_status == 'confirmed' and old_status == 'pending':
            stock_level.allocated += reservation.quantity
            stock_level.save()
        elif new_status in ('released', 'cancelled', 'expired') and old_status == 'confirmed':
            stock_level.allocated = max(stock_level.allocated - reservation.quantity, 0)
            stock_level.save()
    except StockLevel.DoesNotExist:
        pass

    messages.success(request, f'Reservation status changed to {reservation.get_status_display()}.')
    return redirect('inventory:reservation_detail', pk=reservation.pk)
