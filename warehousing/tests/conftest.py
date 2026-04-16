import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

from core.models import Tenant
from warehousing.models import (
    Warehouse, Zone, Aisle, Rack, Bin, CrossDockOrder,
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
        username="wh_qa",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="wh_qa_reader",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=False,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="wh_qa_other",
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
def warehouse(db, tenant):
    return Warehouse.objects.create(tenant=tenant, name="Main DC")


@pytest.fixture
def zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse,
        name="Storage", code="Z-STR-01", zone_type="storage",
    )


@pytest.fixture
def aisle(db, tenant, zone):
    return Aisle.objects.create(
        tenant=tenant, zone=zone, name="Aisle 1", code="A-01",
    )


@pytest.fixture
def rack(db, tenant, aisle):
    return Rack.objects.create(
        tenant=tenant, aisle=aisle, name="Rack 1", code="R-01-01",
        levels=4, max_weight_capacity=Decimal("500.00"),
    )


@pytest.fixture
def bin_obj(db, tenant, zone, rack):
    return Bin.objects.create(
        tenant=tenant, zone=zone, rack=rack,
        name="Bin 1", code="BIN-01-01-01",
        bin_type="standard",
        max_weight=Decimal("100.00"),
        max_volume=Decimal("2.50"),
        max_quantity=50,
    )


@pytest.fixture
def crossdock(db, tenant, user):
    return CrossDockOrder.objects.create(
        tenant=tenant, source="Vendor A", destination="Store 1",
        created_by=user,
    )
