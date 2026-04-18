from io import StringIO

import pytest
from django.core.management import call_command

from forecasting.models import DemandForecast, ReorderPoint, SafetyStock


@pytest.mark.django_db
def test_seed_is_idempotent(tenant, product, warehouse, stock_level):
    out1 = StringIO()
    call_command("seed_forecasting", stdout=out1)
    first = DemandForecast.objects.filter(tenant=tenant).count()

    out2 = StringIO()
    call_command("seed_forecasting", stdout=out2)
    second = DemandForecast.objects.filter(tenant=tenant).count()

    assert first == second, "Seeder must be idempotent"
    assert "already exists" in out2.getvalue()


@pytest.mark.django_db
def test_seed_flush_resets(tenant, product, warehouse, stock_level):
    call_command("seed_forecasting", stdout=StringIO())
    assert DemandForecast.objects.filter(tenant=tenant).exists()

    out = StringIO()
    call_command("seed_forecasting", flush=True, stdout=out)
    # After --flush the seeder deletes everything, then re-seeds.
    assert DemandForecast.objects.filter(tenant=tenant).exists()
    assert "Flushing" in out.getvalue() or "flushed" in out.getvalue()


@pytest.mark.django_db
def test_seed_no_tenants_warns(db):
    from core.models import Tenant
    Tenant.objects.all().delete()
    out = StringIO()
    call_command("seed_forecasting", stdout=out)
    assert "No active tenants" in out.getvalue()
    assert not DemandForecast.objects.exists()
    assert not ReorderPoint.objects.exists()
    assert not SafetyStock.objects.exists()
