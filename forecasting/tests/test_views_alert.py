import pytest
from django.urls import reverse

from forecasting.models import ReorderAlert


@pytest.fixture
def new_alert(db, tenant, rop, product, warehouse):
    return ReorderAlert.objects.create(
        tenant=tenant, rop=rop, product=product, warehouse=warehouse,
        current_qty=5, rop_qty=rop.rop_qty, suggested_order_qty=30, status="new",
    )


@pytest.mark.django_db
class TestAlertStateMachine:
    def test_acknowledge_transitions(self, client_logged_in, new_alert, admin_user):
        r = client_logged_in.post(
            reverse("forecasting:alert_acknowledge", args=[new_alert.pk]),
            {"suggested_order_qty": "25", "notes": "ok"},
        )
        assert r.status_code == 302
        new_alert.refresh_from_db()
        assert new_alert.status == "acknowledged"
        assert new_alert.acknowledged_by == admin_user
        assert new_alert.acknowledged_at is not None
        assert new_alert.suggested_order_qty == 25

    def test_mark_ordered(self, client_logged_in, new_alert):
        new_alert.status = "acknowledged"
        new_alert.save()
        r = client_logged_in.post(
            reverse("forecasting:alert_mark_ordered", args=[new_alert.pk])
        )
        assert r.status_code == 302
        new_alert.refresh_from_db()
        assert new_alert.status == "ordered"

    def test_close(self, client_logged_in, new_alert):
        new_alert.status = "ordered"
        new_alert.save()
        r = client_logged_in.post(
            reverse("forecasting:alert_close", args=[new_alert.pk])
        )
        assert r.status_code == 302
        new_alert.refresh_from_db()
        assert new_alert.status == "closed"
        assert new_alert.closed_at is not None

    def test_cannot_acknowledge_closed(self, client_logged_in, new_alert):
        new_alert.status = "closed"
        new_alert.save()
        r = client_logged_in.get(
            reverse("forecasting:alert_acknowledge", args=[new_alert.pk])
        )
        assert r.status_code == 302
        new_alert.refresh_from_db()
        assert new_alert.status == "closed"


@pytest.mark.django_db
class TestAlertCsrfRegression:
    """D-05 — side-effect-on-GET must be blocked."""

    def test_mark_ordered_rejects_get(self, client_logged_in, new_alert):
        new_alert.status = "acknowledged"
        new_alert.save()
        r = client_logged_in.get(
            reverse("forecasting:alert_mark_ordered", args=[new_alert.pk])
        )
        new_alert.refresh_from_db()
        assert r.status_code == 405
        assert new_alert.status == "acknowledged"

    def test_close_rejects_get(self, client_logged_in, new_alert):
        new_alert.status = "ordered"
        new_alert.save()
        r = client_logged_in.get(
            reverse("forecasting:alert_close", args=[new_alert.pk])
        )
        new_alert.refresh_from_db()
        assert r.status_code == 405
        assert new_alert.status == "ordered"


@pytest.mark.django_db
class TestAlertDelete:
    def test_delete(self, client_logged_in, new_alert):
        r = client_logged_in.post(reverse("forecasting:alert_delete", args=[new_alert.pk]))
        assert r.status_code == 302
        assert not ReorderAlert.objects.filter(pk=new_alert.pk).exists()
