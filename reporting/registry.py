"""Registry of the 21 reports in Module 18 — Reporting & Analytics.

Each report is a dict describing:
- slug: the `report_type` key stored in ReportSnapshot.report_type
- title: human-readable label
- section: section label (grouping in the sidebar + index page)
- section_order, order: sort keys
- icon: remix icon class
- description: short help text
- service: dotted path to the compute function in `reporting.services`
- form: dotted path to the form class in `reporting.forms`
- chart_type: Chart.js chart type (bar / pie / line / doughnut) or '' to skip
- csv_columns: list of (header, data_key) tuples for CSV export

Services, forms, and templates resolve lazily via these slugs so adding a new
report only requires: (a) adding the slug to REPORT_TYPE_CHOICES in models, (b)
writing the compute function + form, (c) adding an entry here.
"""
from collections import OrderedDict


SECTIONS = OrderedDict([
    ('inventory_stock', {'label': 'Inventory & Stock', 'icon': 'ri-archive-2-line', 'order': 1}),
    ('procurement', {'label': 'Procurement', 'icon': 'ri-shopping-cart-2-line', 'order': 2}),
    ('warehouse_ops', {'label': 'Warehouse Ops', 'icon': 'ri-building-2-line', 'order': 3}),
    ('sales_fulfillment', {'label': 'Sales & Fulfillment', 'icon': 'ri-truck-line', 'order': 4}),
    ('tracking_ops', {'label': 'Tracking & Ops', 'icon': 'ri-radar-line', 'order': 5}),
])


REPORTS = OrderedDict()


def register(slug, **spec):
    REPORTS[slug] = {'slug': slug, **spec}


# ═══════════════════════════════════════════════════════════════════════════
# Section 1: Inventory & Stock (6)
# ═══════════════════════════════════════════════════════════════════════════

register(
    'valuation',
    title='Inventory Valuation',
    section='inventory_stock', order=1,
    icon='ri-money-dollar-circle-line',
    description='Total value of current stock on hand, per product and warehouse.',
    service='reporting.services.compute_valuation',
    form='reporting.forms.ValuationForm',
    chart_type='bar',
    csv_columns=[
        ('SKU', 'sku'), ('Product', 'product_name'), ('Warehouse', 'warehouse_name'),
        ('On Hand', 'on_hand'), ('Unit Cost', 'unit_cost'), ('Total Value', 'total_value'),
    ],
)

register(
    'aging',
    title='Aging Analysis',
    section='inventory_stock', order=2,
    icon='ri-time-line',
    description='Identify slow-moving or dead stock by days since last movement.',
    service='reporting.services.compute_aging',
    form='reporting.forms.AgingForm',
    chart_type='bar',
    csv_columns=[
        ('SKU', 'sku'), ('Product', 'product_name'), ('Warehouse', 'warehouse_name'),
        ('On Hand', 'on_hand'), ('Last Movement', 'last_movement'),
        ('Days Since', 'days_since'), ('Bucket', 'bucket'), ('Value', 'value'),
    ],
)

register(
    'abc',
    title='ABC Analysis',
    section='inventory_stock', order=3,
    icon='ri-bar-chart-grouped-line',
    description='Classify inventory by consumption value and velocity (Pareto 80/15/5).',
    service='reporting.services.compute_abc',
    form='reporting.forms.ABCForm',
    chart_type='doughnut',
    csv_columns=[
        ('Rank', 'rank'), ('SKU', 'sku'), ('Product', 'product_name'),
        ('Annual Qty', 'annual_qty'), ('Unit Cost', 'unit_cost'),
        ('Annual Value', 'annual_value'), ('Cumulative %', 'cum_pct'), ('Class', 'abc_class'),
    ],
)

register(
    'turnover',
    title='Stock Turnover Ratio',
    section='inventory_stock', order=4,
    icon='ri-refresh-line',
    description='How quickly inventory is sold and replaced over a period.',
    service='reporting.services.compute_turnover',
    form='reporting.forms.TurnoverForm',
    chart_type='bar',
    csv_columns=[
        ('SKU', 'sku'), ('Product', 'product_name'),
        ('COGS', 'cogs'), ('Avg Inventory', 'avg_inventory'),
        ('Turnover', 'turnover'), ('DSI (days)', 'dsi'),
    ],
)

register(
    'reservations',
    title='Reservations Report',
    section='inventory_stock', order=5,
    icon='ri-lock-2-line',
    description='Reserved inventory by status, product, and warehouse.',
    service='reporting.services.compute_reservations',
    form='reporting.forms.ReservationsForm',
    chart_type='pie',
    csv_columns=[
        ('Ref', 'reference'), ('Product', 'product_name'), ('Warehouse', 'warehouse_name'),
        ('Qty', 'quantity'), ('Status', 'status'), ('Reserved At', 'reserved_at'),
    ],
)

