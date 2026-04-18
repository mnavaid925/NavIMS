import pytest
from django.urls import reverse

from forecasting.models import ReorderAlert, ReorderPoint


@pytest.mark.django_db
class TestReorderPointCRUD:
    def test_list(self, client_logged_in):
        r = client_logged_in.get(reverse("forecasting:rop_list"))
        assert r.status_code == 200

    def test_create_recalculates(self, client_logged_in, tenant, product, warehouse):
        r = client_logged_in.post(reverse("forecasting:rop_create"), {
            "product": product.pk, "warehouse": warehouse.pk,
            "avg_daily_usage": "5", "lead_time_days": "7",
            "safety_stock_qty": "10", "rop_qty": "0",
            "min_qty": "10", "max_qty": "100", "reorder_qty": "30",
            "is_active": "on", "notes": "",
        })
        assert r.status_code == 302
        rp = ReorderPoint.objects.get(tenant=tenant)
        assert rp.rop_qty == 45  # 5*7 + 10

    def test_duplicate_caught_by_form(
        self, client_logged_in, tenant, product, warehouse,
    ):
        """D-01 end-to-end — form error, not 500."""
        ReorderPoint.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
        )
        r = client_logged_in.post(reverse("forecasting:rop_create"), {
            "product": product.pk, "warehouse": warehouse.pk,
            "avg_daily_usage": "1", "lead_time_days": "1",
            "safety_stock_qty": "0", "rop_qty": "0",
            "min_qty": "0", "max_qty": "0", "reorder_qty": "0",
            "is_active": "on", "notes": "",
        })
        # Form re-render (200) rather than IntegrityError (500)
        assert r.status_code == 200
        assert ReorderPoint.objects.filter(tenant=tenant).count() == 1

    def test_edit_updates_last_calculated_at(
        self, client_logged_in, tenant, rop, product, warehouse,
    ):
        from django.utils import timezone
        old_ts = rop.last_calculated_at
        r = client_logged_in.post(reverse("forecasting:rop_edit", args=[rop.pk]), {
            "product": product.pk, "warehouse": warehouse.pk,
            "avg_daily_usage": "10", "lead_time_days": "7",
            "safety_stock_qty": "15", "rop_qty": "0",
            "min_qty": "15", "max_qty": "150", "reorder_qty": "40",
            "is_active": "on", "notes": "",
        })
        assert r.status_code == 302
        rop.refresh_from_db()
        assert rop.rop_qty == 85  # 10*7 + 15
        if old_ts:
            assert rop.last_calculated_at > old_ts

    def test_delete(self, client_logged_in, rop):
        r = client_logged_in.post(reverse("forecasting:rop_delete", args=[rop.pk]))
        assert r.status_code == 302
        assert not ReorderPoint.objects.filter(pk=rop.pk).exists()


@pytest.mark.django_db
class TestRopCheckAlerts:
    def test_scan_creates_alert_on_breach(
        self, client_logged_in, tenant, rop, product, warehouse, stock_level,
    ):
        stock_level.on_hand = 10
        stock_level.save()
        assert ReorderAlert.objects.filter(tenant=tenant).count() == 0
        r = client_logged_in.post(reverse("forecasting:rop_check_alerts"))
        assert r.status_code == 302
        assert ReorderAlert.objects.filter(tenant=tenant).count() == 1

    def test_scan_skips_above_rop(
        self, client_logged_in, tenant, rop, stock_level,
    ):
        stock_level.on_hand = 1000
        stock_level.save()
        client_logged_in.post(reverse("forecasting:rop_check_alerts"))
        assert ReorderAlert.objects.filter(tenant=tenant).count() == 0

    def test_scan_skips_existing_open_alert(
        self, client_logged_in, tenant, rop, product, warehouse, stock_level,
    ):
        stock_level.on_hand = 0
        stock_level.save()
        ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status="new",
        )
        client_logged_in.post(reverse("forecasting:rop_check_alerts"))
        assert ReorderAlert.objects.filter(tenant=tenant).count() == 1

    def test_scan_rejects_get(self, client_logged_in):
        """D-05 regression — GET must not mutate."""
        r = client_logged_in.get(reverse("forecasting:rop_check_alerts"))
        assert r.status_code == 405
