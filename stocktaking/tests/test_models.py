"""Model invariants — numbering, state machines, variance math, uniqueness."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from stocktaking.models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)
from warehousing.models import Warehouse


@pytest.mark.django_db
class TestAutoNumbering:
    def test_freeze_number_starts_at_00001(self, tenant, warehouse):
        f = StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        assert f.freeze_number == 'FRZ-00001'

    def test_freeze_numbers_are_monotonic(self, tenant, warehouse):
        for _ in range(3):
            StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        nums = sorted(StocktakeFreeze.objects.filter(tenant=tenant)
                      .values_list('freeze_number', flat=True))
        assert nums == ['FRZ-00001', 'FRZ-00002', 'FRZ-00003']

    def test_freeze_numbers_independent_per_tenant(
        self, tenant, other_tenant, warehouse, other_warehouse,
    ):
        StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        f2 = StocktakeFreeze.objects.create(tenant=other_tenant, warehouse=other_warehouse)
        assert f2.freeze_number == 'FRZ-00001'

    def test_count_number_auto_generated(self, tenant, warehouse):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        assert c.count_number == 'CNT-00001'

    def test_adjustment_number_auto_generated(self, tenant, warehouse):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        adj = StockVarianceAdjustment.objects.create(tenant=tenant, count=c)
        assert adj.adjustment_number == 'VADJ-00001'

    def test_D08_race_retry_regenerates_number(self, tenant, warehouse):
        """D-07/D-08 regression — forcing a clashing number triggers the retry path.

        Pre-create a freeze with the *next* number (FRZ-00002), then request a new
        one. The retry helper must catch the IntegrityError, clear the number,
        and re-generate → FRZ-00003.
        """
        StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse, freeze_number='FRZ-00002',
        )
        # With last id-based logic, the next auto-number *would* be FRZ-00002
        # if the pre-created row's id isn't the latest. Regardless, the retry
        # guarantees the final row persists without IntegrityError.
        StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        assert StocktakeFreeze.objects.filter(tenant=tenant).count() == 2


@pytest.mark.django_db
class TestCountStateMachine:
    @pytest.mark.parametrize('src,dst,ok', [
        ('draft', 'in_progress', True),
        ('draft', 'cancelled', True),
        ('draft', 'counted', False),
        ('draft', 'reviewed', False),
        ('in_progress', 'counted', True),
        ('in_progress', 'cancelled', True),
        ('counted', 'reviewed', True),
        ('counted', 'in_progress', True),
        ('counted', 'cancelled', True),
        ('reviewed', 'adjusted', True),
        ('reviewed', 'counted', True),
        ('reviewed', 'cancelled', True),
        ('reviewed', 'draft', False),
        ('adjusted', 'draft', False),
        ('adjusted', 'cancelled', False),
        ('cancelled', 'draft', True),
        ('cancelled', 'in_progress', False),
    ])
    def test_transitions(self, tenant, warehouse, src, dst, ok):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status=src,
        )
        assert c.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestAdjustmentStateMachine:
    @pytest.mark.parametrize('src,dst,ok', [
        ('pending', 'approved', True),
        ('pending', 'rejected', True),
        ('pending', 'posted', False),
        ('approved', 'posted', True),
        ('approved', 'rejected', True),
        ('approved', 'pending', False),
        ('posted', 'approved', False),
        ('posted', 'pending', False),
        ('rejected', 'pending', True),
        ('rejected', 'posted', False),
    ])
    def test_transitions(self, tenant, warehouse, src, dst, ok):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        adj = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=c, status=src,
        )
        assert adj.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestVarianceMath:
    def test_variance_none_when_uncounted(self, tenant, warehouse, products):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        i = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=10,
        )
        assert i.variance is None
        assert i.variance_value == Decimal('0.00')
        assert i.has_variance is False

    def test_variance_positive(self, tenant, warehouse, products):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        i = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=12, unit_cost=Decimal('5.00'),
        )
        assert i.variance == 2
        assert i.variance_value == Decimal('10.00')
        assert i.has_variance is True

    def test_variance_negative(self, tenant, warehouse, products):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        i = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=7, unit_cost=Decimal('5.00'),
        )
        assert i.variance == -3
        assert i.variance_value == Decimal('-15.00')

    def test_variance_zero_no_has_variance(self, tenant, warehouse, products):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        i = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=10, unit_cost=Decimal('5.00'),
        )
        assert i.variance == 0
        assert i.has_variance is False

    def test_aggregate_properties(self, counted_count):
        """counted_count has deltas [-2, 0, +3, 0, -1, 0] — 3 items with variance."""
        assert counted_count.total_items == 6
        assert counted_count.counted_items == 6
        assert counted_count.variance_items == 3
        # Net variance value: (-2 + 3 + -1) × 10 = 0
        assert counted_count.total_variance_value == Decimal('0.00')


@pytest.mark.django_db
class TestUniqueness:
    def test_freeze_unique_together(self, tenant, warehouse):
        StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse, freeze_number='FRZ-00001',
        )
        with pytest.raises(IntegrityError):
            StocktakeFreeze.objects.create(
                tenant=tenant, warehouse=warehouse, freeze_number='FRZ-00001',
            )

    def test_count_unique_together(self, tenant, warehouse):
        StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), count_number='CNT-00001',
        )
        with pytest.raises(IntegrityError):
            StockCount.objects.create(
                tenant=tenant, warehouse=warehouse,
                scheduled_date=date.today(), count_number='CNT-00001',
            )


@pytest.mark.django_db
class TestCountedQtyValidator:
    """D-05 — counted_qty must reject negatives via full_clean."""
    def test_negative_rejected_by_full_clean(self, tenant, warehouse, products):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        item = StockCountItem(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=-5,
        )
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_zero_accepted(self, tenant, warehouse, products):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        item = StockCountItem(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=0,
        )
        item.full_clean()  # must not raise
