from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import (
    StockLevel, StockStatus, InventoryReservation,
    ValuationConfig, ValuationEntry,
)

User = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Test", slug="acme-test")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Globex Test", slug="globex-test")


@pytest.fixture
def admin_user(db, tenant):
    return User.objects.create_user(
        username="inv_admin", password="pw_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="inv_staff", password="pw_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_user(db, other_tenant):
    return User.objects.create_user(
        username="inv_other", password="pw_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code="WH-01", name="Main", is_active=True,
    )


@pytest.fixture
def product(db, tenant):
    cat = Category.objects.create(tenant=tenant, name="Supplies")
    return Product.objects.create(
        tenant=tenant, sku="SUP-001", name="Widget",
        category=cat, purchase_cost=10, retail_price=15,
        status="active",
    )


@pytest.fixture
def stock_level(db, tenant, product, warehouse):
    return StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=50, allocated=0, reorder_point=10, reorder_quantity=20,
    )


@pytest.fixture
def damaged_status(db, tenant, product, warehouse):
    return StockStatus.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        status='damaged', quantity=10,
    )


@pytest.fixture
def pending_reservation(db, tenant, product, warehouse, admin_user, stock_level):
    return InventoryReservation.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=5, status='pending', reserved_by=admin_user,
    )


@pytest.fixture
def confirmed_reservation(db, pending_reservation, stock_level):
    pending_reservation.status = 'confirmed'
    pending_reservation.save()
    stock_level.allocated += pending_reservation.quantity
    stock_level.save()
    return pending_reservation


@pytest.fixture
def valuation_config(db, tenant):
    return ValuationConfig.objects.create(tenant=tenant, method='weighted_avg')


@pytest.fixture
def cost_layers(db, tenant, product, warehouse):
    """Canonical 2-layer cost fixture for FIFO/LIFO correctness checks.

    Layer 1 (old): 2026-02-01, qty=5, unit_cost=$10.00
    Layer 2 (new): 2026-03-01, qty=5, unit_cost=$20.00

    With stock_level.on_hand = 5 (simulating 5 units consumed):
      - FIFO: oldest consumed first → on-hand valued at newest → $20.00
      - LIFO: newest consumed first → on-hand valued at oldest → $10.00
      - WAVG: (5×10 + 5×20)/10 = $15.00 → on-hand valued at $15.00
    """
    old = ValuationEntry.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        entry_date=date.today() - timedelta(days=60),
        quantity=5, remaining_quantity=5, unit_cost=Decimal('10'),
    )
    new = ValuationEntry.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        entry_date=date.today() - timedelta(days=30),
        quantity=5, remaining_quantity=5, unit_cost=Decimal('20'),
    )
    return [old, new]
