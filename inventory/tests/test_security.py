import pytest
from django.urls import reverse

from core.models import AuditLog


@pytest.mark.django_db
class TestAuthRequired:
    @pytest.mark.parametrize("url_name,args", [
        ('inventory:stock_level_list', []),
        ('inventory:stock_adjustment_list', []),
        ('inventory:stock_status_list', []),
        ('inventory:stock_status_transition_list', []),
        ('inventory:valuation_dashboard', []),
        ('inventory:reservation_list', []),
    ])
    def test_anonymous_redirected(self, client, url_name, args):
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302
        assert '/accounts/login/' in r['Location']


@pytest.mark.django_db
class TestRBAC:
    """Regression for D-05 — every sensitive mutation requires tenant admin."""

    def test_non_admin_cannot_adjust(self, client, non_admin_user, stock_level):
        client.force_login(non_admin_user)
        client.post(
            reverse('inventory:stock_adjust', args=[stock_level.pk]),
            {'adjustment_type': 'increase', 'quantity': 100, 'reason': 'other'},
        )
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 50

    def test_non_admin_cannot_transition_status(
        self, client, non_admin_user, damaged_status, product, warehouse
    ):
        client.force_login(non_admin_user)
        client.post(
            reverse('inventory:stock_status_transition'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'damaged', 'to_status': 'active',
                'quantity': 5, 'reason': 'x',
            },
        )
        damaged_status.refresh_from_db()
        assert damaged_status.quantity == 10

    def test_non_admin_cannot_recalculate(
        self, client, non_admin_user, valuation_config, cost_layers, stock_level
    ):
        client.force_login(non_admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        from inventory.models import InventoryValuation
        assert InventoryValuation.objects.count() == 0

    def test_non_admin_cannot_transition_reservation(
        self, client, non_admin_user, pending_reservation
    ):
        client.force_login(non_admin_user)
        client.post(reverse(
            'inventory:reservation_transition',
            args=[pending_reservation.pk, 'cancelled'],
        ))
        pending_reservation.refresh_from_db()
        assert pending_reservation.status == 'pending'

    def test_non_admin_cannot_create_reservation(
        self, client, non_admin_user, stock_level, product, warehouse
    ):
        client.force_login(non_admin_user)
        client.post(
            reverse('inventory:reservation_create'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity': 1, 'reference_type': '', 'reference_number': '',
                'expires_at': '', 'notes': '',
            },
        )
        from inventory.models import InventoryReservation
        assert InventoryReservation.objects.count() == 0


@pytest.mark.django_db
class TestIDOR:
    def test_stock_level_cross_tenant_404(
        self, client, other_tenant_user, stock_level
    ):
        client.force_login(other_tenant_user)
        r = client.get(reverse('inventory:stock_level_detail', args=[stock_level.pk]))
        assert r.status_code == 404

    def test_reservation_cross_tenant_404(
        self, client, other_tenant_user, pending_reservation
    ):
        client.force_login(other_tenant_user)
        r = client.get(
            reverse('inventory:reservation_detail', args=[pending_reservation.pk]))
        assert r.status_code == 404


@pytest.mark.django_db
class TestCSRFMethods:
    @pytest.mark.parametrize("url_name,arg_source", [
        ('inventory:reservation_delete', 'pk'),
        ('inventory:valuation_recalculate', None),
    ])
    def test_get_is_safe(
        self, client, admin_user, pending_reservation, url_name, arg_source
    ):
        client.force_login(admin_user)
        args = [pending_reservation.pk] if arg_source == 'pk' else []
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302


@pytest.mark.django_db
class TestXSS:
    def test_reservation_notes_escaped(
        self, client_logged_in, pending_reservation
    ):
        pending_reservation.notes = '<script>alert(1)</script>'
        pending_reservation.save()
        r = client_logged_in.get(
            reverse('inventory:reservation_detail', args=[pending_reservation.pk]))
        assert b'<script>alert(1)</script>' not in r.content


@pytest.mark.django_db
class TestAuditLog:
    """Regression for D-07 — forensic trail on every mutation."""

    def test_adjust_writes_audit(self, client, admin_user, stock_level):
        client.force_login(admin_user)
        client.post(
            reverse('inventory:stock_adjust', args=[stock_level.pk]),
            {'adjustment_type': 'increase', 'quantity': 5, 'reason': 'return'},
        )
        assert AuditLog.objects.filter(action='inventory.adjust').exists()

    def test_transition_writes_audit(
        self, client, admin_user, damaged_status, product, warehouse
    ):
        client.force_login(admin_user)
        client.post(
            reverse('inventory:stock_status_transition'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'damaged', 'to_status': 'active',
                'quantity': 5, 'reason': 'test',
            },
        )
        assert AuditLog.objects.filter(action='inventory.status_transition').exists()

    def test_reservation_transition_writes_audit(
        self, client, admin_user, pending_reservation, stock_level
    ):
        client.force_login(admin_user)
        client.post(reverse(
            'inventory:reservation_transition',
            args=[pending_reservation.pk, 'confirmed'],
        ))
        assert AuditLog.objects.filter(action='inventory.reservation_transition').exists()

    def test_recalculate_writes_audit(
        self, client, admin_user, stock_level, cost_layers, valuation_config
    ):
        stock_level.on_hand = 5
        stock_level.save()
        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        assert AuditLog.objects.filter(action='inventory.valuation_recalculate').exists()
