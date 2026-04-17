"""Integration — expiry dashboard, alert list, acknowledge (D-14 notes append)."""
import pytest
from datetime import date, timedelta
from django.urls import reverse

from lot_tracking.models import ExpiryAlert, LotBatch


@pytest.mark.django_db
class TestExpiryDashboard:
    def test_dashboard_renders(self, client_logged_in, lot):
        r = client_logged_in.get(reverse("lot_tracking:expiry_dashboard"))
        assert r.status_code == 200

    def test_dashboard_template_has_no_quarantined_literal(self):
        """D-08 regression — the misspelled 'quarantined' branch is dead code and must not reappear."""
        from django.template.loader import get_template
        src = get_template("lot_tracking/expiry_dashboard.html").origin.name
        with open(src, encoding="utf-8") as fh:
            body = fh.read()
        assert "'quarantined'" not in body, "D-08 — template still uses 'quarantined' (model value is 'quarantine')"


@pytest.mark.django_db
class TestExpiryAcknowledge:
    def test_acknowledge_sets_fields(self, client_logged_in, tenant, lot, user):
        alert = ExpiryAlert.objects.create(
            tenant=tenant, lot=lot, alert_type="approaching",
            alert_date=date.today(), days_before_expiry=10,
        )
        r = client_logged_in.post(
            reverse("lot_tracking:expiry_acknowledge", args=[alert.pk]),
            {"notes": "reviewed"},
        )
        assert r.status_code == 302
        alert.refresh_from_db()
        assert alert.is_acknowledged is True
        assert alert.acknowledged_by == user
        assert alert.acknowledged_at is not None
        assert "reviewed" in alert.notes

    def test_acknowledge_appends_instead_of_overwriting(
        self, client_logged_in, tenant, lot,
    ):
        """D-14 — prior notes must be preserved."""
        alert = ExpiryAlert.objects.create(
            tenant=tenant, lot=lot, alert_type="approaching",
            alert_date=date.today(), days_before_expiry=10,
            notes="Seeded: original narrative",
        )
        client_logged_in.post(
            reverse("lot_tracking:expiry_acknowledge", args=[alert.pk]),
            {"notes": "checked by QA"},
        )
        alert.refresh_from_db()
        assert "Seeded: original narrative" in alert.notes
        assert "checked by QA" in alert.notes

    def test_double_acknowledge_blocked(self, client_logged_in, tenant, lot):
        alert = ExpiryAlert.objects.create(
            tenant=tenant, lot=lot, alert_type="approaching",
            alert_date=date.today(), days_before_expiry=5,
            is_acknowledged=True,
        )
        r = client_logged_in.post(
            reverse("lot_tracking:expiry_acknowledge", args=[alert.pk]),
            {"notes": "again"}, follow=True,
        )
        assert r.status_code == 200
        alert.refresh_from_db()
        # Notes not appended after second ack
        assert "again" not in alert.notes
