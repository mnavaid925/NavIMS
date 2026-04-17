"""Form validation — negative matrix, tenant scoping, D-05 regression."""
from datetime import date

import pytest

from stocktaking.forms import (
    StocktakeFreezeForm, CycleCountScheduleForm,
    StockCountForm, StockCountItemCountForm, StockVarianceAdjustmentForm,
)
from stocktaking.models import StockCount, StockCountItem


@pytest.mark.django_db
class TestStocktakeFreezeForm:
    def test_valid(self, tenant, warehouse):
        form = StocktakeFreezeForm(
            {'warehouse': warehouse.pk, 'reason': 'EOY', 'notes': ''},
            tenant=tenant,
        )
        assert form.is_valid(), form.errors

    def test_warehouse_filtered_by_tenant(self, tenant, other_warehouse):
        form = StocktakeFreezeForm(tenant=tenant)
        assert other_warehouse not in form.fields['warehouse'].queryset


@pytest.mark.django_db
class TestCycleCountScheduleForm:
    def test_valid(self, tenant, warehouse):
        form = CycleCountScheduleForm({
            'name': 'weekly A', 'frequency': 'weekly', 'abc_class': 'a',
            'warehouse': warehouse.pk, 'next_run_date': '', 'is_active': 'on',
            'notes': '',
        }, tenant=tenant)
        assert form.is_valid(), form.errors

    def test_empty_name_invalid(self, tenant, warehouse):
        form = CycleCountScheduleForm({
            'name': '', 'frequency': 'weekly', 'abc_class': 'a',
            'warehouse': warehouse.pk,
        }, tenant=tenant)
        assert not form.is_valid()
        assert 'name' in form.errors

    def test_invalid_frequency(self, tenant, warehouse):
        form = CycleCountScheduleForm({
            'name': 'x', 'frequency': 'hourly', 'abc_class': 'a',
            'warehouse': warehouse.pk,
        }, tenant=tenant)
        assert not form.is_valid()
        assert 'frequency' in form.errors


@pytest.mark.django_db
class TestStockCountForm:
    def test_valid(self, tenant, warehouse):
        form = StockCountForm({
            'type': 'cycle', 'warehouse': warehouse.pk,
            'scheduled_date': '2026-04-18', 'blind_count': '',
        }, tenant=tenant)
        assert form.is_valid(), form.errors

    def test_invalid_type(self, tenant, warehouse):
        form = StockCountForm({
            'type': 'xxx', 'warehouse': warehouse.pk,
            'scheduled_date': '2026-04-18',
        }, tenant=tenant)
        assert not form.is_valid()
        assert 'type' in form.errors

    def test_missing_scheduled_date(self, tenant, warehouse):
        form = StockCountForm({
            'type': 'cycle', 'warehouse': warehouse.pk,
        }, tenant=tenant)
        assert not form.is_valid()
        assert 'scheduled_date' in form.errors


@pytest.mark.django_db
class TestStockCountItemCountForm:
    """D-05 regression — counted_qty must reject negatives."""
    def test_negative_counted_qty_rejected(self):
        form = StockCountItemCountForm(
            {'counted_qty': '-5', 'reason_code': '', 'notes': ''},
        )
        assert not form.is_valid()
        assert 'counted_qty' in form.errors

    def test_zero_counted_qty_accepted(self):
        form = StockCountItemCountForm(
            {'counted_qty': '0', 'reason_code': '', 'notes': ''},
        )
        assert form.is_valid(), form.errors

    def test_blank_counted_qty_accepted(self):
        # A blank input means "not yet counted" — must be allowed.
        form = StockCountItemCountForm(
            {'counted_qty': '', 'reason_code': '', 'notes': ''},
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestD13ZoneWarehouseCrossValidation:
    """D-13 regression — a zone attached to warehouse A must be rejected
    when the form's warehouse is B."""
    def test_stock_count_zone_from_wrong_warehouse_rejected(
        self, tenant,
    ):
        from warehousing.models import Warehouse, Zone
        wh_a = Warehouse.objects.create(tenant=tenant, code='WHA', name='A', is_active=True)
        wh_b = Warehouse.objects.create(tenant=tenant, code='WHB', name='B', is_active=True)
        zone_b = Zone.objects.create(tenant=tenant, warehouse=wh_b, code='Z1', name='Z1')

        form = StockCountForm({
            'type': 'cycle', 'warehouse': wh_a.pk, 'zone': zone_b.pk,
            'scheduled_date': '2026-04-18',
        }, tenant=tenant)
        assert not form.is_valid(), 'Zone from wrong warehouse must be rejected.'

    def test_schedule_zones_from_wrong_warehouse_rejected(
        self, tenant,
    ):
        from warehousing.models import Warehouse, Zone
        wh_a = Warehouse.objects.create(tenant=tenant, code='WHA', name='A', is_active=True)
        wh_b = Warehouse.objects.create(tenant=tenant, code='WHB', name='B', is_active=True)
        zone_b = Zone.objects.create(tenant=tenant, warehouse=wh_b, code='Z1', name='Z1')

        form = CycleCountScheduleForm({
            'name': 'x', 'frequency': 'weekly', 'abc_class': 'a',
            'warehouse': wh_a.pk, 'zones': [zone_b.pk],
        }, tenant=tenant)
        assert not form.is_valid()


@pytest.mark.django_db
class TestStockVarianceAdjustmentForm:
    def test_queryset_limited_to_counted_or_reviewed(
        self, tenant, warehouse,
    ):
        draft = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='draft',
        )
        counted = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='counted',
        )
        form = StockVarianceAdjustmentForm(tenant=tenant)
        qs = form.fields['count'].queryset
        assert counted in qs
        assert draft not in qs
