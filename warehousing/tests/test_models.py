"""Unit tests — model invariants and computed properties."""
import pytest
from decimal import Decimal

from warehousing.models import Warehouse, Bin, CrossDockOrder


@pytest.mark.django_db
class TestWarehouseAutoCode:
    def test_auto_code_first(self, tenant):
        w = Warehouse.objects.create(tenant=tenant, name="A")
        assert w.code == "WH-00001"

    def test_auto_code_increments(self, tenant):
        Warehouse.objects.create(tenant=tenant, name="A")
        w2 = Warehouse.objects.create(tenant=tenant, name="B")
        assert w2.code == "WH-00002"

    def test_auto_code_per_tenant(self, tenant, other_tenant):
        Warehouse.objects.create(tenant=tenant, name="A")
        w = Warehouse.objects.create(tenant=other_tenant, name="B")
        assert w.code == "WH-00001"

    def test_explicit_code_preserved(self, tenant):
        w = Warehouse.objects.create(tenant=tenant, code="CUSTOM-01", name="A")
        assert w.code == "CUSTOM-01"


@pytest.mark.django_db
class TestBinProperties:
    def test_utilization_percentage_half(self, bin_obj):
        bin_obj.current_weight = Decimal("50.00")
        bin_obj.current_volume = Decimal("1.25")
        bin_obj.current_quantity = 25
        bin_obj.save()
        assert bin_obj.utilization_percentage == 50.0

    def test_utilization_zero_caps(self, tenant, zone):
        b = Bin.objects.create(
            tenant=tenant, zone=zone, name="Empty", code="BIN-EMPTY",
            bin_type="standard",
        )
        assert b.utilization_percentage == 0

    def test_available_weight_clamps_over_capacity(self, bin_obj):
        bin_obj.current_weight = Decimal("200.00")
        assert bin_obj.available_weight == 0

    def test_available_weight_normal(self, bin_obj):
        bin_obj.current_weight = Decimal("30.00")
        assert bin_obj.available_weight == Decimal("70.00")

    def test_available_volume_zero_max(self, tenant, zone):
        b = Bin.objects.create(
            tenant=tenant, zone=zone, name="V", code="BIN-V",
            bin_type="standard",
        )
        assert b.available_volume == 0

    def test_location_path_with_rack(self, bin_obj):
        path = bin_obj.location_path
        assert path.startswith(bin_obj.zone.warehouse.code)
        assert bin_obj.code in path
        assert bin_obj.rack.code in path

    def test_location_path_floor_bin(self, tenant, zone):
        b = Bin.objects.create(
            tenant=tenant, zone=zone, name="Floor", code="BIN-FLR",
            bin_type="pallet",
        )
        path = b.location_path
        # Floor bin: path is warehouse > zone > bin (no aisle, no rack)
        assert path.split(" > ") == [zone.warehouse.code, zone.code, b.code]


TRANSITIONS_OK = [
    ("pending", "in_transit"),
    ("pending", "cancelled"),
    ("in_transit", "at_dock"),
    ("in_transit", "cancelled"),
    ("at_dock", "processing"),
    ("at_dock", "cancelled"),
    ("processing", "dispatched"),
    ("processing", "cancelled"),
    ("dispatched", "completed"),
    ("cancelled", "pending"),
]

TRANSITIONS_BAD = [
    ("pending", "completed"),
    ("pending", "at_dock"),
    ("pending", "dispatched"),
    ("completed", "pending"),
    ("completed", "cancelled"),
    ("dispatched", "cancelled"),
    ("dispatched", "processing"),
    ("at_dock", "completed"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", TRANSITIONS_OK)
def test_transition_allowed(crossdock, src, dst):
    crossdock.status = src
    assert crossdock.can_transition_to(dst)


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", TRANSITIONS_BAD)
def test_transition_denied(crossdock, src, dst):
    crossdock.status = src
    assert not crossdock.can_transition_to(dst)


@pytest.mark.django_db
def test_crossdock_auto_number(tenant):
    o = CrossDockOrder.objects.create(
        tenant=tenant, source="S", destination="D",
    )
    assert o.order_number == "CD-00001"
