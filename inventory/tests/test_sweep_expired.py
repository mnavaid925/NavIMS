"""D-10 — sweep_expired_reservations management command."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from inventory.models import InventoryReservation


@pytest.mark.django_db
class TestSweepExpiredReservations:
    def test_expires_stale_pending_reservation(self, pending_reservation):
        pending_reservation.expires_at = timezone.now() - timedelta(hours=1)
        pending_reservation.save()
        out = StringIO()
        call_command('sweep_expired_reservations', stdout=out)
        pending_reservation.refresh_from_db()
        assert pending_reservation.status == 'expired'

    def test_releases_allocated_on_confirmed_sweep(
        self, confirmed_reservation, stock_level
    ):
        confirmed_reservation.expires_at = timezone.now() - timedelta(hours=1)
        confirmed_reservation.save()
        assert stock_level.allocated == confirmed_reservation.quantity
        out = StringIO()
        call_command('sweep_expired_reservations', stdout=out)
        confirmed_reservation.refresh_from_db()
        stock_level.refresh_from_db()
        assert confirmed_reservation.status == 'expired'
        assert stock_level.allocated == 0

    def test_future_expiry_untouched(self, confirmed_reservation):
        confirmed_reservation.expires_at = timezone.now() + timedelta(hours=1)
        confirmed_reservation.save()
        call_command('sweep_expired_reservations', stdout=StringIO())
        confirmed_reservation.refresh_from_db()
        assert confirmed_reservation.status == 'confirmed'

    def test_no_expiry_untouched(self, pending_reservation):
        pending_reservation.expires_at = None
        pending_reservation.save()
        call_command('sweep_expired_reservations', stdout=StringIO())
        pending_reservation.refresh_from_db()
        assert pending_reservation.status == 'pending'

    def test_dry_run_does_not_mutate(self, pending_reservation):
        pending_reservation.expires_at = timezone.now() - timedelta(hours=1)
        pending_reservation.save()
        call_command('sweep_expired_reservations', '--dry-run', stdout=StringIO())
        pending_reservation.refresh_from_db()
        assert pending_reservation.status == 'pending'
