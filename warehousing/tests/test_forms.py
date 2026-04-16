"""Form-level negative coverage — regression guards for D-01..D-10 fixes."""
import pytest
from datetime import timedelta
from django.utils import timezone

from warehousing.forms import (
    ZoneForm, AisleForm, RackForm, BinForm,
    CrossDockOrderForm, CrossDockItemForm,
)
from warehousing.models import Zone, Aisle, Rack, Warehouse


def _zone_data(warehouse, **overrides):
    data = {
        'warehouse': warehouse.pk,
        'name': 'Z', 'code': 'Z-NEW',
        'zone_type': 'storage',
        'temperature_controlled': False,
        'is_active': True,
        'description': '',
    }
    data.update(overrides)
    return data


def _bin_data(zone, **overrides):
    data = {
        'zone': zone.pk, 'rack': '',
        'name': 'B', 'code': 'BIN-NEW',
        'bin_type': 'standard',
        'max_weight': '10', 'max_volume': '1', 'max_quantity': 1,
        'is_active': True,
    }
    data.update(overrides)
    return data


# ── D-01 — duplicate code rejected at form layer ──────────────────────────

@pytest.mark.django_db
class TestZoneFormUniqueCode:
    def test_duplicate_code_same_tenant_rejected(self, tenant, warehouse, zone):
        form = ZoneForm(data=_zone_data(warehouse, code=zone.code), tenant=tenant)
        assert not form.is_valid()
        assert 'code' in form.errors

    def test_duplicate_case_insensitive(self, tenant, warehouse, zone):
        form = ZoneForm(data=_zone_data(warehouse, code=zone.code.lower()), tenant=tenant)
        assert not form.is_valid()

    def test_editing_zone_with_own_code_allowed(self, tenant, warehouse, zone):
        form = ZoneForm(
            data=_zone_data(warehouse, code=zone.code, name=zone.name),
            instance=zone, tenant=tenant,
        )
        assert form.is_valid(), form.errors

    def test_same_code_different_tenant_allowed(self, other_tenant, zone):
        wh2 = Warehouse.objects.create(tenant=other_tenant, name="B")
        form = ZoneForm(data=_zone_data(wh2, code=zone.code), tenant=other_tenant)
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestAisleFormUniqueCode:
    def test_duplicate_aisle_code_rejected(self, tenant, aisle):
        form = AisleForm(
            data={'zone': aisle.zone.pk, 'name': 'Dup', 'code': aisle.code, 'is_active': True},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'code' in form.errors


@pytest.mark.django_db
class TestRackFormUniqueCode:
    def test_duplicate_rack_code_rejected(self, tenant, rack):
        form = RackForm(
            data={'aisle': rack.aisle.pk, 'name': 'Dup', 'code': rack.code,
                  'levels': 1, 'max_weight_capacity': '100', 'is_active': True},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'code' in form.errors


@pytest.mark.django_db
class TestBinFormUniqueCode:
    def test_duplicate_bin_code_rejected(self, tenant, zone, bin_obj):
        form = BinForm(data=_bin_data(zone, code=bin_obj.code), tenant=tenant)
        assert not form.is_valid()
        assert 'code' in form.errors


# ── D-02 — temperature inversion ──────────────────────────────────────────

@pytest.mark.django_db
class TestZoneFormTemperature:
    def test_temp_min_gt_max_rejected(self, tenant, warehouse):
        form = ZoneForm(data=_zone_data(
            warehouse, code='Z-TEMP-1', temperature_controlled=True,
            temperature_min='50', temperature_max='-10',
        ), tenant=tenant)
        assert not form.is_valid()

    def test_temp_controlled_without_min_max_rejected(self, tenant, warehouse):
        form = ZoneForm(data=_zone_data(
            warehouse, code='Z-TEMP-2', temperature_controlled=True,
        ), tenant=tenant)
        assert not form.is_valid()

    def test_temp_controlled_valid_range(self, tenant, warehouse):
        form = ZoneForm(data=_zone_data(
            warehouse, code='Z-TEMP-OK', temperature_controlled=True,
            temperature_min='-20', temperature_max='5',
        ), tenant=tenant)
        assert form.is_valid(), form.errors


# ── D-03 — negative capacities ────────────────────────────────────────────

@pytest.mark.django_db
class TestBinFormNegativeCapacity:
    def test_negative_max_weight_rejected(self, tenant, zone):
        form = BinForm(data=_bin_data(zone, code='BIN-NEG-W', max_weight='-1'), tenant=tenant)
        assert not form.is_valid()
        assert 'max_weight' in form.errors

    def test_negative_max_volume_rejected(self, tenant, zone):
        form = BinForm(data=_bin_data(zone, code='BIN-NEG-V', max_volume='-1'), tenant=tenant)
        assert not form.is_valid()
        assert 'max_volume' in form.errors


@pytest.mark.django_db
class TestRackFormNegativeCapacity:
    def test_negative_max_weight_capacity_rejected(self, tenant, aisle):
        form = RackForm(
            data={'aisle': aisle.pk, 'name': 'R', 'code': 'R-NEG',
                  'levels': 1, 'max_weight_capacity': '-10', 'is_active': True},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'max_weight_capacity' in form.errors


# ── D-04 — zone/rack mismatch ─────────────────────────────────────────────

@pytest.mark.django_db
class TestBinFormZoneRackMismatch:
    def test_rack_from_other_zone_rejected(self, tenant, warehouse, rack):
        other_zone = Zone.objects.create(
            tenant=tenant, warehouse=warehouse,
            name="Other", code="Z-OTHER", zone_type="storage",
        )
        form = BinForm(
            data=_bin_data(other_zone, code='BIN-MIX', rack=rack.pk),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'rack' in form.errors

    def test_matching_zone_rack_allowed(self, tenant, zone, rack):
        form = BinForm(
            data=_bin_data(zone, code='BIN-MATCH', rack=rack.pk),
            tenant=tenant,
        )
        assert form.is_valid(), form.errors

    def test_floor_bin_no_rack_allowed(self, tenant, zone):
        form = BinForm(
            data=_bin_data(zone, code='BIN-FLOOR', rack=''),
            tenant=tenant,
        )
        assert form.is_valid(), form.errors


# ── D-09 — qty must be >= 1 ───────────────────────────────────────────────

@pytest.mark.django_db
class TestCrossDockItemForm:
    def test_quantity_zero_rejected(self):
        form = CrossDockItemForm(data={
            'product': '', 'description': 'x', 'quantity': 0,
            'weight': '0', 'volume': '0',
        })
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_negative_weight_rejected(self):
        form = CrossDockItemForm(data={
            'product': '', 'description': 'x', 'quantity': 1,
            'weight': '-1', 'volume': '0',
        })
        assert not form.is_valid()
        assert 'weight' in form.errors


# ── D-10 — scheduled_arrival > scheduled_departure ────────────────────────

@pytest.mark.django_db
class TestCrossDockOrderSchedule:
    def test_arrival_after_departure_rejected(self, tenant):
        now = timezone.now()
        form = CrossDockOrderForm(data={
            'source': 'A', 'destination': 'B', 'priority': 'normal',
            'scheduled_arrival': now.strftime('%Y-%m-%dT%H:%M'),
            'scheduled_departure': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'dock_door': '', 'notes': '',
        }, tenant=tenant)
        assert not form.is_valid()

    def test_valid_schedule_accepted(self, tenant):
        now = timezone.now()
        form = CrossDockOrderForm(data={
            'source': 'A', 'destination': 'B', 'priority': 'normal',
            'scheduled_arrival': now.strftime('%Y-%m-%dT%H:%M'),
            'scheduled_departure': (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
            'dock_door': 'Dock 1', 'notes': '',
        }, tenant=tenant)
        assert form.is_valid(), form.errors
