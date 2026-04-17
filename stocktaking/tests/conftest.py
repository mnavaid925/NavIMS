"""Shared fixtures for the stocktaking test suite.

Mirrors the conventions used in lot_tracking/tests/conftest.py and
orders/tests/conftest.py — tenant + warehouse + product + stock levels,
with matching `other_*` fixtures for cross-tenant IDOR tests.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse, Zone
from inventory.models import StockLevel
from stocktaking.models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Stock', slug='t-stock')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other', slug='t-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_stock', password='x',
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_stock', password='x',
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other', password='x',
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Widgets')


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
def zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse, code='Z1', name='Zone 1',
    )


@pytest.fixture
def products(db, tenant, category):
    return [
        Product.objects.create(
            tenant=tenant, category=category,
            sku=f'SKU-{i:03d}', name=f'Widget {i}',
            purchase_cost=Decimal('10.00'), status='active',
        )
        for i in range(6)
    ]


@pytest.fixture
def stock_levels(db, tenant, warehouse, products):
    return [
        StockLevel.objects.create(
            tenant=tenant, warehouse=warehouse, product=p,
            on_hand=100, allocated=0, on_order=0,
        )
        for p in products
    ]


@pytest.fixture
def schedule(db, tenant, warehouse, tenant_admin):
    return CycleCountSchedule.objects.create(
        tenant=tenant, warehouse=warehouse,
        name='Weekly Class A', frequency='weekly', abc_class='a',
        is_active=True, created_by=tenant_admin,
    )


@pytest.fixture
def freeze(db, tenant, warehouse):
    return StocktakeFreeze.objects.create(
        tenant=tenant, warehouse=warehouse, status='active',
    )


@pytest.fixture
def draft_count(db, tenant, warehouse, tenant_admin):
    return StockCount.objects.create(
        tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        created_by=tenant_admin,
    )


@pytest.fixture
def counted_count(db, tenant, warehouse, products, stock_levels):
    """A StockCount in status=counted with:
       - 3 items with variance (delta: -2, +3, -1)
       - 3 items with zero variance
    Net variance qty = 0; values will reflect variance × 10 unit cost.
    """
    c = StockCount.objects.create(
        tenant=tenant, warehouse=warehouse,
        scheduled_date=date.today(), status='counted',
    )
    deltas = [-2, 0, 3, 0, -1, 0]
    for p, sl, d in zip(products, stock_levels, deltas):
        StockCountItem.objects.create(
            tenant=tenant, count=c, product=p,
            system_qty=sl.on_hand, counted_qty=sl.on_hand + d,
            unit_cost=Decimal('10.00'),
        )
    return c


@pytest.fixture
def approved_adj(db, tenant, counted_count):
    return StockVarianceAdjustment.objects.create(
        tenant=tenant, count=counted_count, status='approved',
    )


@pytest.fixture
def pending_adj(db, tenant, counted_count):
    return StockVarianceAdjustment.objects.create(
        tenant=tenant, count=counted_count, status='pending',
    )


# ── Authenticated clients ──────────────────────────────────────────

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
