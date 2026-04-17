import pytest
from datetime import date, timedelta
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from lot_tracking.models import LotBatch, SerialNumber

User = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Test", slug="acme-test")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Other Co", slug="other-co")


@pytest.fixture
def user(db, tenant):
    return User.objects.create_user(
        username="lt_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="lt_qa_reader", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="lt_qa_other", password="qa_pass_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def client_non_admin(client, non_admin_user):
    client.force_login(non_admin_user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Electronics")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku="SKU-001", name="ThinkPad",
        category=category, purchase_cost=100, retail_price=200,
        status="active",
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(tenant=tenant, name="Main DC")


@pytest.fixture
def lot(db, tenant, product, warehouse):
    return LotBatch.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=100, available_quantity=100,
        manufacturing_date=date.today() - timedelta(days=30),
        expiry_date=date.today() + timedelta(days=180),
    )


@pytest.fixture
def serial(db, tenant, product, warehouse, lot):
    return SerialNumber.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        lot=lot, serial_number="SN-0001",
    )
