"""Shared fixtures for the reporting test suite.

Mirrors the conventions used in alerts_notifications/tests/conftest.py —
tenant + warehouse + product + stock_level, plus `other_*` fixtures for
cross-tenant IDOR coverage.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import StockLevel

from reporting.models import ReportSnapshot


# ── tenants & users ───────────────────────────────────────────────────────

@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Reporting', slug='t-reporting')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other', slug='t-other-reporting')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_rep', password='x',
        email='admin_rep@example.com',
        tenant=tenant, is_tenant_admin=True, is_active=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_rep', password='x',
        tenant=tenant, is_tenant_admin=False, is_active=True,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other_rep', password='x',
        email='admin_other_rep@example.com',
        tenant=other_tenant, is_tenant_admin=True, is_active=True,
    )


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


# ── catalog + warehouse ────────────────────────────────────────────────────

@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Widgets')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category,
        sku='SKU-REP-1', name='Report Widget',
        purchase_cost=Decimal('10.00'), status='active',
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name='OtherCat')
    return Product.objects.create(
        tenant=other_tenant, category=cat,
        sku='OTH-REP-1', name='Other Widget',
        purchase_cost=Decimal('5.00'), status='active',
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WHR', name='Report WH', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WHR', name='Other Report WH', is_active=True,
    )


@pytest.fixture
def stock_level(db, tenant, warehouse, product):
    return StockLevel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=100, allocated=0, reorder_point=10, reorder_quantity=50,
    )


# ── report snapshots ──────────────────────────────────────────────────────

@pytest.fixture
def valuation_snapshot(db, tenant, tenant_admin, warehouse):
    return ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation',
        title='Test Valuation',
        as_of_date=date.today(),
        warehouse=warehouse,
        parameters={'as_of_date': date.today().isoformat()},
        summary={'total_value': '1000.00', 'total_units': '100', 'total_skus': 1},
        data={'columns': ['sku', 'total_value'], 'rows': [{'sku': 'SKU-REP-1', 'total_value': '1000.00'}]},
        generated_by=tenant_admin,
    )


@pytest.fixture
def other_tenant_snapshot(db, other_tenant, other_tenant_admin, other_warehouse):
    # Explicit number so cross-tenant tests can assert on a unique value
    return ReportSnapshot.objects.create(
        tenant=other_tenant, report_type='valuation',
        report_number='RPT-OTH-1',
        title='Other Tenant Valuation',
        as_of_date=date.today(),
        warehouse=other_warehouse,
        parameters={}, summary={}, data={'columns': [], 'rows': []},
        generated_by=other_tenant_admin,
    )
