import pytest

from receiving.models import PutawayTask, WarehouseLocation


@pytest.mark.django_db
class TestSuggestLocation:
    def test_best_fit_picks_smallest_sufficient(self, tenant):
        loose = WarehouseLocation.objects.create(
            tenant=tenant, name="B1", code="B1", location_type="bin",
            capacity=200, current_quantity=0, is_active=True,
        )
        tight = WarehouseLocation.objects.create(
            tenant=tenant, name="B2", code="B2", location_type="bin",
            capacity=100, current_quantity=0, is_active=True,
        )
        WarehouseLocation.objects.create(
            tenant=tenant, name="B3", code="B3", location_type="bin",
            capacity=500, current_quantity=0, is_active=True,
        )
        picked = PutawayTask.suggest_location(tenant, 50)
        assert picked == tight
        assert loose != tight

    def test_returns_none_when_no_fit(self, tenant):
        WarehouseLocation.objects.create(
            tenant=tenant, name="B1", code="B1", location_type="bin",
            capacity=10, current_quantity=0, is_active=True,
        )
        assert PutawayTask.suggest_location(tenant, 9999) is None

    def test_excludes_inactive(self, tenant):
        WarehouseLocation.objects.create(
            tenant=tenant, name="B1", code="B1", location_type="bin",
            capacity=500, current_quantity=0, is_active=False,
        )
        assert PutawayTask.suggest_location(tenant, 10) is None

    def test_excludes_non_bin_types(self, tenant):
        WarehouseLocation.objects.create(
            tenant=tenant, name="Z", code="Z", location_type="zone",
            capacity=500, current_quantity=0, is_active=True,
        )
        assert PutawayTask.suggest_location(tenant, 10) is None

    def test_tenant_scoped(self, tenant, other_tenant):
        WarehouseLocation.objects.create(
            tenant=other_tenant, name="OB", code="OB", location_type="bin",
            capacity=500, current_quantity=0, is_active=True,
        )
        assert PutawayTask.suggest_location(tenant, 10) is None
