from datetime import date
from decimal import Decimal

import pytest

from forecasting.models import (
    DemandForecast, ReorderAlert, ReorderPoint,
    SafetyStock, SeasonalityProfile, SeasonalityPeriod,
)


@pytest.mark.django_db
class TestForecastNumbering:
    def test_first_is_fc_00001(self, tenant, product, warehouse):
        f = DemandForecast.objects.create(
            tenant=tenant, name="A", product=product, warehouse=warehouse,
        )
        assert f.forecast_number == "FC-00001"

    def test_second_increments(self, tenant, product, warehouse):
        DemandForecast.objects.create(tenant=tenant, name="A", product=product, warehouse=warehouse)
        f = DemandForecast.objects.create(tenant=tenant, name="B", product=product, warehouse=warehouse)
        assert f.forecast_number == "FC-00002"

    def test_sequence_is_unique_under_rapid_saves(self, tenant, product, warehouse):
        numbers = [
            DemandForecast.objects.create(
                tenant=tenant, name=f"F{i}", product=product, warehouse=warehouse,
            ).forecast_number
            for i in range(5)
        ]
        assert len(set(numbers)) == 5

    def test_alert_numbering(self, tenant, product, warehouse, rop):
        a1 = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse,
        )
        a2 = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse,
        )
        assert a1.alert_number == "ROA-00001"
        assert a2.alert_number == "ROA-00002"


@pytest.mark.django_db
class TestDemandForecastProperties:
    def test_total_forecast_qty_prefers_adjusted(self, tenant, product, warehouse):
        f = DemandForecast.objects.create(
            tenant=tenant, name="T", product=product, warehouse=warehouse,
        )
        f.lines.create(
            tenant=tenant, period_index=0, period_label="Jan",
            period_start_date=date(2026, 1, 1), period_end_date=date(2026, 1, 31),
            forecast_qty=100, adjusted_qty=150,
        )
        f.lines.create(
            tenant=tenant, period_index=1, period_label="Feb",
            period_start_date=date(2026, 2, 1), period_end_date=date(2026, 2, 28),
            forecast_qty=80, adjusted_qty=None,
        )
        assert f.total_forecast_qty == 230  # 150 + 80


@pytest.mark.django_db
class TestReorderPoint:
    def test_rop_formula(self, tenant, product, warehouse):
        rp = ReorderPoint(
            tenant=tenant, product=product, warehouse=warehouse,
            avg_daily_usage=Decimal("5"), lead_time_days=7, safety_stock_qty=10,
        )
        rp.recalc_rop()
        assert rp.rop_qty == 45

    def test_decimal_rounding(self, tenant, product, warehouse):
        rp = ReorderPoint(
            tenant=tenant, product=product, warehouse=warehouse,
            avg_daily_usage=Decimal("5.6"), lead_time_days=3, safety_stock_qty=0,
        )
        rp.recalc_rop()
        assert rp.rop_qty == 17

    def test_zero_lead_time(self, tenant, product, warehouse):
        rp = ReorderPoint(
            tenant=tenant, product=product, warehouse=warehouse,
            avg_daily_usage=Decimal("10"), lead_time_days=0, safety_stock_qty=5,
        )
        rp.recalc_rop()
        assert rp.rop_qty == 5


@pytest.mark.django_db
class TestAlertTransitions:
    @pytest.mark.parametrize("src,dst,ok", [
        ("new", "acknowledged", True),
        ("new", "ordered", False),
        ("new", "closed", True),
        ("acknowledged", "ordered", True),
        ("acknowledged", "closed", True),
        ("ordered", "closed", True),
        ("ordered", "acknowledged", False),
        ("closed", "acknowledged", False),
        ("closed", "ordered", False),
        ("closed", "new", False),
    ])
    def test_matrix(self, tenant, product, warehouse, rop, src, dst, ok):
        a = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status=src,
        )
        assert a.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestSafetyStockRecalc:
    def test_fixed(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="fixed", fixed_qty=25,
        )
        ss.recalc()
        assert ss.safety_stock_qty == 25

    def test_percentage(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="percentage",
            avg_demand=Decimal("10"), avg_lead_time_days=Decimal("7"),
            percentage=Decimal("20"),
        )
        ss.recalc()
        assert ss.safety_stock_qty == 14

    def test_statistical_95(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="statistical", service_level=Decimal("0.95"),
            avg_demand=Decimal("10"), demand_std_dev=Decimal("2"),
            avg_lead_time_days=Decimal("7"), lead_time_std_dev=Decimal("1"),
        )
        ss.recalc()
        # Z=1.645, variance = 7*4 + 100*1 = 128, sqrt ≈ 11.31; 1.645*11.31 ≈ 18.61 → 19
        assert ss.safety_stock_qty == 19

    def test_zero_variance(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="statistical",
        )
        ss.recalc()
        assert ss.safety_stock_qty == 0

    def test_service_level_50_gives_zero(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="statistical", service_level=Decimal("0.50"),
            avg_demand=Decimal("10"), demand_std_dev=Decimal("2"),
            avg_lead_time_days=Decimal("7"), lead_time_std_dev=Decimal("1"),
        )
        ss.recalc()
        assert ss.safety_stock_qty == 0

    def test_z_lookup_nearest_0_93_is_0_95(self):
        assert SafetyStock._lookup_z(Decimal("0.93")) == Decimal("1.645")


@pytest.mark.django_db
class TestSeasonalityMultiplier:
    def test_monthly_returns_attached_period(self, monthly_profile):
        assert monthly_profile.multiplier_for_date(date(2026, 7, 15)) == Decimal("1.50")

    def test_monthly_default_is_1(self, monthly_profile):
        assert monthly_profile.multiplier_for_date(date(2026, 3, 15)) == Decimal("1.00")

    def test_quarter_returns_q4(self, quarter_profile):
        assert quarter_profile.multiplier_for_date(date(2026, 11, 15)) == Decimal("1.40")

    def test_missing_period_falls_back_to_1(self, tenant):
        prof = SeasonalityProfile.objects.create(
            tenant=tenant, name="sparse", period_type="month",
        )
        assert prof.multiplier_for_date(date(2026, 3, 15)) == Decimal("1.00")
