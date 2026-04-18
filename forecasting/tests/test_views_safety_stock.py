import pytest
from django.urls import reverse

from forecasting.models import SafetyStock


@pytest.mark.django_db
class TestSafetyStockCRUD:
    def test_list(self, client_logged_in):
        r = client_logged_in.get(reverse("forecasting:safety_stock_list"))
        assert r.status_code == 200

    def test_create_with_fixed_method(self, client_logged_in, tenant, product, warehouse):
        r = client_logged_in.post(reverse("forecasting:safety_stock_create"), {
            "product": product.pk, "warehouse": warehouse.pk,
            "method": "fixed", "service_level": "0.95",
            "avg_demand": "0", "demand_std_dev": "0",
            "avg_lead_time_days": "0", "lead_time_std_dev": "0",
            "fixed_qty": "25", "percentage": "20",
            "safety_stock_qty": "0", "notes": "",
        })
        assert r.status_code == 302
        ss = SafetyStock.objects.get(tenant=tenant)
        assert ss.safety_stock_qty == 25
        assert ss.calculated_at is not None

    def test_duplicate_caught_by_form(
        self, client_logged_in, tenant, product, warehouse,
    ):
        """D-02 end-to-end."""
        SafetyStock.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        r = client_logged_in.post(reverse("forecasting:safety_stock_create"), {
            "product": product.pk, "warehouse": warehouse.pk,
            "method": "fixed", "service_level": "0.95",
            "avg_demand": "0", "demand_std_dev": "0",
            "avg_lead_time_days": "0", "lead_time_std_dev": "0",
            "fixed_qty": "5", "percentage": "20",
            "safety_stock_qty": "0", "notes": "",
        })
        assert r.status_code == 200
        assert SafetyStock.objects.filter(tenant=tenant).count() == 1

    def test_recalc_rejects_get(self, client_logged_in, tenant, product, warehouse):
        """D-05 regression."""
        ss = SafetyStock.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, method="fixed", fixed_qty=10,
        )
        r = client_logged_in.get(reverse("forecasting:safety_stock_recalc", args=[ss.pk]))
        assert r.status_code == 405

    def test_recalc_post_updates_qty(self, client_logged_in, tenant, product, warehouse):
        ss = SafetyStock.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            method="fixed", fixed_qty=30,
        )
        r = client_logged_in.post(reverse("forecasting:safety_stock_recalc", args=[ss.pk]))
        assert r.status_code == 302
        ss.refresh_from_db()
        assert ss.safety_stock_qty == 30

    def test_delete(self, client_logged_in, tenant, product, warehouse):
        ss = SafetyStock.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        r = client_logged_in.post(reverse("forecasting:safety_stock_delete", args=[ss.pk]))
        assert r.status_code == 302
        assert not SafetyStock.objects.filter(pk=ss.pk).exists()
