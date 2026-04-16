from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from vendors.models import Vendor
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from receiving.models import (
    WarehouseLocation, GoodsReceiptNote, GoodsReceiptNoteItem,
    VendorInvoice,
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
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def other_client_logged_in(client, other_user):
    client.force_login(other_user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Hardware")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku="SKU-001",
        name="Widget", status="active",
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name="X")
    return Product.objects.create(
        tenant=other_tenant, category=cat, sku="X-001",
        name="OtherWidget", status="active",
    )


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant, company_name="Acme Supplies",
        email="sup@example.com", is_active=True,
    )


@pytest.fixture
def other_vendor(db, other_tenant):
    return Vendor.objects.create(
        tenant=other_tenant, company_name="Other Supplies",
        email="o@example.com", is_active=True,
    )


@pytest.fixture
def po(db, tenant, vendor, user):
    return PurchaseOrder.objects.create(
        tenant=tenant, vendor=vendor, status="sent",
        order_date=date(2026, 1, 1), created_by=user,
    )


@pytest.fixture
def po_item(db, tenant, po, product):
    return PurchaseOrderItem.objects.create(
        tenant=tenant, purchase_order=po, product=product,
        quantity=10, unit_price=Decimal("5.00"),
    )


@pytest.fixture
def other_po(db, other_tenant, other_vendor, other_user):
    return PurchaseOrder.objects.create(
        tenant=other_tenant, vendor=other_vendor, status="sent",
        order_date=date(2026, 1, 1), created_by=other_user,
    )


@pytest.fixture
def other_po_item(db, other_tenant, other_po, other_product):
    return PurchaseOrderItem.objects.create(
        tenant=other_tenant, purchase_order=other_po, product=other_product,
        quantity=3, unit_price=Decimal("9.00"),
    )


@pytest.fixture
def bin_location(db, tenant):
    return WarehouseLocation.objects.create(
        tenant=tenant, name="Bin A-01", code="A-01",
        location_type="bin", capacity=1000, is_active=True,
    )


@pytest.fixture
def grn(db, tenant, po, user):
    return GoodsReceiptNote.objects.create(
        tenant=tenant, purchase_order=po,
        received_date=date(2026, 1, 2),
        received_by=user, created_by=user,
    )


@pytest.fixture
def completed_grn_full(db, tenant, po, po_item, product, user):
    g = GoodsReceiptNote.objects.create(
        tenant=tenant, purchase_order=po,
        received_date=date(2026, 1, 2), status="completed",
        received_by=user, created_by=user,
    )
    GoodsReceiptNoteItem.objects.create(
        tenant=tenant, grn=g, po_item=po_item, product=product,
        quantity_received=po_item.quantity,
    )
    return g
