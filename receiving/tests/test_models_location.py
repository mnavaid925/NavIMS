import pytest
from receiving.models import WarehouseLocation


@pytest.mark.django_db
class TestWarehouseLocation:
    def test_same_code_allowed_across_tenants(self, tenant, other_tenant):
        WarehouseLocation.objects.create(tenant=tenant, name="B", code="DUP", location_type="bin")
        WarehouseLocation.objects.create(tenant=other_tenant, name="B", code="DUP", location_type="bin")
        assert WarehouseLocation.objects.count() == 2

    def test_available_capacity_clamps_at_zero(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="B", code="F", location_type="bin",
            capacity=10, current_quantity=15,
        )
        assert loc.available_capacity == 0

    def test_is_full_unlimited_capacity(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="Z", code="ZZ", location_type="zone", capacity=0,
        )
        assert loc.is_full is False

    def test_is_full_when_at_capacity(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="B", code="B", location_type="bin",
            capacity=10, current_quantity=10,
        )
        assert loc.is_full is True

    def test_full_path_nested(self, tenant):
        z = WarehouseLocation.objects.create(tenant=tenant, name="Z", code="Z1", location_type="zone")
        a = WarehouseLocation.objects.create(tenant=tenant, name="A1", code="A1", parent=z, location_type="aisle")
        b = WarehouseLocation.objects.create(tenant=tenant, name="B1", code="B11", parent=a, location_type="bin")
        assert b.full_path == "Z > A1 > B1"

    def test_full_path_root(self, tenant):
        z = WarehouseLocation.objects.create(tenant=tenant, name="Z", code="Z2", location_type="zone")
        assert z.full_path == "Z"