register(
    'multi_location',
    title='Multi-Location Stock Roll-up',
    section='inventory_stock', order=6,
    icon='ri-map-pin-line',
    description='Aggregate stock across location hierarchy (Region → DC → Store).',
    service='reporting.services.compute_multi_location',
    form='reporting.forms.MultiLocationForm',
    chart_type='bar',
    csv_columns=[
        ('Location', 'location_name'), ('Type', 'location_type'),
        ('SKUs', 'sku_count'), ('Total On Hand', 'total_on_hand'),
        ('Total Value', 'total_value'),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════
# Section 2: Procurement (4)
# ═══════════════════════════════════════════════════════════════════════════

register(
    'po_summary',
    title='Purchase Order Summary',
    section='procurement', order=1,
    icon='ri-file-list-3-line',
    description='POs by status, vendor, and value over a period.',
    service='reporting.services.compute_po_summary',
    form='reporting.forms.POSummaryForm',
    chart_type='bar',
    csv_columns=[
        ('PO #', 'po_number'), ('Vendor', 'vendor_name'), ('Status', 'status'),
        ('Order Date', 'order_date'), ('Total', 'total_value'),
    ],
)

register(
    'vendor_performance',
    title='Vendor Performance',
    section='procurement', order=2,
    icon='ri-user-star-line',
    description='Overall score, on-time delivery, quality, and compliance per vendor.',
    service='reporting.services.compute_vendor_performance',
    form='reporting.forms.VendorPerformanceForm',
    chart_type='bar',
    csv_columns=[
        ('Vendor', 'vendor_name'), ('PO Count', 'po_count'),
        ('On-Time Ratio', 'on_time_ratio'), ('Quality', 'quality_score'),
        ('Compliance', 'compliance_score'), ('Overall', 'overall_score'),
    ],
)

register(
    'three_way_match',
    title='Three-Way Match Variance',
    section='procurement', order=3,
    icon='ri-scales-3-line',
    description='PO ↔ GRN ↔ Invoice variance detection across matches.',
    service='reporting.services.compute_three_way_match',
    form='reporting.forms.ThreeWayMatchForm',
    chart_type='bar',
    csv_columns=[
        ('Match #', 'match_number'), ('PO #', 'po_number'), ('GRN #', 'grn_number'),
        ('Invoice #', 'invoice_number'), ('Status', 'status'), ('Variance', 'variance_total'),
    ],
)

register(
    'receiving_grn',
    title='Receiving / GRN',
    section='procurement', order=4,
    icon='ri-inbox-archive-line',
    description='Received quantities and variances by period, vendor, and warehouse.',
    service='reporting.services.compute_receiving_grn',
    form='reporting.forms.ReceivingGRNForm',
    chart_type='bar',
    csv_columns=[
        ('GRN #', 'grn_number'), ('Vendor', 'vendor_name'), ('Warehouse', 'warehouse_name'),
        ('Received Date', 'received_date'), ('Total Qty', 'total_qty'),
        ('Status', 'status'),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════
# Section 3: Warehouse Ops (4)
# ═══════════════════════════════════════════════════════════════════════════

register(
    'stock_transfers',
    title='Stock Transfers',
    section='warehouse_ops', order=1,
    icon='ri-swap-box-line',
    description='Stock transfers by status, route, source and destination.',
    service='reporting.services.compute_stock_transfers',
    form='reporting.forms.StockTransfersForm',
    chart_type='bar',
    csv_columns=[
        ('Transfer #', 'transfer_number'), ('From', 'source'), ('To', 'destination'),
        ('Status', 'status'), ('Created', 'created_at'), ('Item Count', 'item_count'),
    ],
)

register(
    'stocktake_variance',
    title='Stocktaking Variance',
    section='warehouse_ops', order=2,
    icon='ri-clipboard-line',
    description='Variance per stock count — counted vs system, with reason codes.',
    service='reporting.services.compute_stocktake_variance',
    form='reporting.forms.StocktakeVarianceForm',
    chart_type='bar',
    csv_columns=[
        ('Count #', 'count_number'), ('Warehouse', 'warehouse_name'),
        ('Status', 'status'), ('Items', 'item_count'),
        ('Variance Qty', 'variance_qty'), ('Variance Value', 'variance_value'),
    ],
)

register(
    'quality_control',
    title='Quality Control',
    section='warehouse_ops', order=3,
    icon='ri-shield-check-line',
    description='Quarantines and defect reports by status, severity, and type.',
    service='reporting.services.compute_quality_control',
    form='reporting.forms.QualityControlForm',
    chart_type='doughnut',
    csv_columns=[
        ('Kind', 'kind'), ('Ref #', 'ref_number'), ('Product', 'product_name'),
        ('Severity', 'severity'), ('Status', 'status'), ('Created', 'created_at'),
    ],
)

register(
    'scrap_writeoff',
    title='Scrap Write-Off',
    section='warehouse_ops', order=4,
    icon='ri-delete-bin-line',
    description='Posted scrap write-offs by period, warehouse, value, and reason.',
    service='reporting.services.compute_scrap_writeoff',
    form='reporting.forms.ScrapWriteoffForm',
    chart_type='pie',
    csv_columns=[
        ('Scrap #', 'scrap_number'), ('Product', 'product_name'), ('Warehouse', 'warehouse_name'),
        ('Qty', 'quantity'), ('Unit Cost', 'unit_cost'), ('Total Value', 'total_value'),
        ('Status', 'status'),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════
# Section 4: Sales & Fulfillment (4)
# ═══════════════════════════════════════════════════════════════════════════

register(
    'so_summary',
    title='Sales Order Summary',
    section='sales_fulfillment', order=1,
    icon='ri-shopping-bag-3-line',
    description='Sales orders by status, customer, and value over a period.',
    service='reporting.services.compute_so_summary',
    form='reporting.forms.SOSummaryForm',
    chart_type='bar',
    csv_columns=[
        ('SO #', 'so_number'), ('Customer', 'customer'), ('Status', 'status'),
        ('Order Date', 'order_date'), ('Total', 'total_value'),
    ],
)

register(
    'fulfillment',
    title='Fulfillment (Pick/Pack/Ship)',
    section='sales_fulfillment', order=2,
    icon='ri-send-plane-2-line',
    description='Pick / pack / ship throughput and SLA across orders.',
    service='reporting.services.compute_fulfillment',
    form='reporting.forms.FulfillmentForm',
    chart_type='line',
    csv_columns=[
        ('SO #', 'so_number'), ('Picked', 'picked_at'), ('Packed', 'packed_at'),
        ('Shipped', 'shipped_at'), ('Cycle Hrs', 'cycle_hours'),
    ],
)

register(
    'shipment_carrier',
    title='Shipment / Carrier',
    section='sales_fulfillment', order=3,
    icon='ri-ship-line',
    description='Shipments by carrier, status, and tracking events over a period.',
    service='reporting.services.compute_shipment_carrier',
    form='reporting.forms.ShipmentCarrierForm',
    chart_type='bar',
    csv_columns=[
        ('Shipment #', 'shipment_number'), ('Carrier', 'carrier_name'),
        ('Tracking', 'tracking_number'), ('Status', 'status'),
        ('Dispatched', 'dispatched_at'), ('Delivered', 'delivered_at'),
    ],
)

register(
    'returns_rma',
    title='Returns (RMA)',
    section='sales_fulfillment', order=4,
    icon='ri-arrow-go-back-line',
    description='Return authorizations, dispositions, and refunds over a period.',
    service='reporting.services.compute_returns_rma',
    form='reporting.forms.ReturnsRMAForm',
    chart_type='doughnut',
    csv_columns=[
        ('RMA #', 'rma_number'), ('Customer', 'customer'), ('Status', 'status'),
        ('Reason', 'reason'), ('Total Value', 'total_value'),
    ],
)


# ═══════════════════════════════════════════════════════════════════════════
# Section 5: Tracking & Ops (3)
# ═══════════════════════════════════════════════════════════════════════════

register(
    'lot_expiry',
    title='Lot / Serial / Expiry',
    section='tracking_ops', order=1,
    icon='ri-barcode-line',
    description='Lots and serials with expiry status — active, approaching, expired.',
    service='reporting.services.compute_lot_expiry',
    form='reporting.forms.LotExpiryForm',
    chart_type='bar',
    csv_columns=[
        ('Lot #', 'lot_number'), ('Product', 'product_name'), ('Warehouse', 'warehouse_name'),
        ('Qty', 'quantity'), ('Expiry Date', 'expiry_date'),
        ('Days to Expiry', 'days_to_expiry'), ('Status', 'status'),
    ],
)

register(
    'forecast_vs_actual',
    title='Forecast vs Actual',
    section='tracking_ops', order=2,
    icon='ri-line-chart-line',
    description='Compare demand forecast lines against actual delivered sales.',
    service='reporting.services.compute_forecast_vs_actual',
    form='reporting.forms.ForecastVsActualForm',
    chart_type='line',
    csv_columns=[
        ('Product', 'product_name'), ('Period', 'period'),
        ('Forecast Qty', 'forecast_qty'), ('Actual Qty', 'actual_qty'),
        ('Variance', 'variance'), ('Variance %', 'variance_pct'),
    ],
)

register(
    'alerts_log',
    title='Alerts & Notifications Log',
    section='tracking_ops', order=3,
    icon='ri-notification-3-line',
    description='Alerts raised and notifications delivered over a period.',
    service='reporting.services.compute_alerts_log',
    form='reporting.forms.AlertsLogForm',
    chart_type='doughnut',
    csv_columns=[
        ('Alert #', 'alert_number'), ('Type', 'alert_type'), ('Severity', 'severity'),
        ('Status', 'status'), ('Created', 'created_at'),
    ],
)


def get_report(slug):
    """Return the registry entry for a slug, or None if unknown."""
    return REPORTS.get(slug)


def sections_with_reports():
    """Yield (section_key, section_meta, reports_in_section) in section order."""
    for key, meta in SECTIONS.items():
        reports = [r for r in REPORTS.values() if r['section'] == key]
        reports.sort(key=lambda r: r['order'])
        yield key, meta, reports


def resolve(dotted_path):
    """Import a dotted module.attr path — used for late-binding service/form lookups."""
    import importlib
    module_path, _, attr = dotted_path.rpartition('.')
    module = importlib.import_module(module_path)
    return getattr(module, attr)
