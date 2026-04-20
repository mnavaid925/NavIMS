"""Shared fixtures for the quality_control test suite.

Follows the conventions in stocktaking/tests/conftest.py and
returns/tests/conftest.py — tenant + user + category + product +
warehouse + zone + stock_level, with cross-tenant `other_*` fixtures
for IDOR coverage.
"""
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from vendors.models import Vendor
from warehousing.models import Warehouse, Zone
from inventory.models import StockLevel

from quality_control.models import (
    QCChecklist, QCChecklistItem,
    InspectionRoute,
    QuarantineRecord,
    DefectReport,
    ScrapWriteOff,
)


# ── Tenants & users ──────────────────────────────────────────────

@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-QC', slug='t-qc')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-QC-Other', slug='t-qc-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_qc', password='x',
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_admin_two(db, tenant):
    """Second admin in the same tenant — used for segregation-of-duties tests
    where the approver must differ from the requester."""
    return User.objects.create_user(
        username='admin_qc_two', password='x',
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_qc', password='x',
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_qc_other', password='x',
        tenant=other_tenant, is_tenant_admin=True,
    )


# ── Catalog / vendor ─────────────────────────────────────────────

@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Widgets')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku='SKU-QC-001', name='Widget A',
        category=category, status='active', is_active=True,
        purchase_cost=Decimal('10.00'),
    )


@pytest.fixture
def product_b(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku='SKU-QC-002', name='Widget B',
        category=category, status='active', is_active=True,
        purchase_cost=Decimal('5.00'),
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name='Foo')
    return Product.objects.create(
        tenant=other_tenant, sku='SKU-OTHER-001', name='Foreign Widget',
        category=cat, status='active', is_active=True,
    )


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(tenant=tenant, company_name='Acme Supplies')


# ── Warehouse / zones ────────────────────────────────────────────

@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other', is_active=True,
    )


@pytest.fixture
def qc_zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse, code='ZQC',
        name='QC Hold', zone_type='quarantine',
    )


@pytest.fixture
def storage_zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse, code='ZST',
        name='Main Storage', zone_type='storage',
    )


@pytest.fixture
def alien_zone(db, other_tenant, other_warehouse):
    return Zone.objects.create(
        tenant=other_tenant, warehouse=other_warehouse, code='ZA',
        name='Alien Zone', zone_type='quarantine',
    )


# ── Stock ────────────────────────────────────────────────────────

@pytest.fixture
def stock_level(db, tenant, warehouse, product):
    return StockLevel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=100, allocated=0, on_order=0,
    )


# ── Authenticated clients ────────────────────────────────────────

@pytest.fixture
def client_admin(db, tenant_admin):
    c = Client()
    c.force_login(tenant_admin)
    return c


@pytest.fixture
def client_user(db, tenant_user):
    c = Client()
    c.force_login(tenant_user)
    return c


@pytest.fixture
def client_other(db, other_tenant_admin):
    c = Client()
    c.force_login(other_tenant_admin)
    return c


# ── Pre-built QC records ─────────────────────────────────────────

@pytest.fixture
def checklist(db, tenant, tenant_admin):
    c = QCChecklist.objects.create(
        tenant=tenant, name='Default', applies_to='all', created_by=tenant_admin,
    )
    QCChecklistItem.objects.create(
        tenant=tenant, checklist=c, sequence=1,
        check_name='Visual inspection', check_type='visual',
    )
    return c


@pytest.fixture
def route(db, tenant, warehouse, qc_zone, storage_zone):
    return InspectionRoute.objects.create(
        tenant=tenant, name='Standard', source_warehouse=warehouse,
        qc_zone=qc_zone, putaway_zone=storage_zone, priority=100,
    )


@pytest.fixture
def active_quarantine(db, tenant, product, warehouse, qc_zone, tenant_admin):
    return QuarantineRecord.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, zone=qc_zone,
        quantity=5, reason='defect', held_by=tenant_admin,
    )


@pytest.fixture
def open_defect(db, tenant, product, warehouse, tenant_admin):
    return DefectReport.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity_affected=2, defect_type='visual', severity='minor',
        source='receiving', description='demo defect',
        reported_by=tenant_admin,
    )


@pytest.fixture
def approved_scrap(db, tenant, product, warehouse, tenant_admin):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=3, unit_cost=Decimal('10.0000'), reason='demo',
        approval_status='approved', requested_by=tenant_admin,
        approved_by=tenant_admin,
    )
    return s
