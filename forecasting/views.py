import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import tenant_admin_required, emit_audit

from catalog.models import Product, Category
from warehousing.models import Warehouse
from inventory.models import StockLevel
from orders.models import SalesOrderItem
from .models import (
    DemandForecast, DemandForecastLine,
    ReorderPoint, ReorderAlert,
    SafetyStock,
    SeasonalityProfile, SeasonalityPeriod,
)
from .forms import (
    DemandForecastForm,
    ReorderPointForm, ReorderAlertAcknowledgeForm,
    SafetyStockForm,
    SeasonalityProfileForm, SeasonalityPeriodFormSet,
    GenerateForecastForm,
)


# ══════════════════════════════════════════════
# Helpers — period math and forecast calculations
# ══════════════════════════════════════════════

def _period_bounds(reference_date, period_index, period_type):
    """Return (start_date, end_date, label) for a given period offset from reference_date."""
    if period_type == 'weekly':
        start = reference_date - timedelta(days=reference_date.weekday())
        start = start + timedelta(weeks=period_index)
        end = start + timedelta(days=6)
        iso_year, iso_week, _ = start.isocalendar()
        label = f"W{iso_week:02d}-{iso_year}"
        return start, end, label

    if period_type == 'quarterly':
        q = (reference_date.month - 1) // 3
        base_year = reference_date.year
        target_q = q + period_index
        year_offset, target_q = divmod(target_q, 4)
        year = base_year + year_offset
        start_month = target_q * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        end_day = calendar.monthrange(year, end_month)[1]
        end = date(year, end_month, end_day)
        label = f"Q{target_q + 1} {year}"
        return start, end, label

    # monthly (default)
    base_year = reference_date.year
    base_month = reference_date.month
    total_months = base_month - 1 + period_index
    year_offset, month_idx = divmod(total_months, 12)
    year = base_year + year_offset
    month = month_idx + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    label = start.strftime('%b %Y')
    return start, end, label


def _historical_demand_for(product, warehouse, start, end):
    agg = SalesOrderItem.objects.filter(
        tenant=product.tenant,
        product=product,
        sales_order__warehouse=warehouse,
        sales_order__order_date__gte=start,
        sales_order__order_date__lte=end,
    ).aggregate(total=Sum('quantity'))
    return int(agg['total'] or 0)


