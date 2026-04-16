import json
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone

from catalog.models import Product
from core.models import AuditLog
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
# Decorators / helpers
# ──────────────────────────────────────────────

def tenant_admin_required(view_func):
    """Restrict destructive inventory views to tenant admins (D-05)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and getattr(user, 'is_tenant_admin', False)):
            messages.error(
                request,
                'You do not have permission to perform this action.',
            )
            return redirect('inventory:stock_level_list')
        return view_func(request, *args, **kwargs)
    return _wrapped


def tenant_required(view_func):
    """Guard views that require a tenant — superuser (`tenant=None`) is redirected (D-09)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(request, 'tenant', None) is None:
            messages.warning(
                request,
                'This page is scoped to a tenant. Log in as a tenant admin to view inventory.',
            )
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _audit(request, action, obj, model_name, changes=None):
    """Write an AuditLog row for an inventory mutation (D-07)."""
    AuditLog.objects.create(
        tenant=request.tenant,
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model_name=model_name,
        object_id=str(obj.pk),
        changes=json.dumps(changes or {}, default=str),
        ip_address=request.META.get('REMOTE_ADDR') or None,
    )


def _coerce_int(value, default=None):
    """Coerce a GET param to int safely (D-11)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _compute_unit_cost(entries, on_hand, method):
    """Compute per-unit cost of `on_hand` from `entries` under `method` (D-04).

    Returns (unit_cost, total_value) both as 2-dp Decimals.

    - **weighted_avg**: Σ(layer.qty × layer.cost) / Σ layer.qty across all layers.
    - **fifo**: assume oldest layers were consumed first → value `on_hand`
      against newest layers; walk newest → oldest.
    - **lifo**: assume newest layers were consumed first → value `on_hand`
      against oldest layers; walk oldest → newest.

    If `on_hand` exceeds total layer quantity, the residual is valued at
    weighted-avg of all layers (soft fallback).
    """
    two_dp = Decimal('0.01')
    if on_hand <= 0:
        return Decimal('0.00'), Decimal('0.00')

    entries = list(entries)
    if not entries:
        return Decimal('0.00'), Decimal('0.00')

    total_layer_qty = sum(int(e.quantity) for e in entries)
    wavg_numer = sum(int(e.quantity) * Decimal(e.unit_cost) for e in entries)
    wavg_unit = (wavg_numer / total_layer_qty) if total_layer_qty else Decimal('0')

    if method == 'weighted_avg' or not entries:
        unit_cost = wavg_unit
    else:
        if method == 'fifo':
            sorted_entries = sorted(
                entries, key=lambda e: (e.entry_date, e.id), reverse=True,
            )
        elif method == 'lifo':
            sorted_entries = sorted(
                entries, key=lambda e: (e.entry_date, e.id),
            )
        else:
            sorted_entries = entries

        remaining = on_hand
        allocated_cost = Decimal('0')
        allocated_qty = 0
        for e in sorted_entries:
            take = min(int(e.quantity), remaining)
            allocated_cost += Decimal(take) * Decimal(e.unit_cost)
            allocated_qty += take
            remaining -= take
            if remaining <= 0:
                break
        # Soft fallback for overflow (on_hand > total layer qty): use wavg
        if remaining > 0 and wavg_unit > 0:
            allocated_cost += Decimal(remaining) * wavg_unit
            allocated_qty += remaining
        unit_cost = (allocated_cost / Decimal(on_hand)) if on_hand else Decimal('0')

    unit_cost = unit_cost.quantize(two_dp, rounding=ROUND_HALF_UP)
    total_value = (Decimal(on_hand) * unit_cost).quantize(two_dp, rounding=ROUND_HALF_UP)
    return unit_cost, total_value


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
    warehouse_pk = _coerce_int(warehouse_id)
    if warehouse_pk:
        queryset = queryset.filter(warehouse_id=warehouse_pk)
    else:
        warehouse_id = ''  # keep template consistent on bad input

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
@tenant_admin_required
def stock_adjust_view(request, pk):
    tenant = request.tenant
    stock_level = get_object_or_404(StockLevel, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST, tenant=tenant, stock_level=stock_level)
        if form.is_valid():
            with transaction.atomic():
                adjustment = form.save(commit=False)
                adjustment.tenant = tenant
                adjustment.stock_level = stock_level
                adjustment.adjusted_by = request.user
                adjustment.save()
                adjustment.apply_adjustment()
            _audit(request, 'inventory.adjust', adjustment, 'StockAdjustment', {
                'adjustment_number': adjustment.adjustment_number,
                'stock_level_id': stock_level.pk,
                'type': adjustment.adjustment_type,
                'quantity': adjustment.quantity,
            })
            messages.success(
                request,
                f'Stock adjustment {adjustment.adjustment_number} applied successfully.',
            )
            return redirect('inventory:stock_level_detail', pk=stock_level.pk)
    else:
        form = StockAdjustmentForm(tenant=tenant, stock_level=stock_level)

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
    warehouse_pk = _coerce_int(warehouse_id)
    if warehouse_pk:
        queryset = queryset.filter(warehouse_id=warehouse_pk)
    else:
        warehouse_id = ''

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
@tenant_admin_required
def stock_status_transition_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = StockStatusTransitionForm(request.POST, tenant=tenant)
        if form.is_valid():
            with transaction.atomic():
                transition = form.save(commit=False)
                transition.tenant = tenant
                transition.transitioned_by = request.user
                transition.save()
                transition.apply_transition()
            _audit(request, 'inventory.status_transition', transition,
                   'StockStatusTransition', {
                       'transition_number': transition.transition_number,
                       'from': transition.from_status,
                       'to': transition.to_status,
                       'quantity': transition.quantity,
                   })
            messages.success(
                request,
                f'Status transition {transition.transition_number} applied successfully.',
            )
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
@tenant_required
def valuation_dashboard_view(request):
    tenant = request.tenant
    config, _ = ValuationConfig.objects.get_or_create(tenant=tenant)

    valuations = InventoryValuation.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    total_value = valuations.aggregate(total=Sum('total_value'))['total'] or 0
    total_products = valuations.values('product').distinct().count()

    warehouse_id = request.GET.get('warehouse', '')
    warehouse_pk = _coerce_int(warehouse_id)
    if warehouse_pk:
        valuations = valuations.filter(warehouse_id=warehouse_pk)
    else:
        warehouse_id = ''

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
@tenant_required
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
@tenant_admin_required
@tenant_required
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
@tenant_admin_required
@tenant_required
def valuation_recalculate_view(request):
    """Recompute today's valuation snapshot using the active method (D-04, D-12)."""
    if request.method != 'POST':
        return redirect('inventory:valuation_dashboard')

    tenant = request.tenant
    config, _ = ValuationConfig.objects.get_or_create(tenant=tenant)
    today = timezone.now().date()

    stock_levels = list(
        StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse')
    )

    with transaction.atomic():
        InventoryValuation.objects.filter(tenant=tenant, valuation_date=today).delete()

        for sl in stock_levels:
            if sl.on_hand == 0:
                continue
            entries = ValuationEntry.objects.filter(
                tenant=tenant, product=sl.product, warehouse=sl.warehouse,
            )
            unit_cost, total_value = _compute_unit_cost(entries, sl.on_hand, config.method)
            if unit_cost == 0 and total_value == 0 and not entries.exists():
                continue

            InventoryValuation.objects.create(
                tenant=tenant,
                product=sl.product,
                warehouse=sl.warehouse,
                valuation_date=today,
                method=config.method,
                total_quantity=sl.on_hand,
                unit_cost=unit_cost,
                total_value=total_value,
            )

        config.last_calculated_at = timezone.now()
        config.save()

    _audit(request, 'inventory.valuation_recalculate', config,
           'ValuationConfig', {'method': config.method, 'date': str(today)})
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
    warehouse_pk = _coerce_int(warehouse_id)
    if warehouse_pk:
        queryset = queryset.filter(warehouse_id=warehouse_pk)
    else:
        warehouse_id = ''

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
@tenant_admin_required
def reservation_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = InventoryReservationForm(request.POST, tenant=tenant)
        if form.is_valid():
            with transaction.atomic():
                reservation = form.save(commit=False)
                reservation.tenant = tenant
                reservation.reserved_by = request.user
                reservation.save()
            _audit(request, 'inventory.reservation_create', reservation,
                   'InventoryReservation', {
                       'reservation_number': reservation.reservation_number,
                       'quantity': reservation.quantity,
                   })
            messages.success(
                request,
                f'Reservation {reservation.reservation_number} created successfully.',
            )
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
@tenant_admin_required
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
            _audit(request, 'inventory.reservation_edit', reservation,
                   'InventoryReservation', {
                       'reservation_number': reservation.reservation_number,
                   })
            messages.success(
                request,
                f'Reservation {reservation.reservation_number} updated successfully.',
            )
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
@tenant_admin_required
def reservation_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('inventory:reservation_list')

    reservation = get_object_or_404(InventoryReservation, pk=pk, tenant=tenant)

    if reservation.status not in ('pending', 'cancelled'):
        messages.warning(request, 'Only pending or cancelled reservations can be deleted.')
        return redirect('inventory:reservation_detail', pk=reservation.pk)

    _audit(request, 'inventory.reservation_delete', reservation,
           'InventoryReservation', {
               'reservation_number': reservation.reservation_number,
           })
    reservation.delete()
    messages.success(request, 'Reservation deleted successfully.')
    return redirect('inventory:reservation_list')


