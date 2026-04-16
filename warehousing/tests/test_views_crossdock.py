"""Integration tests — cross-dock state transitions, reopen, formset."""
import pytest
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
class TestCrossDockStatus:
    def test_valid_transition_pending_to_in_transit(self, client_logged_in, crossdock):
        r = client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "in_transit"},
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "in_transit"
        assert r.status_code == 302

    def test_invalid_transition_ignored(self, client_logged_in, crossdock):
        client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "completed"},
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "pending"

    def test_status_get_redirects(self, client_logged_in, crossdock):
        r = client_logged_in.get(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
        )
        assert r.status_code == 302
        crossdock.refresh_from_db()
        assert crossdock.status == "pending"

    def test_at_dock_auto_sets_arrival(self, client_logged_in, crossdock):
        crossdock.status = "in_transit"
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "at_dock"},
        )
        crossdock.refresh_from_db()
        assert crossdock.actual_arrival is not None

    def test_dispatched_auto_sets_departure(self, client_logged_in, crossdock):
        crossdock.status = "processing"
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "dispatched"},
        )
        crossdock.refresh_from_db()
        assert crossdock.actual_departure is not None

    def test_reopen_clears_timestamps(self, client_logged_in, crossdock):
        crossdock.status = "cancelled"
        crossdock.actual_arrival = timezone.now()
        crossdock.actual_departure = timezone.now()
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_reopen", args=[crossdock.pk]),
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "pending"
        assert crossdock.actual_arrival is None
        assert crossdock.actual_departure is None

    def test_reopen_disallowed_from_completed(self, client_logged_in, crossdock):
        crossdock.status = "completed"
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_reopen", args=[crossdock.pk]),
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "completed"

    def test_edit_locked_post_pending(self, client_logged_in, crossdock):
        crossdock.status = "in_transit"
        crossdock.save()
        r = client_logged_in.get(
            reverse("warehousing:crossdock_edit", args=[crossdock.pk]),
        )
        assert r.status_code == 302

    def test_delete_locked_post_pending(self, client_logged_in, crossdock):
        crossdock.status = "in_transit"
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_delete", args=[crossdock.pk]),
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "in_transit"  # still there

    def test_delete_pending_succeeds(self, client_logged_in, crossdock):
        r = client_logged_in.post(
            reverse("warehousing:crossdock_delete", args=[crossdock.pk])
        )
        assert r.status_code == 302
