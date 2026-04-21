"""Compute services for the 21 report snapshots.

Each function is a pure compute — given `tenant` and report params, produce:

    {
        'summary': {...KPI cards...},
        'data': {
            'columns': [...],   # table headers (optional override of csv_columns)
            'rows': [...],      # list of row dicts
            'chart': {          # optional Chart.js config
                'type': 'bar',
                'labels': [...],
                'datasets': [...],
            },
        },
    }

JSON-serializable primitives only: Decimal→str, dates→ISO.
Services are unit-testable without HTTP; views, seed, and exporters all consume
the same dict shape.
"""
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _d(value):
    """Coerce to Decimal; returns Decimal('0') for None / empty."""
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def _s(value):
    """String-ify for JSON (Decimal → str, date → ISO)."""
    if value is None:
        return ''
    if isinstance(value, (Decimal, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _pct(part, whole):
    """Return part/whole as a Decimal percentage, safe for zero."""
    if not whole:
        return Decimal('0')
    return (_d(part) / _d(whole)) * Decimal('100')


def _empty_report(message='No data available.'):
    return {
        'summary': {'message': message},
        'data': {'columns': [], 'rows': [], 'chart': None},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Section 1: Inventory & Stock
# ═══════════════════════════════════════════════════════════════════════════

def compute_valuation(tenant, *, as_of_date=None, warehouse=None, category=None, **_):
    from inventory.models import StockLevel, InventoryValuation
    from catalog.models import Product

    as_of_date = as_of_date or date.today()
    qs = StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse', 'product__category')
    if warehouse:
        qs = qs.filter(warehouse=warehouse)
    if category:
        qs = qs.filter(product__category=category)

    # Build latest-valuation lookup per (product_id, warehouse_id)
    valuations = InventoryValuation.objects.filter(tenant=tenant).order_by('-valuation_date')
    latest_cost = {}
    for v in valuations:
        key = (v.product_id, v.warehouse_id)
        if key not in latest_cost:
            latest_cost[key] = v.unit_cost

    rows = []
    total_value = Decimal('0')
    total_units = Decimal('0')
    for sl in qs:
        unit_cost = latest_cost.get((sl.product_id, sl.warehouse_id))
        if unit_cost is None:
            unit_cost = sl.product.cost_price if hasattr(sl.product, 'cost_price') else getattr(sl.product, 'cost', None)
        unit_cost = _d(unit_cost)
        on_hand = _d(sl.on_hand)
        row_value = on_hand * unit_cost
        total_value += row_value
        total_units += on_hand
        rows.append({
            'sku': sl.product.sku,
            'product_name': sl.product.name,
            'warehouse_name': sl.warehouse.name if sl.warehouse else '',
            'category': sl.product.category.name if sl.product.category_id else '',
            'on_hand': _s(on_hand),
            'unit_cost': _s(unit_cost),
            'total_value': _s(row_value),
        })

    rows.sort(key=lambda r: _d(r['total_value']), reverse=True)

    # Chart: top 10 products by value
    top10 = rows[:10]
    chart = {
        'type': 'bar',
        'labels': [r['product_name'] for r in top10],
        'datasets': [{'label': 'Total Value', 'data': [float(_d(r['total_value'])) for r in top10]}],
    }

    summary = {
        'as_of_date': _s(as_of_date),
        'total_value': _s(total_value),
        'total_units': _s(total_units),
        'total_skus': len(rows),
        'avg_unit_cost': _s(total_value / total_units) if total_units else '0',
    }
    return {
        'summary': summary,
        'data': {'columns': ['sku', 'product_name', 'warehouse_name', 'on_hand', 'unit_cost', 'total_value'], 'rows': rows, 'chart': chart},
    }


def compute_aging(tenant, *, as_of_date=None, warehouse=None, category=None, dead_stock_days=180, **_):
    from inventory.models import StockLevel, StockAdjustment
    from stock_movements.models import StockTransferItem
    from orders.models import SalesOrderItem

    as_of_date = as_of_date or date.today()
    qs = StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse')
    if warehouse:
        qs = qs.filter(warehouse=warehouse)
    if category:
        qs = qs.filter(product__category=category)

    # Last-movement date per (product_id, warehouse_id)
    last_movement = {}

    adj_qs = StockAdjustment.objects.filter(tenant=tenant).select_related('stock_level').order_by('-created_at')
    for adj in adj_qs[:10000]:
        key = (adj.stock_level.product_id, adj.stock_level.warehouse_id)
        if key not in last_movement:
            last_movement[key] = adj.created_at.date() if adj.created_at else None

    try:
        ti_qs = StockTransferItem.objects.filter(tenant=tenant).select_related('transfer').order_by('-transfer__created_at')
        for ti in ti_qs[:10000]:
            src_key = (ti.product_id, ti.transfer.source_warehouse_id) if hasattr(ti.transfer, 'source_warehouse_id') else None
            dst_key = (ti.product_id, ti.transfer.destination_warehouse_id) if hasattr(ti.transfer, 'destination_warehouse_id') else None
            for key in (src_key, dst_key):
                if key and key not in last_movement and ti.transfer.created_at:
                    last_movement[key] = ti.transfer.created_at.date()
    except Exception:
        pass

    try:
        soi_qs = (SalesOrderItem.objects.filter(tenant=tenant, sales_order__status__in=['delivered', 'closed'])
                  .select_related('sales_order').order_by('-sales_order__created_at'))
        for soi in soi_qs[:10000]:
            key = (soi.product_id, getattr(soi.sales_order, 'warehouse_id', None))
            if key[1] is not None and key not in last_movement:
                last_movement[key] = soi.sales_order.created_at.date() if soi.sales_order.created_at else None
    except Exception:
        pass

    buckets = OrderedDict([('0-30', 0), ('31-60', 0), ('61-90', 0), ('91-180', 0), ('180+', 0)])
    bucket_values = OrderedDict([(k, Decimal('0')) for k in buckets])
    rows = []
    for sl in qs:
        last = last_movement.get((sl.product_id, sl.warehouse_id))
        if last:
            days_since = (as_of_date - last).days
        else:
            days_since = 9999
        if days_since <= 30:
            bucket = '0-30'
        elif days_since <= 60:
            bucket = '31-60'
        elif days_since <= 90:
            bucket = '61-90'
        elif days_since <= 180:
            bucket = '91-180'
        else:
            bucket = '180+'
        unit_cost = _d(getattr(sl.product, 'cost_price', None) or getattr(sl.product, 'cost', 0))
        value = _d(sl.on_hand) * unit_cost
        buckets[bucket] += 1
        bucket_values[bucket] += value
        rows.append({
            'sku': sl.product.sku,
            'product_name': sl.product.name,
            'warehouse_name': sl.warehouse.name if sl.warehouse else '',
            'on_hand': _s(sl.on_hand),
            'last_movement': _s(last) if last else 'Never',
            'days_since': days_since if days_since < 9999 else 'N/A',
            'bucket': bucket,
            'value': _s(value),
        })

    rows.sort(key=lambda r: r['days_since'] if isinstance(r['days_since'], int) else -1, reverse=True)

    chart = {
        'type': 'bar',
        'labels': list(buckets.keys()),
        'datasets': [
            {'label': 'SKU Count', 'data': list(buckets.values())},
            {'label': 'Value', 'data': [float(v) for v in bucket_values.values()]},
        ],
    }
    summary = {
        'as_of_date': _s(as_of_date),
        'dead_stock_days': dead_stock_days,
        'dead_stock_skus': buckets['180+'],
        'dead_stock_value': _s(bucket_values['180+']),
        'slow_moving_skus': buckets['91-180'],
        'slow_moving_value': _s(bucket_values['91-180']),
        'bucket_counts': {k: v for k, v in buckets.items()},
        'bucket_values': {k: _s(v) for k, v in bucket_values.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['sku', 'product_name', 'warehouse_name', 'on_hand', 'last_movement', 'days_since', 'bucket', 'value'], 'rows': rows, 'chart': chart},
    }


def compute_abc(tenant, *, period_start=None, period_end=None, warehouse=None, category=None, a_threshold=80, b_threshold=15, **_):
    from orders.models import SalesOrderItem

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=365))

    qs = (SalesOrderItem.objects.filter(
        tenant=tenant,
        sales_order__status__in=['delivered', 'closed'],
        sales_order__created_at__date__gte=period_start,
        sales_order__created_at__date__lte=period_end,
    ).select_related('product', 'product__category'))
    if category:
        qs = qs.filter(product__category=category)

    # Aggregate annual value per product
    agg = defaultdict(lambda: {'qty': Decimal('0'), 'value': Decimal('0'), 'name': '', 'sku': ''})
    for soi in qs:
        key = soi.product_id
        unit_cost = _d(getattr(soi.product, 'cost_price', None) or getattr(soi.product, 'cost', 0))
        qty = _d(soi.quantity)
        agg[key]['qty'] += qty
        agg[key]['value'] += qty * unit_cost
        agg[key]['name'] = soi.product.name
        agg[key]['sku'] = soi.product.sku
        agg[key]['unit_cost'] = unit_cost

    rows = sorted(
        [{'product_id': pid, **meta} for pid, meta in agg.items()],
        key=lambda r: r['value'], reverse=True,
    )
    total_value = sum((r['value'] for r in rows), Decimal('0'))

    a_cut = _d(a_threshold)
    ab_cut = _d(a_threshold) + _d(b_threshold)

    cum = Decimal('0')
    a_count = b_count = c_count = 0
    a_value = b_value = c_value = Decimal('0')
    output_rows = []
    for rank, r in enumerate(rows, 1):
        cum += r['value']
        cum_pct = _pct(cum, total_value) if total_value else Decimal('0')
        if cum_pct <= a_cut:
            abc_class = 'A'
            a_count += 1
            a_value += r['value']
        elif cum_pct <= ab_cut:
            abc_class = 'B'
            b_count += 1
            b_value += r['value']
        else:
            abc_class = 'C'
            c_count += 1
            c_value += r['value']
        output_rows.append({
            'rank': rank,
            'sku': r['sku'],
            'product_name': r['name'],
            'annual_qty': _s(r['qty']),
            'unit_cost': _s(r['unit_cost']),
            'annual_value': _s(r['value']),
            'cum_pct': _s(cum_pct.quantize(Decimal('0.01'))),
            'abc_class': abc_class,
        })

    chart = {
        'type': 'doughnut',
        'labels': ['A', 'B', 'C'],
        'datasets': [{
            'label': 'Value',
            'data': [float(a_value), float(b_value), float(c_value)],
        }],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_value': _s(total_value),
        'a_count': a_count, 'b_count': b_count, 'c_count': c_count,
        'a_value': _s(a_value), 'b_value': _s(b_value), 'c_value': _s(c_value),
        'a_threshold': int(_d(a_threshold)), 'b_threshold': int(_d(b_threshold)),
    }
    return {
        'summary': summary,
        'data': {'columns': ['rank', 'sku', 'product_name', 'annual_qty', 'unit_cost', 'annual_value', 'cum_pct', 'abc_class'], 'rows': output_rows, 'chart': chart},
    }


def compute_turnover(tenant, *, period_start=None, period_end=None, warehouse=None, category=None, **_):
    from inventory.models import StockLevel
    from orders.models import SalesOrderItem

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=365))

    soi_qs = (SalesOrderItem.objects.filter(
        tenant=tenant,
        sales_order__status__in=['delivered', 'closed'],
        sales_order__created_at__date__gte=period_start,
        sales_order__created_at__date__lte=period_end,
    ).select_related('product'))
    if category:
        soi_qs = soi_qs.filter(product__category=category)

    per_product = defaultdict(lambda: {'cogs': Decimal('0'), 'qty': Decimal('0'), 'name': '', 'sku': ''})
    total_cogs = Decimal('0')
    for soi in soi_qs:
        unit_cost = _d(getattr(soi.product, 'cost_price', None) or getattr(soi.product, 'cost', 0))
        qty = _d(soi.quantity)
        per_product[soi.product_id]['cogs'] += qty * unit_cost
        per_product[soi.product_id]['qty'] += qty
        per_product[soi.product_id]['name'] = soi.product.name
        per_product[soi.product_id]['sku'] = soi.product.sku
        per_product[soi.product_id]['unit_cost'] = unit_cost
        total_cogs += qty * unit_cost

    sl_qs = StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse')
    if warehouse:
        sl_qs = sl_qs.filter(warehouse=warehouse)
    if category:
        sl_qs = sl_qs.filter(product__category=category)

    per_product_inventory = defaultdict(lambda: Decimal('0'))
    total_inventory = Decimal('0')
    for sl in sl_qs:
        unit_cost = _d(getattr(sl.product, 'cost_price', None) or getattr(sl.product, 'cost', 0))
        value = _d(sl.on_hand) * unit_cost
        per_product_inventory[sl.product_id] += value
        total_inventory += value

    rows = []
    for pid, meta in per_product.items():
        avg_inv = per_product_inventory.get(pid, Decimal('0'))
        turnover = (meta['cogs'] / avg_inv) if avg_inv else Decimal('0')
        dsi = (Decimal('365') / turnover) if turnover else Decimal('0')
        rows.append({
            'sku': meta['sku'],
            'product_name': meta['name'],
            'cogs': _s(meta['cogs']),
            'avg_inventory': _s(avg_inv),
            'turnover': _s(turnover.quantize(Decimal('0.01'))),
            'dsi': _s(dsi.quantize(Decimal('0.01'))),
        })
    rows.sort(key=lambda r: _d(r['turnover']), reverse=True)

    overall_turnover = (total_cogs / total_inventory) if total_inventory else Decimal('0')
    overall_dsi = (Decimal('365') / overall_turnover) if overall_turnover else Decimal('0')

    top10 = rows[:10]
    chart = {
        'type': 'bar',
        'labels': [r['product_name'] for r in top10],
        'datasets': [{'label': 'Turnover Ratio', 'data': [float(_d(r['turnover'])) for r in top10]}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_cogs': _s(total_cogs),
        'avg_inventory_value': _s(total_inventory),
        'overall_turnover': _s(overall_turnover.quantize(Decimal('0.01'))),
        'overall_dsi_days': _s(overall_dsi.quantize(Decimal('0.01'))),
    }
    return {
        'summary': summary,
        'data': {'columns': ['sku', 'product_name', 'cogs', 'avg_inventory', 'turnover', 'dsi'], 'rows': rows, 'chart': chart},
    }


def compute_reservations(tenant, *, warehouse=None, category=None, status=None, **_):
    try:
        from inventory.models import InventoryReservation
    except ImportError:
        return _empty_report('InventoryReservation model not available.')

    qs = InventoryReservation.objects.filter(tenant=tenant).select_related('product', 'warehouse')
    if warehouse:
        qs = qs.filter(warehouse=warehouse)
    if category:
        qs = qs.filter(product__category=category)
    if status:
        qs = qs.filter(status=status)

    rows = []
    by_status = defaultdict(int)
    by_status_qty = defaultdict(lambda: Decimal('0'))
    total_qty = Decimal('0')
    for r in qs:
        qty = _d(r.quantity)
        total_qty += qty
        by_status[r.status] += 1
        by_status_qty[r.status] += qty
        rows.append({
            'reference': getattr(r, 'reference_number', '') or getattr(r, 'reference', '') or str(r.pk),
            'product_name': r.product.name if r.product_id else '',
            'warehouse_name': r.warehouse.name if r.warehouse_id else '',
            'quantity': _s(qty),
            'status': r.status,
            'reserved_at': _s(getattr(r, 'reserved_at', None) or r.created_at),
        })

    chart = {
        'type': 'pie',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Count', 'data': list(by_status.values())}],
    }
    summary = {
        'total_reservations': len(rows),
        'total_quantity': _s(total_qty),
        'by_status': {k: v for k, v in by_status.items()},
        'by_status_qty': {k: _s(v) for k, v in by_status_qty.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['reference', 'product_name', 'warehouse_name', 'quantity', 'status', 'reserved_at'], 'rows': rows, 'chart': chart},
    }


def compute_multi_location(tenant, *, category=None, **_):
    try:
        from multi_location.models import Location
    except ImportError:
        return _empty_report('Location model not available.')
    from inventory.models import StockLevel

    rows = []
    total_on_hand = Decimal('0')
    total_value = Decimal('0')
    sku_set_global = set()

    for loc in Location.objects.filter(tenant=tenant).select_related('warehouse'):
        wh = getattr(loc, 'warehouse', None)
        if not wh:
            continue
        sl_qs = StockLevel.objects.filter(tenant=tenant, warehouse=wh).select_related('product')
        if category:
            sl_qs = sl_qs.filter(product__category=category)
        loc_on_hand = Decimal('0')
        loc_value = Decimal('0')
        sku_set = set()
        for sl in sl_qs:
            unit_cost = _d(getattr(sl.product, 'cost_price', None) or getattr(sl.product, 'cost', 0))
            loc_on_hand += _d(sl.on_hand)
            loc_value += _d(sl.on_hand) * unit_cost
            sku_set.add(sl.product_id)
            sku_set_global.add(sl.product_id)
        total_on_hand += loc_on_hand
        total_value += loc_value
        rows.append({
            'location_name': loc.name,
            'location_type': getattr(loc, 'location_type', '') or '',
            'warehouse': wh.name,
            'sku_count': len(sku_set),
            'total_on_hand': _s(loc_on_hand),
            'total_value': _s(loc_value),
        })

    rows.sort(key=lambda r: _d(r['total_value']), reverse=True)
    chart = {
        'type': 'bar',
        'labels': [r['location_name'] for r in rows[:10]],
        'datasets': [{'label': 'Total Value', 'data': [float(_d(r['total_value'])) for r in rows[:10]]}],
    }
    summary = {
        'total_locations': len(rows),
        'total_unique_skus': len(sku_set_global),
        'total_on_hand': _s(total_on_hand),
        'total_value': _s(total_value),
    }
    return {
        'summary': summary,
        'data': {'columns': ['location_name', 'location_type', 'warehouse', 'sku_count', 'total_on_hand', 'total_value'], 'rows': rows, 'chart': chart},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Section 2: Procurement
# ═══════════════════════════════════════════════════════════════════════════

def compute_po_summary(tenant, *, period_start=None, period_end=None, vendor=None, status=None, **_):
    from purchase_orders.models import PurchaseOrder

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = PurchaseOrder.objects.filter(
        tenant=tenant,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).select_related('vendor')
    if vendor:
        qs = qs.filter(vendor=vendor)
    if status:
        qs = qs.filter(status=status)

    by_status = defaultdict(int)
    by_status_value = defaultdict(lambda: Decimal('0'))
    total_value = Decimal('0')
    rows = []
    for po in qs.prefetch_related('items'):
        po_total = Decimal('0')
        for it in po.items.all():
            line = _d(it.quantity) * _d(it.unit_price)
            line -= line * (_d(getattr(it, 'discount', 0)) / Decimal('100'))
            line += line * (_d(getattr(it, 'tax_rate', 0)) / Decimal('100'))
            po_total += line
        total_value += po_total
        by_status[po.status] += 1
        by_status_value[po.status] += po_total
        rows.append({
            'po_number': po.po_number,
            'vendor_name': po.vendor.company_name if po.vendor_id else '',
            'status': po.status,
            'order_date': _s(getattr(po, 'order_date', None) or (po.created_at.date() if po.created_at else '')),
            'total_value': _s(po_total),
        })

    rows.sort(key=lambda r: _d(r['total_value']), reverse=True)
    chart = {
        'type': 'bar',
        'labels': list(by_status.keys()),
        'datasets': [
            {'label': 'Count', 'data': list(by_status.values())},
            {'label': 'Value', 'data': [float(v) for v in by_status_value.values()]},
        ],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_pos': len(rows),
        'total_value': _s(total_value),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['po_number', 'vendor_name', 'status', 'order_date', 'total_value'], 'rows': rows, 'chart': chart},
    }


def compute_vendor_performance(tenant, *, period_start=None, period_end=None, **_):
    try:
        from vendors.models import Vendor, VendorPerformance
    except ImportError:
        return _empty_report('Vendor models not available.')
    from purchase_orders.models import PurchaseOrder

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=365))

    rows = []
    for v in Vendor.objects.filter(tenant=tenant):
        pos = PurchaseOrder.objects.filter(
            tenant=tenant, vendor=v,
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        )
        po_count = pos.count()
        closed_count = pos.filter(status__in=['received', 'closed']).count()
        on_time_ratio = (Decimal(closed_count) / Decimal(po_count) * 100) if po_count else Decimal('0')
        review = (VendorPerformance.objects.filter(tenant=tenant, vendor=v)
                  .order_by('-created_at').first())
        quality = _d(getattr(review, 'quality_rating', None)) if review else Decimal('0')
        compliance = _d(getattr(review, 'compliance_rating', None)) if review else Decimal('0')
        delivery = _d(getattr(review, 'delivery_rating', None)) if review else Decimal('0')
        # Overall score = avg of three ratings
        if review:
            overall = ((quality + compliance + delivery) / Decimal('3')).quantize(Decimal('0.01'))
        else:
            overall = Decimal('0')
        rows.append({
            'vendor_name': v.company_name,
            'po_count': po_count,
            'on_time_ratio': _s(on_time_ratio.quantize(Decimal('0.01'))),
            'quality_score': _s(quality),
            'compliance_score': _s(compliance),
            'overall_score': _s(overall),
        })

    rows.sort(key=lambda r: _d(r['overall_score']), reverse=True)
    chart = {
        'type': 'bar',
        'labels': [r['vendor_name'] for r in rows[:10]],
        'datasets': [{'label': 'Overall Score', 'data': [float(_d(r['overall_score'])) for r in rows[:10]]}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_vendors': len(rows),
        'avg_overall_score': _s(
            (sum((_d(r['overall_score']) for r in rows), Decimal('0')) / Decimal(len(rows))).quantize(Decimal('0.01'))
            if rows else Decimal('0')
        ),
    }
    return {
        'summary': summary,
        'data': {'columns': ['vendor_name', 'po_count', 'on_time_ratio', 'quality_score', 'compliance_score', 'overall_score'], 'rows': rows, 'chart': chart},
    }


def compute_three_way_match(tenant, *, period_start=None, period_end=None, status=None, **_):
    try:
        from receiving.models import ThreeWayMatch
    except ImportError:
        return _empty_report('ThreeWayMatch model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = ThreeWayMatch.objects.filter(
        tenant=tenant,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).select_related('purchase_order', 'grn', 'vendor_invoice')
    if status:
        qs = qs.filter(status=status)

    rows = []
    by_status = defaultdict(int)
    total_variance = Decimal('0')
    for m in qs:
        po_total = _d(getattr(m, 'po_total', 0))
        inv_total = _d(getattr(m, 'invoice_total', 0))
        variance = abs(po_total - inv_total)
        total_variance += variance
        by_status[m.status] += 1
        rows.append({
            'match_number': getattr(m, 'match_number', '') or str(m.pk),
            'po_number': m.purchase_order.po_number if getattr(m, 'purchase_order_id', None) else '',
            'grn_number': getattr(m.grn, 'grn_number', '') if getattr(m, 'grn_id', None) else '',
            'invoice_number': getattr(m.vendor_invoice, 'invoice_number', '') if getattr(m, 'vendor_invoice_id', None) else '',
            'status': m.status,
            'variance_total': _s(variance),
        })

    chart = {
        'type': 'doughnut',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Count', 'data': list(by_status.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_matches': len(rows),
        'total_variance': _s(total_variance),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['match_number', 'po_number', 'grn_number', 'invoice_number', 'status', 'variance_total'], 'rows': rows, 'chart': chart},
    }


