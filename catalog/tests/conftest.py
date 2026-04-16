import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product

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
        username="qa_user",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="qa_other",
        password="qa_pass_123!",
        tenant=other_tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def department(db, tenant):
    return Category.objects.create(tenant=tenant, name="Electronics")


@pytest.fixture
def category(db, tenant, department):
    return Category.objects.create(tenant=tenant, name="Laptops", parent=department)


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant,
        sku="LAP-001",
        name="ThinkPad X1",
        category=category,
        purchase_cost=800,
        retail_price=1200,
        status="active",
    )
