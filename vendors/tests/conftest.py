import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Tenant
from vendors.models import Vendor, VendorPerformance, VendorContract, VendorCommunication

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
        username="vendor_qa",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    """A non-admin tenant user — used to prove D-10 gate works."""
    return User.objects.create_user(
        username="vendor_qa_reader",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=False,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="vendor_qa_other",
        password="qa_pass_123!",
        tenant=other_tenant,
        is_tenant_admin=True,
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
def vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant,
        company_name="Acme Corp",
        email="acme@example.com",
        vendor_type="manufacturer",
        status="active",
        payment_terms="net_30",
        lead_time_days=14,
        minimum_order_quantity=10,
    )


@pytest.fixture
def foreign_vendor(db, other_tenant):
    return Vendor.objects.create(
        tenant=other_tenant,
        company_name="Foreign Co",
        status="active",
    )


@pytest.fixture
def performance(db, tenant, vendor, user):
    return VendorPerformance.objects.create(
        tenant=tenant, vendor=vendor,
        review_date=date.today(),
        delivery_rating=5, quality_rating=4, compliance_rating=5,
        defect_rate=Decimal("1.20"),
        on_time_delivery_rate=Decimal("97.50"),
        reviewed_by=user,
    )


@pytest.fixture
def contract(db, tenant, vendor):
    return VendorContract.objects.create(
        tenant=tenant, vendor=vendor,
        contract_number="CON-001", title="Annual Supply",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        payment_terms="net_30", lead_time_days=14, moq=100,
        contract_value=Decimal("100000.00"),
        status="active",
    )


@pytest.fixture
def communication(db, tenant, vendor, user):
    return VendorCommunication.objects.create(
        tenant=tenant, vendor=vendor,
        communication_type="email",
        subject="Kickoff email",
        message="Welcome onboard.",
        contact_person="John Smith",
        communicated_by=user,
        communication_date=timezone.now(),
    )