def compute_receiving_grn(tenant, *, period_start=None, period_end=None, warehouse=None, vendor=None, **_):
    try:
        from receiving.models import GoodsReceiptNote
    except ImportError:
        return _empty_report('GoodsReceiptNote model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    # GRN has no direct vendor/warehouse FK — both resolved via purchase_order
    qs = GoodsReceiptNote.objects.filter(
        tenant=tenant,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).select_related('purchase_order', 'purchase_order__vendor').prefetch_related('items')
    if vendor:
        qs = qs.filter(purchase_order__vendor=vendor)

    rows = []
    total_qty = Decimal('0')
    by_status = defaultdict(int)
    for g in qs:
        qty = sum((_d(getattr(it, 'received_quantity', None) or getattr(it, 'quantity', 0)) for it in g.items.all()), Decimal('0'))
        total_qty += qty
        by_status[g.status] += 1
        po = getattr(g, 'purchase_order', None)
        vendor_name = po.vendor.company_name if po and po.vendor_id else ''
        rows.append({
            'grn_number': g.grn_number,
            'vendor_name': vendor_name,
            'warehouse_name': '',  # no warehouse on GRN/PO in this schema
            'received_date': _s(getattr(g, 'received_date', None) or (g.created_at.date() if g.created_at else '')),
            'total_qty': _s(qty),
            'status': g.status,
        })

    chart = {
        'type': 'bar',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'GRN Count', 'data': list(by_status.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_grns': len(rows),
        'total_qty_received': _s(total_qty),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['grn_number', 'vendor_name', 'warehouse_name', 'received_date', 'total_qty', 'status'], 'rows': rows, 'chart': chart},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Section 3: Warehouse Ops
# ═══════════════════════════════════════════════════════════════════════════

def compute_stock_transfers(tenant, *, period_start=None, period_end=None, status=None, **_):
    from stock_movements.models import StockTransfer

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = StockTransfer.objects.filter(
        tenant=tenant,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).select_related('source_warehouse', 'destination_warehouse').prefetch_related('items')
    if status:
        qs = qs.filter(status=status)

    rows = []
    by_status = defaultdict(int)
    for t in qs:
        by_status[t.status] += 1
        rows.append({
            'transfer_number': getattr(t, 'transfer_number', '') or str(t.pk),
            'source': t.source_warehouse.name if t.source_warehouse_id else '',
            'destination': t.destination_warehouse.name if t.destination_warehouse_id else '',
            'status': t.status,
            'created_at': _s(t.created_at.date() if t.created_at else ''),
            'item_count': t.items.count(),
        })

    chart = {
        'type': 'bar',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Count', 'data': list(by_status.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_transfers': len(rows),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['transfer_number', 'source', 'destination', 'status', 'created_at', 'item_count'], 'rows': rows, 'chart': chart},
    }


def compute_stocktake_variance(tenant, *, period_start=None, period_end=None, warehouse=None, **_):
    try:
        from stocktaking.models import StockCount
    except ImportError:
        return _empty_report('StockCount model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = StockCount.objects.filter(
        tenant=tenant,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).select_related('warehouse').prefetch_related('items')
    if warehouse:
        qs = qs.filter(warehouse=warehouse)

    rows = []
    total_var_qty = Decimal('0')
    total_var_value = Decimal('0')
    for c in qs:
        var_qty = Decimal('0')
        var_value = Decimal('0')
        for it in c.items.all():
            counted = _d(getattr(it, 'counted_qty', None) or getattr(it, 'counted_quantity', 0))
            system = _d(getattr(it, 'system_qty', None) or getattr(it, 'system_quantity', 0))
            diff = counted - system
            var_qty += diff
            product = getattr(it, 'product', None)
            unit_cost = _d(getattr(product, 'cost_price', None) or getattr(product, 'cost', 0)) if product else Decimal('0')
            var_value += diff * unit_cost
        total_var_qty += var_qty
        total_var_value += var_value
        rows.append({
            'count_number': getattr(c, 'count_number', '') or str(c.pk),
            'warehouse_name': c.warehouse.name if c.warehouse_id else '',
            'status': c.status,
            'item_count': c.items.count(),
            'variance_qty': _s(var_qty),
            'variance_value': _s(var_value),
        })

    chart = {
        'type': 'bar',
        'labels': [r['count_number'] for r in rows[:10]],
        'datasets': [{'label': 'Variance Value', 'data': [float(_d(r['variance_value'])) for r in rows[:10]]}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_counts': len(rows),
        'total_variance_qty': _s(total_var_qty),
        'total_variance_value': _s(total_var_value),
    }
    return {
        'summary': summary,
        'data': {'columns': ['count_number', 'warehouse_name', 'status', 'item_count', 'variance_qty', 'variance_value'], 'rows': rows, 'chart': chart},
    }


def compute_quality_control(tenant, *, period_start=None, period_end=None, **_):
    try:
        from quality_control.models import QuarantineRecord, DefectReport
    except ImportError:
        return _empty_report('Quality Control models not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    rows = []
    by_status = defaultdict(int)
    by_severity = defaultdict(int)

    for q in QuarantineRecord.objects.filter(
        tenant=tenant, created_at__date__gte=period_start, created_at__date__lte=period_end,
    ).select_related('product'):
        by_status[q.status] += 1
        rows.append({
            'kind': 'Quarantine',
            'ref_number': q.quarantine_number,
            'product_name': q.product.name if getattr(q, 'product_id', None) else '',
            'severity': getattr(q, 'severity', '') or '',
            'status': q.status,
            'created_at': _s(q.created_at.date() if q.created_at else ''),
        })

    for d in DefectReport.objects.filter(
        tenant=tenant, created_at__date__gte=period_start, created_at__date__lte=period_end,
    ).select_related('product'):
        by_severity[d.severity] += 1
        by_status[d.status] += 1
        rows.append({
            'kind': 'Defect',
            'ref_number': d.defect_number,
            'product_name': d.product.name if getattr(d, 'product_id', None) else '',
            'severity': d.severity,
            'status': d.status,
            'created_at': _s(d.created_at.date() if d.created_at else ''),
        })

    chart = {
        'type': 'doughnut',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Count by Status', 'data': list(by_status.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_records': len(rows),
        'by_status': {k: v for k, v in by_status.items()},
        'by_severity': {k: v for k, v in by_severity.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['kind', 'ref_number', 'product_name', 'severity', 'status', 'created_at'], 'rows': rows, 'chart': chart},
    }


def compute_scrap_writeoff(tenant, *, period_start=None, period_end=None, warehouse=None, **_):
    try:
        from quality_control.models import ScrapWriteOff
    except ImportError:
        return _empty_report('ScrapWriteOff model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = ScrapWriteOff.objects.filter(
        tenant=tenant, created_at__date__gte=period_start, created_at__date__lte=period_end,
    ).select_related('product', 'warehouse')
    if warehouse:
        qs = qs.filter(warehouse=warehouse)

    rows = []
    total_value = Decimal('0')
    by_status = defaultdict(int)
    by_status_value = defaultdict(lambda: Decimal('0'))
    for s in qs:
        qty = _d(s.quantity)
        cost = _d(getattr(s, 'unit_cost', 0))
        value = qty * cost
        total_value += value
        by_status[s.status] += 1
        by_status_value[s.status] += value
        rows.append({
            'scrap_number': s.scrap_number,
            'product_name': s.product.name if getattr(s, 'product_id', None) else '',
            'warehouse_name': s.warehouse.name if getattr(s, 'warehouse_id', None) else '',
            'quantity': _s(qty),
            'unit_cost': _s(cost),
            'total_value': _s(value),
            'status': s.status,
        })

    chart = {
        'type': 'pie',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Value', 'data': [float(v) for v in by_status_value.values()]}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_writeoffs': len(rows),
        'total_value': _s(total_value),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['scrap_number', 'product_name', 'warehouse_name', 'quantity', 'unit_cost', 'total_value', 'status'], 'rows': rows, 'chart': chart},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Section 4: Sales & Fulfillment
# ═══════════════════════════════════════════════════════════════════════════

def compute_so_summary(tenant, *, period_start=None, period_end=None, status=None, **_):
    from orders.models import SalesOrder

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = SalesOrder.objects.filter(
        tenant=tenant, created_at__date__gte=period_start, created_at__date__lte=period_end,
    ).prefetch_related('items')
    if status:
        qs = qs.filter(status=status)

    rows = []
    by_status = defaultdict(int)
    by_status_value = defaultdict(lambda: Decimal('0'))
    total_value = Decimal('0')
    for so in qs:
        so_total = Decimal('0')
        for it in so.items.all():
            line = _d(it.quantity) * _d(getattr(it, 'unit_price', 0))
            line -= line * (_d(getattr(it, 'discount', 0)) / Decimal('100'))
            line += line * (_d(getattr(it, 'tax_rate', 0)) / Decimal('100'))
            so_total += line
        total_value += so_total
        by_status[so.status] += 1
        by_status_value[so.status] += so_total
        rows.append({
            'so_number': getattr(so, 'order_number', '') or str(so.pk),
            'customer': getattr(so, 'customer_name', '') or '',
            'status': so.status,
            'order_date': _s(getattr(so, 'order_date', None) or (so.created_at.date() if so.created_at else '')),
            'total_value': _s(so_total),
        })

    rows.sort(key=lambda r: _d(r['total_value']), reverse=True)
    chart = {
        'type': 'bar',
        'labels': list(by_status.keys()),
        'datasets': [
            {'label': 'Count', 'data': list(by_status.values())},
            {'label': 'Value', 'data': [float(v) for v in by_status_value.values()]},
        ],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_orders': len(rows),
        'total_value': _s(total_value),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['so_number', 'customer', 'status', 'order_date', 'total_value'], 'rows': rows, 'chart': chart},
    }


def compute_fulfillment(tenant, *, period_start=None, period_end=None, **_):
    try:
        from orders.models import SalesOrder, PickList, PackingList, Shipment
    except ImportError:
        return _empty_report('Orders fulfillment models not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    rows = []
    cycle_hours_total = Decimal('0')
    cycle_count = 0
    for so in (SalesOrder.objects.filter(
        tenant=tenant, created_at__date__gte=period_start, created_at__date__lte=period_end,
    ).prefetch_related('pick_lists', 'packing_lists', 'shipments')):
        picked_at = None
        packed_at = None
        shipped_at = None
        try:
            picked_at = next((pl.completed_at for pl in so.pick_lists.all() if pl.status == 'completed'), None)
        except Exception:
            pass
        try:
            packed_at = next((pl.packed_at for pl in so.packing_lists.all() if pl.status == 'completed'), None)
        except Exception:
            pass
        try:
            shipped_at = next((sh.shipped_date for sh in so.shipments.all() if getattr(sh, 'shipped_date', None)), None)
        except Exception:
            pass
        cycle = None
        if picked_at and shipped_at:
            # shipped_date is DateField; picked_at is DateTimeField — coerce both to datetime
            from datetime import datetime as _dt
            picked_dt = picked_at if isinstance(picked_at, _dt) else _dt.combine(picked_at, _dt.min.time())
            shipped_dt = shipped_at if isinstance(shipped_at, _dt) else _dt.combine(shipped_at, _dt.min.time())
            cycle = Decimal((shipped_dt - picked_dt).total_seconds() / 3600).quantize(Decimal('0.01'))
            cycle_hours_total += cycle
            cycle_count += 1
        rows.append({
            'so_number': getattr(so, 'order_number', '') or getattr(so, 'so_number', '') or str(so.pk),
            'picked_at': _s(picked_at),
            'packed_at': _s(packed_at),
            'shipped_at': _s(shipped_at),
            'cycle_hours': _s(cycle) if cycle is not None else '',
        })

    chart = {
        'type': 'line',
        'labels': [r['so_number'] for r in rows[:20]],
        'datasets': [{'label': 'Cycle Hours', 'data': [float(_d(r['cycle_hours'] or 0)) for r in rows[:20]]}],
    }
    avg_cycle = (cycle_hours_total / Decimal(cycle_count)).quantize(Decimal('0.01')) if cycle_count else Decimal('0')
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_orders': len(rows),
        'orders_with_cycle': cycle_count,
        'avg_cycle_hours': _s(avg_cycle),
    }
    return {
        'summary': summary,
        'data': {'columns': ['so_number', 'picked_at', 'packed_at', 'shipped_at', 'cycle_hours'], 'rows': rows, 'chart': chart},
    }


def compute_shipment_carrier(tenant, *, period_start=None, period_end=None, carrier=None, **_):
    try:
        from orders.models import Shipment
    except ImportError:
        return _empty_report('Shipment model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = Shipment.objects.filter(
        tenant=tenant, created_at__date__gte=period_start, created_at__date__lte=period_end,
    ).select_related('carrier')
    if carrier:
        qs = qs.filter(carrier=carrier)

    rows = []
    by_carrier = defaultdict(int)
    by_status = defaultdict(int)
    for sh in qs:
        carrier_name = sh.carrier.name if getattr(sh, 'carrier_id', None) else ''
        by_carrier[carrier_name or 'Unassigned'] += 1
        by_status[sh.status] += 1
        rows.append({
            'shipment_number': getattr(sh, 'shipment_number', '') or str(sh.pk),
            'carrier_name': carrier_name,
            'tracking_number': getattr(sh, 'tracking_number', '') or '',
            'status': sh.status,
            'dispatched_at': _s(getattr(sh, 'shipped_date', None)),
            'delivered_at': _s(getattr(sh, 'actual_delivery_date', None)),
        })

    chart = {
        'type': 'bar',
        'labels': list(by_carrier.keys()),
        'datasets': [{'label': 'Shipments', 'data': list(by_carrier.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_shipments': len(rows),
        'by_carrier': {k: v for k, v in by_carrier.items()},
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['shipment_number', 'carrier_name', 'tracking_number', 'status', 'dispatched_at', 'delivered_at'], 'rows': rows, 'chart': chart},
    }


def compute_returns_rma(tenant, *, period_start=None, period_end=None, status=None, **_):
    try:
        from returns.models import ReturnAuthorization
    except ImportError:
        return _empty_report('ReturnAuthorization model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=90))

    qs = ReturnAuthorization.objects.filter(
        tenant=tenant,
        created_at__date__gte=period_start, created_at__date__lte=period_end,
    )
    if hasattr(ReturnAuthorization, 'deleted_at'):
        qs = qs.filter(deleted_at__isnull=True)
    if status:
        qs = qs.filter(status=status)

    rows = []
    by_status = defaultdict(int)
    total_value = Decimal('0')
    for r in qs:
        value = _d(getattr(r, 'total_value', None) or getattr(r, 'total_amount', 0))
        total_value += value
        by_status[r.status] += 1
        rows.append({
            'rma_number': getattr(r, 'rma_number', '') or str(r.pk),
            'customer': getattr(r, 'customer_name', '') or '',
            'status': r.status,
            'reason': getattr(r, 'reason', '') or '',
            'total_value': _s(value),
        })

    chart = {
        'type': 'doughnut',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Count', 'data': list(by_status.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_rmas': len(rows),
        'total_value': _s(total_value),
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['rma_number', 'customer', 'status', 'reason', 'total_value'], 'rows': rows, 'chart': chart},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Section 5: Tracking & Ops
# ═══════════════════════════════════════════════════════════════════════════

def compute_lot_expiry(tenant, *, as_of_date=None, days_ahead=30, warehouse=None, **_):
    try:
        from lot_tracking.models import LotBatch
    except ImportError:
        return _empty_report('LotBatch model not available.')

    as_of_date = as_of_date or date.today()
    cutoff = as_of_date + timedelta(days=days_ahead)

    qs = LotBatch.objects.filter(tenant=tenant).select_related('product', 'warehouse')
    if warehouse:
        qs = qs.filter(warehouse=warehouse)

    rows = []
    by_status = defaultdict(int)
    expired_count = 0
    approaching_count = 0
    for lot in qs:
        exp = getattr(lot, 'expiry_date', None)
        if exp:
            days_to_expiry = (exp - as_of_date).days
        else:
            days_to_expiry = None
        if exp and exp < as_of_date:
            status = 'expired'
            expired_count += 1
        elif exp and exp <= cutoff:
            status = 'approaching'
            approaching_count += 1
        elif exp:
            status = 'ok'
        else:
            status = 'no_expiry'
        by_status[status] += 1
        rows.append({
            'lot_number': getattr(lot, 'lot_number', '') or str(lot.pk),
            'product_name': lot.product.name if getattr(lot, 'product_id', None) else '',
            'warehouse_name': lot.warehouse.name if getattr(lot, 'warehouse_id', None) else '',
            'quantity': _s(getattr(lot, 'quantity', 0)),
            'expiry_date': _s(exp),
            'days_to_expiry': days_to_expiry if days_to_expiry is not None else 'N/A',
            'status': status,
        })

    rows.sort(key=lambda r: r['days_to_expiry'] if isinstance(r['days_to_expiry'], int) else 99999)
    chart = {
        'type': 'bar',
        'labels': list(by_status.keys()),
        'datasets': [{'label': 'Lots', 'data': list(by_status.values())}],
    }
    summary = {
        'as_of_date': _s(as_of_date),
        'days_ahead': days_ahead,
        'total_lots': len(rows),
        'expired': expired_count,
        'approaching': approaching_count,
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['lot_number', 'product_name', 'warehouse_name', 'quantity', 'expiry_date', 'days_to_expiry', 'status'], 'rows': rows, 'chart': chart},
    }


def compute_forecast_vs_actual(tenant, *, period_start=None, period_end=None, category=None, **_):
    try:
        from forecasting.models import DemandForecastLine
    except ImportError:
        return _empty_report('DemandForecastLine model not available.')
    from orders.models import SalesOrderItem

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=180))

    # Aggregate forecast per (product, period_start_date) within range
    fqs = DemandForecastLine.objects.filter(
        tenant=tenant,
        period_start_date__gte=period_start, period_end_date__lte=period_end,
    ).select_related('forecast__product')
    forecast = defaultdict(lambda: Decimal('0'))
    product_map = {}
    for fl in fqs:
        p = getattr(fl.forecast, 'product', None)
        if not p:
            continue
        if category and p.category_id != (category.pk if hasattr(category, 'pk') else category):
            continue
        key = (p.pk, str(fl.period_start_date))
        forecast[key] += _d(getattr(fl, 'forecast_qty', 0))
        product_map[p.pk] = p

    # Aggregate actual per (product, period_start month) — simplified to month bucket
    sqs = (SalesOrderItem.objects.filter(
        tenant=tenant,
        sales_order__status__in=['delivered', 'closed'],
        sales_order__created_at__date__gte=period_start,
        sales_order__created_at__date__lte=period_end,
    ).select_related('product', 'sales_order'))
    actual = defaultdict(lambda: Decimal('0'))
    for soi in sqs:
        if category and soi.product.category_id != (category.pk if hasattr(category, 'pk') else category):
            continue
        dt = soi.sales_order.created_at.date() if soi.sales_order.created_at else None
        if not dt:
            continue
        period_key = dt.replace(day=1)
        key = (soi.product_id, str(period_key))
        actual[key] += _d(soi.quantity)
        product_map.setdefault(soi.product_id, soi.product)

    all_keys = set(forecast.keys()) | set(actual.keys())
    rows = []
    total_fc = total_ac = Decimal('0')
    for (pid, period) in sorted(all_keys, key=lambda k: (k[1], k[0])):
        p = product_map.get(pid)
        if not p:
            continue
        fc = forecast.get((pid, period), Decimal('0'))
        ac = actual.get((pid, period), Decimal('0'))
        variance = ac - fc
        var_pct = _pct(variance, fc) if fc else Decimal('0')
        total_fc += fc
        total_ac += ac
        rows.append({
            'product_name': p.name,
            'period': period,
            'forecast_qty': _s(fc),
            'actual_qty': _s(ac),
            'variance': _s(variance),
            'variance_pct': _s(var_pct.quantize(Decimal('0.01'))),
        })

    chart = {
        'type': 'line',
        'labels': [r['period'] + ' • ' + r['product_name'] for r in rows[:20]],
        'datasets': [
            {'label': 'Forecast', 'data': [float(_d(r['forecast_qty'])) for r in rows[:20]]},
            {'label': 'Actual', 'data': [float(_d(r['actual_qty'])) for r in rows[:20]]},
        ],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_forecast_qty': _s(total_fc),
        'total_actual_qty': _s(total_ac),
        'total_variance': _s(total_ac - total_fc),
        'total_variance_pct': _s((_pct(total_ac - total_fc, total_fc) if total_fc else Decimal('0')).quantize(Decimal('0.01'))),
    }
    return {
        'summary': summary,
        'data': {'columns': ['product_name', 'period', 'forecast_qty', 'actual_qty', 'variance', 'variance_pct'], 'rows': rows, 'chart': chart},
    }


def compute_alerts_log(tenant, *, period_start=None, period_end=None, alert_type=None, **_):
    try:
        from alerts_notifications.models import Alert
    except ImportError:
        return _empty_report('Alert model not available.')

    period_end = period_end or date.today()
    period_start = period_start or (period_end - timedelta(days=30))

    qs = Alert.objects.filter(
        tenant=tenant,
        triggered_at__date__gte=period_start, triggered_at__date__lte=period_end,
    )
    if hasattr(Alert, 'deleted_at'):
        qs = qs.filter(deleted_at__isnull=True)
    if alert_type:
        qs = qs.filter(alert_type=alert_type)

    rows = []
    by_type = defaultdict(int)
    by_status = defaultdict(int)
    for a in qs:
        by_type[a.alert_type] += 1
        by_status[a.status] += 1
        rows.append({
            'alert_number': getattr(a, 'alert_number', '') or str(a.pk),
            'alert_type': a.alert_type,
            'severity': getattr(a, 'severity', '') or '',
            'status': a.status,
            'created_at': _s(a.triggered_at.date() if a.triggered_at else ''),
        })

    chart = {
        'type': 'doughnut',
        'labels': list(by_type.keys()),
        'datasets': [{'label': 'Count', 'data': list(by_type.values())}],
    }
    summary = {
        'period_start': _s(period_start), 'period_end': _s(period_end),
        'total_alerts': len(rows),
        'by_type': {k: v for k, v in by_type.items()},
        'by_status': {k: v for k, v in by_status.items()},
    }
    return {
        'summary': summary,
        'data': {'columns': ['alert_number', 'alert_type', 'severity', 'status', 'created_at'], 'rows': rows, 'chart': chart},
    }
