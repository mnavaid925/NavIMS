from decimal import Decimal
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from vendors.models import Vendor
from catalog.models import Category, Product
from purchase_orders.models import (
    PurchaseOrder, PurchaseOrderItem, ApprovalRule,
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
        username="admin_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def approver_user(db, tenant):
    return User.objects.create_user(
        username="approver_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="staff_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_user(db, other_tenant):
    return User.objects.create_user(
        username="admin_other", password="qa_pass_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant, company_name="Widgets Inc",
        email="sales@widgets.example",
        is_active=True, status="active",
    )


@pytest.fixture
def inactive_vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant, company_name="Sleepy Vendor",
        is_active=True, status="inactive",
    )


@pytest.fixture
def product(db, tenant):
    category = Category.objects.create(tenant=tenant, name="Supplies")
    return Product.objects.create(
        tenant=tenant, sku="SUP-001", name="Stapler",
        category=category, purchase_cost=10, retail_price=20,
        status="active",
    )


@pytest.fixture
def approval_rule(db, tenant):
    return ApprovalRule.objects.create(
        tenant=tenant, name="Low value",
        min_amount=Decimal("0"), max_amount=Decimal("100000.00"),
        required_approvals=1, is_active=True,
    )


@pytest.fixture
def draft_po(db, tenant, admin_user, vendor, product):
    po = PurchaseOrder.objects.create(
        tenant=tenant, vendor=vendor, order_date=date.today(),
        payment_terms="net_30", created_by=admin_user,
    )
    PurchaseOrderItem.objects.create(
        tenant=tenant, purchase_order=po, product=product,
        quantity=2, unit_price=Decimal("50.00"),
        tax_rate=Decimal("10.00"), discount=Decimal("0"),
    )
    return po


@pytest.fixture
def pending_po(db, draft_po):
    draft_po.status = "pending_approval"
    draft_po.save()
    return draft_po


@pytest.fixture
def approved_po(db, pending_po, approver_user):
    from purchase_orders.models import PurchaseOrderApproval
    PurchaseOrderApproval.objects.create(
        tenant=pending_po.tenant, purchase_order=pending_po,
        approver=approver_user, decision="approved",
    )
    pending_po.status = "approved"
    pending_po.save()
    return pending_po


def formset_payload(prefix="items", rows=None):
    """Build an inline formset POST dict with N rows."""
    rows = rows or []
    data = {
        f"{prefix}-TOTAL_FORMS": str(len(rows)),
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for i, row in enumerate(rows):
        for k, v in row.items():
            data[f"{prefix}-{i}-{k}"] = str(v)
    return data