def _generate_forecast_values(history, method):
    """Return list of forecast_qty for future periods using the selected method.
    `history` is a list of ints (oldest→newest). Produces len(history) values if passed,
    but caller decides how many to use — we return a function-like object.
    """
    def moving_avg(n_future, window=None):
        if not history:
            return [0] * n_future
        w = window or max(3, len(history) // 2)
        w = min(w, len(history))
        out = []
        series = list(history)
        for _ in range(n_future):
            avg = sum(series[-w:]) / w
            out.append(int(round(avg)))
            series.append(out[-1])
        return out

    def exp_smoothing(n_future, alpha=0.3):
        if not history:
            return [0] * n_future
        f = history[0]
        for a in history[1:]:
            f = alpha * a + (1 - alpha) * f
        return [int(round(f))] * n_future

    def linear_regression(n_future):
        n = len(history)
        if n < 2:
            return [history[-1] if history else 0] * n_future
        xs = list(range(n))
        ys = list(history)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        den = sum((xs[i] - mean_x) ** 2 for i in range(n))
        slope = num / den if den else 0
        intercept = mean_y - slope * mean_x
        out = []
        for k in range(1, n_future + 1):
            val = intercept + slope * (n - 1 + k)
            out.append(max(0, int(round(val))))
        return out

    return {
        'moving_avg': moving_avg,
        'exp_smoothing': exp_smoothing,
        'linear_regression': linear_regression,
        'seasonal': moving_avg,  # base for seasonal — multiplier applied separately
    }.get(method, moving_avg)


# ══════════════════════════════════════════════
# Demand Forecast CRUD
# ══════════════════════════════════════════════

@login_required
def forecast_list_view(request):
    tenant = request.tenant
    queryset = DemandForecast.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(forecast_number__icontains=q) | Q(name__icontains=q) | Q(product__name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    method = request.GET.get('method', '')
    if method:
        queryset = queryset.filter(method=method)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    forecasts = paginator.get_page(request.GET.get('page'))

    return render(request, 'forecasting/forecast_list.html', {
        'forecasts': forecasts,
        'q': q,
        'status_choices': DemandForecast.STATUS_CHOICES,
        'method_choices': DemandForecast.METHOD_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_method': method,
        'current_warehouse': warehouse_id,
    })


@login_required
@tenant_admin_required
def forecast_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = DemandForecastForm(request.POST, tenant=tenant)
        if form.is_valid():
            forecast = form.save(commit=False)
            forecast.tenant = tenant
            forecast.created_by = request.user
            forecast.save()
            emit_audit(request, 'create', forecast)
            messages.success(request, f'Forecast "{forecast.forecast_number}" created. Generate lines to populate data.')
            return redirect('forecasting:forecast_detail', pk=forecast.pk)
    else:
        form = DemandForecastForm(tenant=tenant)
    return render(request, 'forecasting/forecast_form.html', {'form': form, 'title': 'Create Demand Forecast'})


@login_required
@tenant_admin_required
def forecast_edit_view(request, pk):
    tenant = request.tenant
    forecast = get_object_or_404(DemandForecast, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = DemandForecastForm(request.POST, instance=forecast, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', forecast)
            messages.success(request, f'Forecast "{forecast.forecast_number}" updated.')
            return redirect('forecasting:forecast_detail', pk=forecast.pk)
    else:
        form = DemandForecastForm(instance=forecast, tenant=tenant)
    return render(request, 'forecasting/forecast_form.html', {
        'form': form, 'forecast': forecast, 'title': f'Edit {forecast.forecast_number}',
    })


@login_required
def forecast_detail_view(request, pk):
    tenant = request.tenant
    forecast = get_object_or_404(
        DemandForecast.objects.select_related('product', 'warehouse', 'seasonality_profile', 'created_by'),
        pk=pk, tenant=tenant,
    )
    lines = forecast.lines.all()
    history_lines = [l for l in lines if l.period_index < 0]
    future_lines = [l for l in lines if l.period_index >= 0]
    return render(request, 'forecasting/forecast_detail.html', {
        'forecast': forecast,
        'history_lines': history_lines,
        'future_lines': future_lines,
    })


@login_required
@tenant_admin_required
def forecast_delete_view(request, pk):
    tenant = request.tenant
    forecast = get_object_or_404(DemandForecast, pk=pk, tenant=tenant)
    if request.method == 'POST':
        # D-17: block deletion of approved forecasts; only drafts/archived may be removed.
        if forecast.status == 'approved':
            messages.error(request, 'Approved forecasts cannot be deleted. Archive first.')
            return redirect('forecasting:forecast_detail', pk=pk)
        num = forecast.forecast_number
        emit_audit(request, 'delete', forecast)
        forecast.delete()
        messages.success(request, f'Forecast "{num}" deleted.')
        return redirect('forecasting:forecast_list')
    return redirect('forecasting:forecast_list')


@login_required
@tenant_admin_required
def forecast_generate_view(request, pk):
    """Pull historical demand from sales orders and compute future projections."""
    tenant = request.tenant
    forecast = get_object_or_404(DemandForecast, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = GenerateForecastForm(request.POST)
        if form.is_valid():
            # D-09 — wrap the entire regenerate + create cycle atomically.
            with transaction.atomic():
                if form.cleaned_data.get('regenerate'):
                    forecast.lines.all().delete()

                today = timezone.now().date()
                history = []
                for i in range(forecast.history_periods, 0, -1):
                    period_index = -i
                    start, end, label = _period_bounds(today, period_index, forecast.period_type)
                    qty = _historical_demand_for(forecast.product, forecast.warehouse, start, end)
                    history.append(qty)
                    DemandForecastLine.objects.create(
                        tenant=tenant,
                        forecast=forecast,
                        period_index=period_index,
                        period_label=label,
                        period_start_date=start,
                        period_end_date=end,
                        historical_qty=qty,
                    )

                generator = _generate_forecast_values(history, forecast.method)
                future_values = generator(forecast.forecast_periods)

                profile = forecast.seasonality_profile
                for k, val in enumerate(future_values, start=1):
                    period_index = k - 1
                    start, end, label = _period_bounds(today, k, forecast.period_type)
                    adjusted = val
                    # D-16 — single branch: apply multiplier whenever a profile is attached.
                    if profile:
                        mult = float(profile.multiplier_for_date(start))
                        adjusted = int(round(val * mult))

                    DemandForecastLine.objects.create(
                        tenant=tenant,
                        forecast=forecast,
                        period_index=period_index,
                        period_label=label,
                        period_start_date=start,
                        period_end_date=end,
                        forecast_qty=val,
                        adjusted_qty=adjusted,
                    )

                forecast.generated_at = timezone.now()
                forecast.save()
                emit_audit(request, 'generate', forecast,
                           changes=f'{forecast.history_periods}h/{forecast.forecast_periods}f')
            messages.success(request, f'Forecast "{forecast.forecast_number}" generated with {forecast.history_periods} history + {forecast.forecast_periods} future periods.')
            return redirect('forecasting:forecast_detail', pk=forecast.pk)
    else:
        form = GenerateForecastForm()

    return render(request, 'forecasting/forecast_generate.html', {
        'form': form, 'forecast': forecast,
    })


# ══════════════════════════════════════════════
# Reorder Point CRUD
# ══════════════════════════════════════════════

@login_required
def rop_list_view(request):
    tenant = request.tenant
    queryset = ReorderPoint.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(notes__icontains=q)
        )

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    active = request.GET.get('active', '')
    if active == 'active':
        queryset = queryset.filter(is_active=True)
    elif active == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    rops = paginator.get_page(request.GET.get('page'))

    return render(request, 'forecasting/rop_list.html', {
        'rops': rops,
        'q': q,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_warehouse': warehouse_id,
        'current_active': active,
    })


@login_required
@tenant_admin_required
def rop_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = ReorderPointForm(request.POST, tenant=tenant)
        if form.is_valid():
            rop = form.save(commit=False)
            rop.tenant = tenant
            rop.last_calculated_at = timezone.now()
            rop.save()
            emit_audit(request, 'create', rop)
            messages.success(request, f'Reorder point saved (ROP = {rop.rop_qty}).')
            return redirect('forecasting:rop_detail', pk=rop.pk)
    else:
        form = ReorderPointForm(tenant=tenant)
    return render(request, 'forecasting/rop_form.html', {'form': form, 'title': 'Create Reorder Point'})


@login_required
@tenant_admin_required
def rop_edit_view(request, pk):
    tenant = request.tenant
    rop = get_object_or_404(ReorderPoint, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = ReorderPointForm(request.POST, instance=rop, tenant=tenant)
        if form.is_valid():
            rop = form.save(commit=False)
            rop.last_calculated_at = timezone.now()
            rop.save()
            emit_audit(request, 'update', rop)
            messages.success(request, f'Reorder point updated (ROP = {rop.rop_qty}).')
            return redirect('forecasting:rop_detail', pk=rop.pk)
    else:
        form = ReorderPointForm(instance=rop, tenant=tenant)
    return render(request, 'forecasting/rop_form.html', {
        'form': form, 'rop': rop, 'title': f'Edit ROP — {rop.product.name}',
    })


@login_required
def rop_detail_view(request, pk):
    tenant = request.tenant
    rop = get_object_or_404(
        ReorderPoint.objects.select_related('product', 'warehouse'),
        pk=pk, tenant=tenant,
    )
    current_stock = StockLevel.objects.filter(
        tenant=tenant, product=rop.product, warehouse=rop.warehouse,
    ).first()
    recent_alerts = rop.alerts.order_by('-triggered_at')[:10]
    return render(request, 'forecasting/rop_detail.html', {
        'rop': rop,
        'current_stock': current_stock,
        'recent_alerts': recent_alerts,
    })


@login_required
@tenant_admin_required
def rop_delete_view(request, pk):
    tenant = request.tenant
    rop = get_object_or_404(ReorderPoint, pk=pk, tenant=tenant)
    if request.method == 'POST':
        emit_audit(request, 'delete', rop)
        rop.delete()
        messages.success(request, 'Reorder point deleted.')
        return redirect('forecasting:rop_list')
    return redirect('forecasting:rop_list')


@login_required
@tenant_admin_required
@require_POST
def rop_check_alerts_view(request):
    """Scan all active ROPs, compare against StockLevel, create new alerts where needed."""
    tenant = request.tenant
    created = 0
    skipped = 0
    for rop in ReorderPoint.objects.filter(tenant=tenant, is_active=True).select_related('product', 'warehouse'):
        stock = StockLevel.objects.filter(
            tenant=tenant, product=rop.product, warehouse=rop.warehouse,
        ).first()
        current_qty = 0
        if stock:
            current_qty = (stock.on_hand or 0) - (stock.allocated or 0)

        if current_qty > rop.rop_qty:
            continue

        open_exists = ReorderAlert.objects.filter(
            tenant=tenant, rop=rop, status__in=['new', 'acknowledged', 'ordered'],
        ).exists()
        if open_exists:
            skipped += 1
            continue

        # D-15 — clamp max_qty delta at 0 to prevent negative-current over-orders.
        if rop.max_qty:
            suggested = max(rop.reorder_qty, max(0, rop.max_qty - current_qty))
        else:
            suggested = rop.reorder_qty
        ReorderAlert.objects.create(
            tenant=tenant,
            rop=rop,
            product=rop.product,
            warehouse=rop.warehouse,
            current_qty=current_qty,
            rop_qty=rop.rop_qty,
            suggested_order_qty=max(suggested, 0),
        )
        created += 1

    messages.success(request, f'ROP scan complete — {created} alert(s) created, {skipped} open alert(s) skipped.')
    return redirect('forecasting:alert_list')


# ══════════════════════════════════════════════
# Reorder Alert views
# ══════════════════════════════════════════════

@login_required
def alert_list_view(request):
    tenant = request.tenant
    queryset = ReorderAlert.objects.filter(tenant=tenant).select_related('product', 'warehouse', 'rop')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(alert_number__icontains=q) | Q(product__name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    alerts = paginator.get_page(request.GET.get('page'))

    return render(request, 'forecasting/alert_list.html', {
        'alerts': alerts,
        'q': q,
        'status_choices': ReorderAlert.STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_warehouse': warehouse_id,
    })


@login_required
def alert_detail_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(
        ReorderAlert.objects.select_related('product', 'warehouse', 'rop', 'acknowledged_by'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'forecasting/alert_detail.html', {'alert': alert})


@login_required
@tenant_admin_required
def alert_acknowledge_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(ReorderAlert, pk=pk, tenant=tenant)
    if not alert.can_transition_to('acknowledged'):
        messages.error(request, 'Alert cannot be acknowledged in its current status.')
        return redirect('forecasting:alert_detail', pk=pk)

    if request.method == 'POST':
        form = ReorderAlertAcknowledgeForm(request.POST, instance=alert)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.status = 'acknowledged'
            alert.acknowledged_by = request.user
            alert.acknowledged_at = timezone.now()
            alert.save()
            emit_audit(request, 'acknowledge', alert)
            messages.success(request, f'Alert "{alert.alert_number}" acknowledged.')
            return redirect('forecasting:alert_detail', pk=pk)
    else:
        form = ReorderAlertAcknowledgeForm(instance=alert)
    return render(request, 'forecasting/alert_acknowledge_form.html', {
        'form': form, 'alert': alert,
    })


@login_required
@tenant_admin_required
@require_POST
def alert_mark_ordered_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(ReorderAlert, pk=pk, tenant=tenant)
    if alert.can_transition_to('ordered'):
        alert.status = 'ordered'
        alert.save()
        emit_audit(request, 'mark_ordered', alert)
        messages.success(request, f'Alert "{alert.alert_number}" marked as ordered.')
    else:
        messages.error(request, 'Cannot mark alert as ordered.')
    return redirect('forecasting:alert_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def alert_close_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(ReorderAlert, pk=pk, tenant=tenant)
    if alert.can_transition_to('closed'):
        alert.status = 'closed'
        alert.closed_at = timezone.now()
        alert.save()
        emit_audit(request, 'close', alert)
        messages.success(request, f'Alert "{alert.alert_number}" closed.')
    else:
        messages.error(request, 'Cannot close alert.')
    return redirect('forecasting:alert_detail', pk=pk)


@login_required
@tenant_admin_required
def alert_delete_view(request, pk):
    tenant = request.tenant
    alert = get_object_or_404(ReorderAlert, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = alert.alert_number
        emit_audit(request, 'delete', alert)
        alert.delete()
        messages.success(request, f'Alert "{num}" deleted.')
        return redirect('forecasting:alert_list')
    return redirect('forecasting:alert_list')


# ══════════════════════════════════════════════
# Safety Stock CRUD
# ══════════════════════════════════════════════

@login_required
def safety_stock_list_view(request):
    tenant = request.tenant
    queryset = SafetyStock.objects.filter(tenant=tenant).select_related('product', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q)
        )

    method = request.GET.get('method', '')
    if method:
        queryset = queryset.filter(method=method)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    items = paginator.get_page(request.GET.get('page'))

    return render(request, 'forecasting/safety_stock_list.html', {
        'items': items,
        'q': q,
        'method_choices': SafetyStock.METHOD_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_method': method,
        'current_warehouse': warehouse_id,
    })


@login_required
@tenant_admin_required
def safety_stock_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = SafetyStockForm(request.POST, tenant=tenant)
        if form.is_valid():
            ss = form.save()
            emit_audit(request, 'create', ss)
            messages.success(request, f'Safety stock saved ({ss.safety_stock_qty} units).')
            return redirect('forecasting:safety_stock_detail', pk=ss.pk)
    else:
        form = SafetyStockForm(tenant=tenant)
    return render(request, 'forecasting/safety_stock_form.html', {'form': form, 'title': 'Create Safety Stock'})


@login_required
@tenant_admin_required
def safety_stock_edit_view(request, pk):
    tenant = request.tenant
    ss = get_object_or_404(SafetyStock, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = SafetyStockForm(request.POST, instance=ss, tenant=tenant)
        if form.is_valid():
            ss = form.save()
            emit_audit(request, 'update', ss)
            messages.success(request, f'Safety stock updated ({ss.safety_stock_qty} units).')
            return redirect('forecasting:safety_stock_detail', pk=ss.pk)
    else:
        form = SafetyStockForm(instance=ss, tenant=tenant)
    return render(request, 'forecasting/safety_stock_form.html', {
        'form': form, 'safety_stock': ss, 'title': f'Edit Safety Stock — {ss.product.name}',
    })


@login_required
def safety_stock_detail_view(request, pk):
    tenant = request.tenant
    ss = get_object_or_404(
        SafetyStock.objects.select_related('product', 'warehouse'),
        pk=pk, tenant=tenant,
    )
    rop = ReorderPoint.objects.filter(
        tenant=tenant, product=ss.product, warehouse=ss.warehouse,
    ).first()
    return render(request, 'forecasting/safety_stock_detail.html', {
        'safety_stock': ss,
        'rop': rop,
    })


@login_required
@tenant_admin_required
def safety_stock_delete_view(request, pk):
    tenant = request.tenant
    ss = get_object_or_404(SafetyStock, pk=pk, tenant=tenant)
    if request.method == 'POST':
        emit_audit(request, 'delete', ss)
        ss.delete()
        messages.success(request, 'Safety stock record deleted.')
        return redirect('forecasting:safety_stock_list')
    return redirect('forecasting:safety_stock_list')


@login_required
@tenant_admin_required
@require_POST
def safety_stock_recalc_view(request, pk):
    tenant = request.tenant
    ss = get_object_or_404(SafetyStock, pk=pk, tenant=tenant)
    ss.recalc()
    ss.calculated_at = timezone.now()
    ss.save()
    emit_audit(request, 'recalc', ss)
    messages.success(request, f'Safety stock recalculated — now {ss.safety_stock_qty} units.')
    return redirect('forecasting:safety_stock_detail', pk=pk)


# ══════════════════════════════════════════════
# Seasonality Profile CRUD
# ══════════════════════════════════════════════

def _default_period_labels(period_type):
    if period_type == 'quarter':
        return [(i, f'Q{i}') for i in range(1, 5)]
    return [(i, date(2000, i, 1).strftime('%b')) for i in range(1, 13)]


@login_required
def profile_list_view(request):
    tenant = request.tenant
    queryset = SeasonalityProfile.objects.filter(tenant=tenant).select_related('category', 'product')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(description__icontains=q))

    period_type = request.GET.get('period_type', '')
    if period_type:
        queryset = queryset.filter(period_type=period_type)

    active = request.GET.get('active', '')
    if active == 'active':
        queryset = queryset.filter(is_active=True)
    elif active == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    profiles = paginator.get_page(request.GET.get('page'))

    return render(request, 'forecasting/profile_list.html', {
        'profiles': profiles,
        'q': q,
        'period_type_choices': SeasonalityProfile.PERIOD_TYPE_CHOICES,
        'current_period_type': period_type,
        'current_active': active,
    })


@login_required
@tenant_admin_required
def profile_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = SeasonalityProfileForm(request.POST, tenant=tenant)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.tenant = tenant
            profile.created_by = request.user
            profile.save()

            for num, label in _default_period_labels(profile.period_type):
                SeasonalityPeriod.objects.create(
                    tenant=tenant,
                    profile=profile,
                    period_number=num,
                    period_label=label,
                    demand_multiplier=Decimal('1.00'),
                )
            emit_audit(request, 'create', profile)
            messages.success(request, f'Seasonality profile "{profile.name}" created. Edit multipliers below.')
            return redirect('forecasting:profile_detail', pk=profile.pk)
    else:
        form = SeasonalityProfileForm(tenant=tenant)
    return render(request, 'forecasting/profile_form.html', {
        'form': form, 'title': 'Create Seasonality Profile', 'is_create': True,
    })


@login_required
@tenant_admin_required
def profile_edit_view(request, pk):
    tenant = request.tenant
    profile = get_object_or_404(SeasonalityProfile, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = SeasonalityProfileForm(request.POST, instance=profile, tenant=tenant)
        formset = SeasonalityPeriodFormSet(request.POST, instance=profile, prefix='periods')
        if form.is_valid() and formset.is_valid():
            profile = form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            emit_audit(request, 'update', profile)
            messages.success(request, f'Seasonality profile "{profile.name}" updated.')
            return redirect('forecasting:profile_detail', pk=profile.pk)
    else:
        form = SeasonalityProfileForm(instance=profile, tenant=tenant)
        formset = SeasonalityPeriodFormSet(instance=profile, prefix='periods')
    return render(request, 'forecasting/profile_form.html', {
        'form': form, 'formset': formset, 'profile': profile,
        'title': f'Edit {profile.name}', 'is_create': False,
    })


@login_required
def profile_detail_view(request, pk):
    tenant = request.tenant
    profile = get_object_or_404(
        SeasonalityProfile.objects.select_related('category', 'product', 'created_by'),
        pk=pk, tenant=tenant,
    )
    periods = profile.periods.all()
    return render(request, 'forecasting/profile_detail.html', {
        'profile': profile,
        'periods': periods,
    })


@login_required
@tenant_admin_required
def profile_delete_view(request, pk):
    tenant = request.tenant
    profile = get_object_or_404(SeasonalityProfile, pk=pk, tenant=tenant)
    if request.method == 'POST':
        name = profile.name
        emit_audit(request, 'delete', profile)
        profile.delete()
        messages.success(request, f'Profile "{name}" deleted.')
        return redirect('forecasting:profile_list')
    return redirect('forecasting:profile_list')
