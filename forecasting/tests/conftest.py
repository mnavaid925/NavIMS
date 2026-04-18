from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import StockLevel
from forecasting.models import (
    DemandForecast, ReorderPoint, ReorderAlert,
    SafetyStock, SeasonalityProfile, SeasonalityPeriod,
)

User = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Forecast", slug="acme-forecast")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Globex Forecast", slug="globex-forecast")


@pytest.fixture
def admin_user(db, tenant):
    return User.objects.create_user(
        username="fc_admin", password="pw_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="fc_staff", password="pw_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username="fc_other", password="pw_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code="WH-FC", name="FC Main", is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Supplies-FC")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku="FC-001", name="Widget FC",
        category=category, purchase_cost=10, retail_price=15, status="active",
    )


@pytest.fixture
def stock_level(db, tenant, product, warehouse):
    return StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=40, allocated=0, reorder_point=0, reorder_quantity=0,
    )


@pytest.fixture
def rop(db, tenant, product, warehouse):
    rp = ReorderPoint(
        tenant=tenant, product=product, warehouse=warehouse,
        avg_daily_usage=Decimal("5"), lead_time_days=7,
        safety_stock_qty=10, min_qty=10, max_qty=100,
        reorder_qty=30, is_active=True,
    )
    rp.recalc_rop()
    rp.save()
    return rp


@pytest.fixture
def monthly_profile(db, tenant):
    prof = SeasonalityProfile.objects.create(
        tenant=tenant, name="Jul peak", period_type="month", is_active=True,
    )
    for m in range(1, 13):
        mult = Decimal("1.50") if m == 7 else Decimal("1.00")
        SeasonalityPeriod.objects.create(
            tenant=tenant, profile=prof, period_number=m,
            period_label=date(2000, m, 1).strftime("%b"),
            demand_multiplier=mult,
        )
    return prof


@pytest.fixture
def quarter_profile(db, tenant):
    prof = SeasonalityProfile.objects.create(
        tenant=tenant, name="Q4 holiday", period_type="quarter", is_active=True,
    )
    mults = {1: "0.9", 2: "0.95", 3: "1.05", 4: "1.40"}
    for q in range(1, 5):
        SeasonalityPeriod.objects.create(
            tenant=tenant, profile=prof, period_number=q,
            period_label=f"Q{q}", demand_multiplier=Decimal(mults[q]),
        )
    return prof