@login_required
@tenant_admin_required
def reservation_transition_view(request, pk, new_status):
    if request.method != 'POST':
        return redirect('inventory:reservation_list')

    tenant = request.tenant
    reservation = get_object_or_404(InventoryReservation, pk=pk, tenant=tenant)

    if not reservation.can_transition_to(new_status):
        messages.error(
            request,
            f'Cannot transition from {reservation.get_status_display()} to {new_status}.',
        )
        return redirect('inventory:reservation_detail', pk=reservation.pk)

    old_status = reservation.status
    with transaction.atomic():
        reservation.status = new_status
        reservation.save()

        try:
            stock_level = StockLevel.objects.select_for_update().get(
                tenant=tenant, product=reservation.product, warehouse=reservation.warehouse,
            )
        except StockLevel.DoesNotExist:
            # D-17: no silent pass — log the inconsistency so it surfaces.
            _audit(request, 'inventory.reservation_transition_no_stock_level',
                   reservation, 'InventoryReservation', {
                       'old_status': old_status, 'new_status': new_status,
                   })
            messages.warning(
                request,
                f'Reservation status changed but no stock level record exists '
                f'for {reservation.product.sku} at {reservation.warehouse.code}.',
            )
            return redirect('inventory:reservation_detail', pk=reservation.pk)

        if new_status == 'confirmed' and old_status == 'pending':
            stock_level.allocated += reservation.quantity
            stock_level.save()
        elif new_status in ('released', 'cancelled', 'expired') and old_status == 'confirmed':
            stock_level.allocated = max(stock_level.allocated - reservation.quantity, 0)
            stock_level.save()

    _audit(request, 'inventory.reservation_transition', reservation,
           'InventoryReservation', {
               'reservation_number': reservation.reservation_number,
               'old_status': old_status, 'new_status': new_status,
           })
    messages.success(
        request,
        f'Reservation status changed to {reservation.get_status_display()}.',
    )
    return redirect('inventory:reservation_detail', pk=reservation.pk)
