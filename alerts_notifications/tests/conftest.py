"""Shared fixtures for the alerts_notifications test suite.

Mirrors the conventions used in stocktaking/tests/conftest.py and
quality_control/tests/conftest.py — tenant + warehouse + product +
stock-level + lot, plus `other_*` fixtures for cross-tenant IDOR tests.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import StockLevel
from lot_tracking.models import LotBatch

from alerts_notifications.models import Alert, NotificationRule


# ── tenants & users ───────────────────────────────────────────────────────

@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Alerts', slug='t-alerts')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other', slug='t-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_alerts', password='x',
        email='admin_alerts@example.com',
        tenant=tenant, is_tenant_admin=True, is_active=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_alerts', password='x',
        tenant=tenant, is_tenant_admin=False, is_active=True,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other', password='x',
        email='admin_other@example.com',
        tenant=other_tenant, is_tenant_admin=True, is_active=True,
    )


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username='qa_super', password='x', email='super@example.com',
    )


# ── catalog + warehouse ────────────────────────────────────────────────────

@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Widgets')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category,
        sku='SKU-A1', name='Widget A',
        purchase_cost=Decimal('10.00'), status='active',
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name='OtherCat')
    return Product.objects.create(
        tenant=other_tenant, category=cat,
        sku='OTH-SKU', name='Other',
        purchase_cost=Decimal('5.00'), status='active',
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main WH', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other WH', is_active=True,
    )


@pytest.fixture
def stock_level(db, tenant, warehouse, product):
    return StockLevel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=100, allocated=0, reorder_point=10, reorder_quantity=50,
    )


@pytest.fixture
def low_stock_level(db, tenant, warehouse, product):
    return StockLevel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=5, allocated=0, reorder_point=10, reorder_quantity=50,
    )


@pytest.fixture
def lot(db, tenant, warehouse, product):
    return LotBatch.objects.create(
        tenant=tenant, lot_number='LOT-T1',
        product=product, warehouse=warehouse,
        quantity=10, available_quantity=10,
        expiry_date=date.today() + timedelta(days=10),
        status='active',
    )


@pytest.fixture
def expired_lot(db, tenant, warehouse, product):
    return LotBatch.objects.create(
        tenant=tenant, lot_number='LOT-EXP',
        product=product, warehouse=warehouse,
        quantity=10, available_quantity=10,
        expiry_date=date.today() - timedelta(days=5),
        status='active',
    )


# ── alert objects ──────────────────────────────────────────────────────────

@pytest.fixture
def new_alert(db, tenant, product, warehouse):
    return Alert.objects.create(
        tenant=tenant, alert_type='low_stock', severity='warning',
        title='Low stock: SKU-A1', dedup_key='test:low:1',
        product=product, warehouse=warehouse,
    )


@pytest.fixture
def acknowledged_alert(db, tenant, tenant_admin, product, warehouse):
    from django.utils import timezone
    return Alert.objects.create(
        tenant=tenant, alert_type='low_stock', severity='warning',
        title='Ack alert', dedup_key='test:ack:1',
        status='acknowledged',
        acknowledged_by=tenant_admin, acknowledged_at=timezone.now(),
        product=product, warehouse=warehouse,
    )


@pytest.fixture
def foreign_alert(db, other_tenant, other_product, other_warehouse):
    return Alert.objects.create(
        tenant=other_tenant, alert_type='low_stock', severity='warning',
        title='Foreign alert', dedup_key='test:foreign:1',
        product=other_product, warehouse=other_warehouse,
    )


@pytest.fixture
def rule(db, tenant, tenant_admin):
    r = NotificationRule.objects.create(
        tenant=tenant, name='Stock-to-admins',
        alert_type='low_stock', min_severity='warning',
        notify_email=True, notify_inbox=True, is_active=True,
    )
    r.recipient_users.add(tenant_admin)
    return r


@pytest.fixture
def foreign_rule(db, other_tenant, other_tenant_admin):
    r = NotificationRule.objects.create(
        tenant=other_tenant, name='Foreign rule',
        alert_type='low_stock', min_severity='warning',
        notify_email=True, is_active=True,
    )
    r.recipient_users.add(other_tenant_admin)
    return r


# ── test clients ───────────────────────────────────────────────────────────

@pytest.fixture
def client_admin(client, tenant_admin):
    client.force_login(tenant_admin)
    return client


@pytest.fixture
def client_user(client, tenant_user):
    client.force_login(tenant_user)
    return client


@pytest.fixture
def client_super(client, superuser):
    client.force_login(superuser)
    return client
