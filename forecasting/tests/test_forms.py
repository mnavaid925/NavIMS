import pytest

from forecasting.forms import (
    DemandForecastForm, ReorderPointForm, SafetyStockForm,
    SeasonalityPeriodForm, ReorderAlertAcknowledgeForm,
)
from forecasting.models import (
    DemandForecast, ReorderAlert, ReorderPoint,
    SafetyStock, SeasonalityPeriod, SeasonalityProfile,
)


def _rop_payload(product, warehouse):
    return {
        "product": product.pk, "warehouse": warehouse.pk,
        "avg_daily_usage": "1", "lead_time_days": "1",
        "safety_stock_qty": "0", "rop_qty": "0", "min_qty": "0",
        "max_qty": "0", "reorder_qty": "0", "is_active": "on", "notes": "",
    }


def _ss_payload(product, warehouse, method="fixed"):
    return {
        "product": product.pk, "warehouse": warehouse.pk,
        "method": method, "service_level": "0.95",
        "avg_demand": "0", "demand_std_dev": "0",
        "avg_lead_time_days": "0", "lead_time_std_dev": "0",
        "fixed_qty": "5", "percentage": "20",
        "safety_stock_qty": "0", "notes": "",
    }


def _fc_payload(product, warehouse, **overrides):
    data = {
        "name": "X", "product": product.pk, "warehouse": warehouse.pk,
        "method": "moving_avg", "period_type": "monthly",
        "history_periods": "6", "forecast_periods": "3",
        "confidence_pct": "80", "status": "draft", "notes": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestReorderPointForm:
    """D-01 regression — duplicate must fail at form level."""

    def test_valid_create(self, tenant, product, warehouse):
        form = ReorderPointForm(data=_rop_payload(product, warehouse), tenant=tenant)
        assert form.is_valid(), form.errors

    def test_duplicate_rejected(self, tenant, product, warehouse):
        ReorderPoint.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        form = ReorderPointForm(data=_rop_payload(product, warehouse), tenant=tenant)
        assert not form.is_valid()
        assert "already exists" in str(form.errors)

    def test_edit_of_same_row_is_allowed(self, tenant, product, warehouse):
        rp = ReorderPoint.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        form = ReorderPointForm(
            data=_rop_payload(product, warehouse), instance=rp, tenant=tenant,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestSafetyStockForm:
    """D-02 regression — duplicate must fail at form level."""

    def test_valid_create(self, tenant, product, warehouse):
        form = SafetyStockForm(data=_ss_payload(product, warehouse), tenant=tenant)
        assert form.is_valid(), form.errors

    def test_duplicate_rejected(self, tenant, product, warehouse):
        SafetyStock.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        form = SafetyStockForm(data=_ss_payload(product, warehouse), tenant=tenant)
        assert not form.is_valid()
        assert "already exists" in str(form.errors)


@pytest.mark.django_db
class TestSeasonalityPeriodBounds:
    """D-06 regression."""

    def test_monthly_period_13_rejected(self, tenant, monthly_profile):
        sp = SeasonalityPeriod(profile=monthly_profile, tenant=tenant)
        form = SeasonalityPeriodForm(
            data={"period_number": "13", "period_label": "x", "demand_multiplier": "1.00", "notes": ""},
            instance=sp,
        )
        assert not form.is_valid()

    def test_quarter_period_5_rejected(self, tenant, quarter_profile):
        sp = SeasonalityPeriod(profile=quarter_profile, tenant=tenant)
        form = SeasonalityPeriodForm(
            data={"period_number": "5", "period_label": "x", "demand_multiplier": "1.00", "notes": ""},
            instance=sp,
        )
        assert not form.is_valid()

    def test_negative_multiplier_rejected(self, tenant, monthly_profile):
        sp = SeasonalityPeriod(profile=monthly_profile, tenant=tenant)
        form = SeasonalityPeriodForm(
            data={"period_number": "1", "period_label": "x", "demand_multiplier": "-1", "notes": ""},
            instance=sp,
        )
        assert not form.is_valid()

    def test_valid_monthly_period(self, tenant, monthly_profile):
        sp = SeasonalityPeriod(profile=monthly_profile, tenant=tenant)
        form = SeasonalityPeriodForm(
            data={"period_number": "6", "period_label": "Jun", "demand_multiplier": "1.20", "notes": ""},
            instance=sp,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestDemandForecastForm:
    """D-07 regression — zero periods rejected."""

    def test_zero_history_rejected(self, tenant, product, warehouse):
        form = DemandForecastForm(
            data=_fc_payload(product, warehouse, history_periods="0"), tenant=tenant,
        )
        assert not form.is_valid()

    def test_zero_forecast_rejected(self, tenant, product, warehouse):
        form = DemandForecastForm(
            data=_fc_payload(product, warehouse, forecast_periods="0"), tenant=tenant,
        )
        assert not form.is_valid()

    def test_confidence_over_100_rejected(self, tenant, product, warehouse):
        form = DemandForecastForm(
            data=_fc_payload(product, warehouse, confidence_pct="101"), tenant=tenant,
        )
        assert not form.is_valid()


@pytest.mark.django_db
class TestReorderAlertAcknowledgeForm:
    """D-08 regression — form rejects non-transitionable statuses."""

    def test_closed_alert_rejected(self, tenant, rop, product, warehouse):
        closed = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status="closed",
        )
        form = ReorderAlertAcknowledgeForm(
            data={"suggested_order_qty": "5", "notes": ""}, instance=closed,
        )
        assert not form.is_valid()

    def test_new_alert_accepted(self, tenant, rop, product, warehouse):
        new = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status="new",
        )
        form = ReorderAlertAcknowledgeForm(
            data={"suggested_order_qty": "5", "notes": ""}, instance=new,
        )
        assert form.is_valid()
