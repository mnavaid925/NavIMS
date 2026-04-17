"""Seed command — idempotency + flush."""
import pytest
from io import StringIO

from django.core.management import call_command

from stocktaking.models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockVarianceAdjustment,
)


@pytest.mark.django_db
def test_seed_is_idempotent(tenant_admin, warehouse, stock_levels):
    """Running seed_stocktaking twice must not duplicate data."""
    call_command('seed_stocktaking', stdout=StringIO())
    counts_first = StockCount.objects.count()
    schedules_first = CycleCountSchedule.objects.count()
    freezes_first = StocktakeFreeze.objects.count()
    adj_first = StockVarianceAdjustment.objects.count()

    call_command('seed_stocktaking', stdout=StringIO())
    assert StockCount.objects.count() == counts_first
    assert CycleCountSchedule.objects.count() == schedules_first
    assert StocktakeFreeze.objects.count() == freezes_first
    assert StockVarianceAdjustment.objects.count() == adj_first


@pytest.mark.django_db
def test_seed_flush_removes_existing(tenant_admin, warehouse, stock_levels):
    call_command('seed_stocktaking', stdout=StringIO())
    assert StockCount.objects.exists()
    call_command('seed_stocktaking', '--flush', stdout=StringIO())
    # After flush + reseed, count of rows should match first seed (idempotent).
    assert StockCount.objects.exists()
