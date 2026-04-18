from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import StockLevel
from multi_location.models import Location

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
        username="ml_admin", password="pw_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def staff_user(db, tenant):
    return User.objects.create_user(
        username="ml_staff", password="pw_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_admin(db, other_tenant):
    return User.objects.create_user(
        username="ml_other", password="pw_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code="WH-01", name="Main", is_active=True,
    )


@pytest.fixture
def warehouse2(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code="WH-02", name="Secondary", is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Supplies")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku="SUP-001", name="Widget",
        category=category, purchase_cost=Decimal("10"), retail_price=Decimal("15"),
        status="active",
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name="Foreign Cat")
    return Product.objects.create(
        tenant=other_tenant, sku="OTH-001", name="Foreign Widget",
        category=cat, purchase_cost=Decimal("5"), retail_price=Decimal("8"),
        status="active",
    )


@pytest.fixture
def company(db, tenant):
    return Location.objects.create(tenant=tenant, name="HQ", location_type="company")


@pytest.fixture
def region(db, tenant, company):
    return Location.objects.create(
        tenant=tenant, name="North", location_type="regional_dc", parent=company,
    )


@pytest.fixture
def dc(db, tenant, region, warehouse):
    return Location.objects.create(
        tenant=tenant, name="Seattle DC", location_type="distribution_center",
        parent=region, warehouse=warehouse,
    )


@pytest.fixture
def store(db, tenant, region):
    return Location.objects.create(
        tenant=tenant, name="Seattle Store", location_type="retail_store", parent=region,
    )


@pytest.fixture
def other_location(db, other_tenant):
    return Location.objects.create(tenant=other_tenant, name="Foreign Loc")


@pytest.fixture
def stock_level(db, tenant, product, warehouse):
    return StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=100, allocated=10, reorder_point=20, reorder_quantity=50,
    )
