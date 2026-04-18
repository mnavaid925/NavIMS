import pytest
from django.urls import reverse

from forecasting.models import DemandForecast


@pytest.mark.django_db
class TestForecastCRUD:
    def test_list_empty(self, client_logged_in):
        r = client_logged_in.get(reverse("forecasting:forecast_list"))
        assert r.status_code == 200

    def test_create_persists(self, client_logged_in, tenant, product, warehouse):
        r = client_logged_in.post(reverse("forecasting:forecast_create"), {
            "name": "Q2 widget", "product": product.pk, "warehouse": warehouse.pk,
            "method": "moving_avg", "period_type": "monthly",
            "history_periods": "6", "forecast_periods": "3",
            "confidence_pct": "80", "status": "draft", "notes": "",
        })
        assert r.status_code == 302
        f = DemandForecast.objects.get(tenant=tenant, name="Q2 widget")
        assert f.forecast_number == "FC-00001"
        assert f.created_by.username == "fc_admin"

    def test_detail_splits_history_and_future(self, client_logged_in, tenant, product, warehouse):
        from datetime import date
        f = DemandForecast.objects.create(
            tenant=tenant, name="X", product=product, warehouse=warehouse,
        )
        f.lines.create(
            tenant=tenant, period_index=-1, period_label="H1",
            period_start_date=date(2026, 1, 1), period_end_date=date(2026, 1, 31),
            historical_qty=10,
        )
        f.lines.create(
            tenant=tenant, period_index=0, period_label="F1",
            period_start_date=date(2026, 2, 1), period_end_date=date(2026, 2, 28),
            forecast_qty=12, adjusted_qty=12,
        )
        r = client_logged_in.get(reverse("forecasting:forecast_detail", args=[f.pk]))
        assert r.status_code == 200
        assert len(r.context["history_lines"]) == 1
        assert len(r.context["future_lines"]) == 1

    def test_edit_updates_name(self, client_logged_in, tenant, product, warehouse):
        f = DemandForecast.objects.create(
            tenant=tenant, name="Old", product=product, warehouse=warehouse,
        )
        r = client_logged_in.post(reverse("forecasting:forecast_edit", args=[f.pk]), {
            "name": "New name", "product": product.pk, "warehouse": warehouse.pk,
            "method": "moving_avg", "period_type": "monthly",
            "history_periods": "6", "forecast_periods": "3",
            "confidence_pct": "80", "status": "draft", "notes": "",
        })
        assert r.status_code == 302
        f.refresh_from_db()
        assert f.name == "New name"

    def test_delete_draft(self, client_logged_in, tenant, product, warehouse):
        f = DemandForecast.objects.create(
            tenant=tenant, name="gone", product=product, warehouse=warehouse, status="draft",
        )
        r = client_logged_in.post(reverse("forecasting:forecast_delete", args=[f.pk]))
        assert r.status_code == 302
        assert not DemandForecast.objects.filter(pk=f.pk).exists()

    def test_delete_approved_blocked(self, client_logged_in, tenant, product, warehouse):
        """D-17 — approved forecasts must not be deletable."""
        f = DemandForecast.objects.create(
            tenant=tenant, name="locked", product=product, warehouse=warehouse, status="approved",
        )
        r = client_logged_in.post(reverse("forecasting:forecast_delete", args=[f.pk]))
        assert r.status_code == 302
        assert DemandForecast.objects.filter(pk=f.pk).exists()


@pytest.mark.django_db
class TestForecastGenerate:
    def test_generate_no_history_creates_zero_lines(
        self, client_logged_in, tenant, product, warehouse,
    ):
        f = DemandForecast.objects.create(
            tenant=tenant, name="empty", product=product, warehouse=warehouse,
            history_periods=3, forecast_periods=2, method="moving_avg",
        )
        r = client_logged_in.post(
            reverse("forecasting:forecast_generate", args=[f.pk]),
            {"regenerate": "on"},
        )
        assert r.status_code == 302
        assert f.lines.count() == 5  # 3 history + 2 future
        history = f.lines.filter(period_index__lt=0)
        assert history.count() == 3
        assert all(l.historical_qty == 0 for l in history)

    def test_regenerate_replaces_lines(self, client_logged_in, tenant, product, warehouse):
        from datetime import date
        f = DemandForecast.objects.create(
            tenant=tenant, name="g", product=product, warehouse=warehouse,
            history_periods=2, forecast_periods=1, method="moving_avg",
        )
        f.lines.create(
            tenant=tenant, period_index=-99, period_label="stale",
            period_start_date=date(2020, 1, 1), period_end_date=date(2020, 1, 31),
            historical_qty=999,
        )
        r = client_logged_in.post(
            reverse("forecasting:forecast_generate", args=[f.pk]),
            {"regenerate": "on"},
        )
        assert r.status_code == 302
        assert not f.lines.filter(period_index=-99).exists()
        assert f.lines.count() == 3

    def test_seasonal_profile_applied(
        self, client_logged_in, tenant, product, warehouse, monthly_profile,
    ):
        f = DemandForecast.objects.create(
            tenant=tenant, name="s", product=product, warehouse=warehouse,
            history_periods=2, forecast_periods=2, method="seasonal",
            seasonality_profile=monthly_profile,
        )
        r = client_logged_in.post(
            reverse("forecasting:forecast_generate", args=[f.pk]),
            {"regenerate": "on"},
        )
        assert r.status_code == 302
        future = f.lines.filter(period_index__gte=0)
        assert future.count() == 2
