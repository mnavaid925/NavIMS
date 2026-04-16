import pytest
from django.urls import reverse

from inventory.models import InventoryReservation


@pytest.mark.django_db
class TestCreate:
    def test_over_reserve_blocked(
        self, client, admin_user, stock_level, product, warehouse
    ):
        """Regression for D-03."""
        client.force_login(admin_user)
        r = client.post(
            reverse('inventory:reservation_create'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity': 9999, 'reference_type': '', 'reference_number': '',
                'expires_at': '', 'notes': '',
            },
        )
        assert r.status_code == 200  # re-rendered with errors
        assert InventoryReservation.objects.count() == 0

    def test_happy_path(
        self, client, admin_user, stock_level, product, warehouse
    ):
        client.force_login(admin_user)
        r = client.post(
            reverse('inventory:reservation_create'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity': 5, 'reference_type': 'SO', 'reference_number': 'SO-1',
                'expires_at': '', 'notes': '',
            },
        )
        assert r.status_code == 302
        assert InventoryReservation.objects.filter(quantity=5).count() == 1


@pytest.mark.django_db
class TestTransition:
    def test_pending_to_confirmed_increases_allocated(
        self, client, admin_user, pending_reservation, stock_level
    ):
        client.force_login(admin_user)
        client.post(reverse(
            'inventory:reservation_transition',
            args=[pending_reservation.pk, 'confirmed'],
        ))
        pending_reservation.refresh_from_db()
        stock_level.refresh_from_db()
        assert pending_reservation.status == 'confirmed'
        assert stock_level.allocated == pending_reservation.quantity

    def test_confirmed_to_released_decreases_allocated(
        self, client, admin_user, confirmed_reservation, stock_level
    ):
        client.force_login(admin_user)
        client.post(reverse(
            'inventory:reservation_transition',
            args=[confirmed_reservation.pk, 'released'],
        ))
        confirmed_reservation.refresh_from_db()
        stock_level.refresh_from_db()
        assert confirmed_reservation.status == 'released'
        assert stock_level.allocated == 0

    def test_invalid_transition_rejected(
        self, client, admin_user, confirmed_reservation
    ):
        client.force_login(admin_user)
        # confirmed → pending is NOT allowed by VALID_TRANSITIONS
        client.post(reverse(
            'inventory:reservation_transition',
            args=[confirmed_reservation.pk, 'pending'],
        ))
        confirmed_reservation.refresh_from_db()
        assert confirmed_reservation.status == 'confirmed'

    def test_missing_stock_level_graceful(
        self, client, admin_user, pending_reservation, stock_level
    ):
        """D-17 — silent pass replaced with audit + warning; no crash."""
        stock_level.delete()
        client.force_login(admin_user)
        r = client.post(reverse(
            'inventory:reservation_transition',
            args=[pending_reservation.pk, 'confirmed'],
        ))
        assert r.status_code == 302
        pending_reservation.refresh_from_db()
        assert pending_reservation.status == 'confirmed'


@pytest.mark.django_db
class TestEditDelete:
    def test_edit_pending_ok(
        self, client, admin_user, pending_reservation, product, warehouse
    ):
        client.force_login(admin_user)
        r = client.post(
            reverse('inventory:reservation_edit', args=[pending_reservation.pk]),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity': 10, 'reference_type': '', 'reference_number': '',
                'expires_at': '', 'notes': 'updated',
            },
        )
        assert r.status_code == 302
        pending_reservation.refresh_from_db()
        assert pending_reservation.quantity == 10

    def test_delete_pending_ok(self, client, admin_user, pending_reservation):
        client.force_login(admin_user)
        pk = pending_reservation.pk
        r = client.post(reverse('inventory:reservation_delete', args=[pk]))
        assert r.status_code == 302
        assert not InventoryReservation.objects.filter(pk=pk).exists()

    def test_delete_confirmed_blocked(self, client, admin_user, confirmed_reservation):
        client.force_login(admin_user)
        client.post(reverse(
            'inventory:reservation_delete', args=[confirmed_reservation.pk]))
        assert InventoryReservation.objects.filter(pk=confirmed_reservation.pk).exists()
