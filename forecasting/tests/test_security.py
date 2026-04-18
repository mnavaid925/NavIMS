import pytest
from django.urls import reverse

from forecasting.models import (
    DemandForecast, ReorderAlert, ReorderPoint,
    SafetyStock, SeasonalityProfile,
)


@pytest.mark.django_db
class TestAnonymousBlocked:
    @pytest.mark.parametrize("url_name,args", [
        ("forecasting:forecast_list", []),
        ("forecasting:forecast_create", []),
        ("forecasting:rop_list", []),
        ("forecasting:rop_create", []),
        ("forecasting:alert_list", []),
        ("forecasting:safety_stock_list", []),
        ("forecasting:safety_stock_create", []),
        ("forecasting:profile_list", []),
        ("forecasting:profile_create", []),
    ])
    def test_anon_redirected(self, client, url_name, args):
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302
        assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
class TestCrossTenantIDOR:
    """OWASP A01 — an admin of tenant B must not touch tenant A's forecasting data."""

    def test_forecast_detail_404(
        self, client, tenant, other_tenant_admin, product, warehouse,
    ):
        f = DemandForecast.objects.create(
            tenant=tenant, name="secret", product=product, warehouse=warehouse,
        )
        client.force_login(other_tenant_admin)
        r = client.get(reverse("forecasting:forecast_detail", args=[f.pk]))
        assert r.status_code == 404

    def test_forecast_delete_404(
        self, client, tenant, other_tenant_admin, product, warehouse,
    ):
        f = DemandForecast.objects.create(
            tenant=tenant, name="gone?", product=product, warehouse=warehouse,
        )
        client.force_login(other_tenant_admin)
        r = client.post(reverse("forecasting:forecast_delete", args=[f.pk]))
        assert r.status_code == 404
        assert DemandForecast.objects.filter(pk=f.pk).exists()

    def test_rop_delete_404(self, client, tenant, other_tenant_admin, rop):
        client.force_login(other_tenant_admin)
        r = client.post(reverse("forecasting:rop_delete", args=[rop.pk]))
        assert r.status_code == 404
        assert ReorderPoint.objects.filter(pk=rop.pk).exists()

    def test_safety_stock_delete_404(
        self, client, tenant, other_tenant_admin, product, warehouse,
    ):
        ss = SafetyStock.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
        )
        client.force_login(other_tenant_admin)
        r = client.post(reverse("forecasting:safety_stock_delete", args=[ss.pk]))
        assert r.status_code == 404
        assert SafetyStock.objects.filter(pk=ss.pk).exists()


@pytest.mark.django_db
class TestRBAC:
    """D-04 regression — non-admin tenant users must not mutate forecasting data."""

    def test_non_admin_cannot_delete_rop(self, client, non_admin_user, rop):
        client.force_login(non_admin_user)
        r = client.post(reverse("forecasting:rop_delete", args=[rop.pk]))
        assert r.status_code == 403
        assert ReorderPoint.objects.filter(pk=rop.pk).exists()

    def test_non_admin_cannot_create_forecast(
        self, client, non_admin_user, product, warehouse, tenant,
    ):
        client.force_login(non_admin_user)
        r = client.post(reverse("forecasting:forecast_create"), {
            "name": "N", "product": product.pk, "warehouse": warehouse.pk,
            "method": "moving_avg", "period_type": "monthly",
            "history_periods": "3", "forecast_periods": "2",
            "confidence_pct": "80", "status": "draft", "notes": "",
        })
        assert r.status_code == 403
        assert not DemandForecast.objects.filter(tenant=tenant).exists()

    def test_non_admin_cannot_run_scan(self, client, non_admin_user):
        client.force_login(non_admin_user)
        r = client.post(reverse("forecasting:rop_check_alerts"))
        assert r.status_code == 403

    def test_non_admin_cannot_recalc_safety_stock(
        self, client, non_admin_user, tenant, product, warehouse,
    ):
        ss = SafetyStock.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            method="fixed", fixed_qty=5,
        )
        client.force_login(non_admin_user)
        r = client.post(reverse("forecasting:safety_stock_recalc", args=[ss.pk]))
        assert r.status_code == 403

    def test_non_admin_cannot_delete_profile(
        self, client, non_admin_user, monthly_profile,
    ):
        client.force_login(non_admin_user)
        r = client.post(reverse("forecasting:profile_delete", args=[monthly_profile.pk]))
        assert r.status_code == 403
        assert SeasonalityProfile.objects.filter(pk=monthly_profile.pk).exists()


@pytest.mark.django_db
class TestXSSEscape:
    def test_forecast_name_escaped_in_detail(
        self, client_logged_in, tenant, product, warehouse,
    ):
        f = DemandForecast.objects.create(
            tenant=tenant, name="<script>alert(1)</script>",
            product=product, warehouse=warehouse,
        )
        r = client_logged_in.get(reverse("forecasting:forecast_detail", args=[f.pk]))
        assert r.status_code == 200
        assert b"<script>alert(1)</script>" not in r.content
        assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in r.content
