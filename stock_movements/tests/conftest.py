import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from stock_movements.models import (
    StockTransfer, StockTransferItem, TransferApprovalRule, TransferRoute,
)

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
        username="qa_user", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="qa_other", password="qa_pass_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def approver_user(db, tenant):
    """A second tenant user, distinct from `user`, used to satisfy D-05 segregation."""
    return User.objects.create_user(
        username="qa_approver", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def approver_client(client, approver_user):
    client.force_login(approver_user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Hardware")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku="SKU-001",
        name="Widget", status="active", is_active=True,
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name="Foreign")
    return Product.objects.create(
        tenant=other_tenant, category=cat, sku="X-001",
        name="OtherWidget", status="active", is_active=True,
    )


@pytest.fixture
def w1(db, tenant):
    return Warehouse.objects.create(tenant=tenant, code="W1", name="Warehouse One", is_active=True)


@pytest.fixture
def w2(db, tenant):
    return Warehouse.objects.create(tenant=tenant, code="W2", name="Warehouse Two", is_active=True)


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code="OW", name="Other Warehouse", is_active=True,
    )


@pytest.fixture
def transfer_draft(db, tenant, w1, w2, user):
    return StockTransfer.objects.create(
        tenant=tenant, transfer_type="inter_warehouse",
        source_warehouse=w1, destination_warehouse=w2,
        priority="normal", status="draft", requested_by=user,
    )


@pytest.fixture
def transfer_pending(db, tenant, w1, w2, user):
    return StockTransfer.objects.create(
        tenant=tenant, transfer_type="inter_warehouse",
        source_warehouse=w1, destination_warehouse=w2,
        priority="normal", status="pending_approval", requested_by=user,
    )


@pytest.fixture
def transfer_in_transit(db, tenant, w1, w2, user, product):
    t = StockTransfer.objects.create(
        tenant=tenant, transfer_type="inter_warehouse",
        source_warehouse=w1, destination_warehouse=w2,
        priority="normal", status="in_transit", requested_by=user,
    )
    StockTransferItem.objects.create(
        tenant=tenant, transfer=t, product=product, quantity=10,
    )
    return t
