"""Scanner command tests — dedup, happy path, edge cases for all 4 scanners."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from alerts_notifications.models import Alert


# ── generate_stock_alerts ────────────────────────────────────────────────

@pytest.mark.django_db
def test_stock_scanner_creates_out_of_stock(tenant, product, warehouse):
    from inventory.models import StockLevel
    StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=0, allocated=0, reorder_point=10,
    )
    call_command('generate_stock_alerts', '--tenant', tenant.slug)
    a = Alert.objects.get(tenant=tenant, alert_type='out_of_stock')
    assert a.severity == 'critical'
    assert a.current_value == 0


@pytest.mark.django_db
def test_stock_scanner_creates_low_stock(tenant, low_stock_level):
    call_command('generate_stock_alerts', '--tenant', tenant.slug)
    a = Alert.objects.get(tenant=tenant, alert_type='low_stock')
    assert a.severity == 'warning'


@pytest.mark.django_db
def test_stock_scanner_dedup_same_day(tenant, low_stock_level):
    call_command('generate_stock_alerts', '--tenant', tenant.slug)
    call_command('generate_stock_alerts', '--tenant', tenant.slug)
    assert Alert.objects.filter(tenant=tenant, alert_type='low_stock').count() == 1


@pytest.mark.django_db
def test_stock_scanner_noop_when_reorder_point_zero(tenant, warehouse, product):
    from inventory.models import StockLevel
    StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=100, allocated=0, reorder_point=0,
    )
    call_command('generate_stock_alerts', '--tenant', tenant.slug)
    assert Alert.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_stock_scanner_dry_run_writes_nothing(tenant, low_stock_level):
    call_command('generate_stock_alerts', '--tenant', tenant.slug, '--dry-run')
    assert Alert.objects.filter(tenant=tenant).count() == 0


# ── generate_overstock_alerts ────────────────────────────────────────────

@pytest.mark.django_db
def test_overstock_scanner_emits_when_on_hand_exceeds_max(tenant, product, warehouse):
    from inventory.models import StockLevel
    from multi_location.models import Location, LocationSafetyStockRule
    StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=800, reorder_point=10,
    )
    loc = Location.objects.create(
        tenant=tenant, code='LOC-1', name='Loc 1',
        warehouse=warehouse,
    )
    LocationSafetyStockRule.objects.create(
        tenant=tenant, location=loc, product=product,
        safety_stock_qty=10, reorder_point=20, max_stock_qty=500,
    )
    call_command('generate_overstock_alerts', '--tenant', tenant.slug)
    a = Alert.objects.get(tenant=tenant, alert_type='overstock')
    assert a.current_value == 800
    assert a.threshold_value == 500


@pytest.mark.django_db
def test_overstock_scanner_skips_tenant_without_rules(tenant, stock_level):
    call_command('generate_overstock_alerts', '--tenant', tenant.slug)
    assert Alert.objects.filter(tenant=tenant, alert_type='overstock').count() == 0


# ── alerts_scan_expiry ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_expiry_scanner_emits_expired(tenant, expired_lot):
    call_command('alerts_scan_expiry', '--tenant', tenant.slug)
    a = Alert.objects.get(tenant=tenant, alert_type='expired')
    assert a.severity == 'critical'


@pytest.mark.django_db
def test_expiry_scanner_emits_approaching_within_horizon(tenant, lot):
    call_command('alerts_scan_expiry', '--tenant', tenant.slug, '--days-ahead', '30')
    a = Alert.objects.get(tenant=tenant, alert_type='expiry_approaching')
    assert a.severity == 'warning'


@pytest.mark.django_db
def test_expiry_scanner_skips_lots_without_expiry(tenant, warehouse, product):
    from lot_tracking.models import LotBatch
    LotBatch.objects.create(
        tenant=tenant, lot_number='L-NOEXP',
        product=product, warehouse=warehouse,
        quantity=10, available_quantity=10,
        status='active',  # expiry_date=None
    )
    call_command('alerts_scan_expiry', '--tenant', tenant.slug)
    assert Alert.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_expiry_scanner_skips_non_active_lots(tenant, warehouse, product):
    from lot_tracking.models import LotBatch
    LotBatch.objects.create(
        tenant=tenant, lot_number='L-CONSUMED',
        product=product, warehouse=warehouse,
        quantity=10, available_quantity=0,
        expiry_date=date.today() - timedelta(days=5),
        status='consumed',
    )
    call_command('alerts_scan_expiry', '--tenant', tenant.slug)
    assert Alert.objects.filter(tenant=tenant, alert_type='expired').count() == 0


@pytest.mark.django_db
def test_expiry_scanner_dedup(tenant, expired_lot):
    call_command('alerts_scan_expiry', '--tenant', tenant.slug)
    call_command('alerts_scan_expiry', '--tenant', tenant.slug)
    assert Alert.objects.filter(tenant=tenant, alert_type='expired').count() == 1


# ── generate_workflow_alerts ─────────────────────────────────────────────

@pytest.mark.django_db
def test_workflow_scanner_emits_po_approval_pending(tenant, product, tenant_admin):
    from datetime import timedelta
    from vendors.models import Vendor
    from purchase_orders.models import PurchaseOrder
    vendor = Vendor.objects.create(tenant=tenant, company_name='V1', email='v@x.com')
    po = PurchaseOrder.objects.create(
        tenant=tenant, vendor=vendor,
        order_date=date.today(), expected_delivery_date=date.today() + timedelta(days=7),
        status='pending_approval', created_by=tenant_admin,
    )
    # Backdate updated_at to 72 hours ago
    PurchaseOrder.objects.filter(pk=po.pk).update(updated_at=timezone.now() - timedelta(hours=72))

    call_command('generate_workflow_alerts', '--tenant', tenant.slug, '--po-stale-hours', '48')
    a = Alert.objects.get(tenant=tenant, alert_type='po_approval_pending')
    assert a.purchase_order_id == po.pk


@pytest.mark.django_db
def test_workflow_scanner_emits_shipment_delayed(tenant, tenant_admin, warehouse, product):
    from datetime import timedelta as td
    from orders.models import SalesOrder, Shipment
    so = SalesOrder.objects.create(
        tenant=tenant, warehouse=warehouse,
        customer_name='C1', customer_email='c@x.com',
        order_date=date.today(), status='shipped', created_by=tenant_admin,
    )
    ship = Shipment.objects.create(
        tenant=tenant, sales_order=so, status='in_transit',
        estimated_delivery_date=date.today() - td(days=3),
    )

    call_command('generate_workflow_alerts', '--tenant', tenant.slug, '--grace-days', '0')
    a = Alert.objects.get(tenant=tenant, alert_type='shipment_delayed')
    assert a.shipment_id == ship.pk


@pytest.mark.django_db
def test_workflow_scanner_grace_days_defers(tenant, tenant_admin, warehouse):
    from datetime import timedelta as td
    from orders.models import SalesOrder, Shipment
    so = SalesOrder.objects.create(
        tenant=tenant, warehouse=warehouse,
        customer_name='C1', customer_email='c@x.com',
        order_date=date.today(), status='shipped', created_by=tenant_admin,
    )
    Shipment.objects.create(
        tenant=tenant, sales_order=so, status='in_transit',
        estimated_delivery_date=date.today() - td(days=1),
    )
    # With grace_days=3, yesterday's overdue should NOT fire
    call_command('generate_workflow_alerts', '--tenant', tenant.slug, '--grace-days', '3')
    assert Alert.objects.filter(tenant=tenant, alert_type='shipment_delayed').count() == 0
