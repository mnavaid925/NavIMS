import pytest
from django.urls import reverse

from inventory.models import StockStatus, StockStatusTransition


@pytest.mark.django_db
class TestStatusTransitionView:
    def _post(self, client, product, warehouse, **over):
        d = {
            'product': product.pk, 'warehouse': warehouse.pk,
            'from_status': 'damaged', 'to_status': 'active',
            'quantity': 5, 'reason': 'x',
        }
        d.update(over)
        return client.post(reverse('inventory:stock_status_transition'), d)

    def test_valid_transition_applied(
        self, client, admin_user, damaged_status, product, warehouse
    ):
        client.force_login(admin_user)
        r = self._post(client, product, warehouse, quantity=5)
        assert r.status_code == 302
        damaged_status.refresh_from_db()
        active = StockStatus.objects.get(
            tenant=damaged_status.tenant, product=product,
            warehouse=warehouse, status='active',
        )
        assert damaged_status.quantity == 5
        assert active.quantity == 5
        assert StockStatusTransition.objects.count() == 1

    def test_phantom_source_blocked_at_form(
        self, client, admin_user, product, warehouse
    ):
        """Regression for D-02 — no StockStatus(damaged) exists."""
        client.force_login(admin_user)
        r = self._post(client, product, warehouse, quantity=50)
        assert r.status_code == 200  # form re-renders
        assert StockStatusTransition.objects.count() == 0
        assert not StockStatus.objects.filter(
            product=product, warehouse=warehouse, status='active',
        ).exists()

    def test_under_stocked_source_blocked(
        self, client, admin_user, damaged_status, product, warehouse
    ):
        client.force_login(admin_user)
        r = self._post(client, product, warehouse, quantity=50)
        assert r.status_code == 200
        damaged_status.refresh_from_db()
        assert damaged_status.quantity == 10


@pytest.mark.django_db
class TestStatusListAndDetail:
    def test_list_filter_by_status(
        self, client_logged_in, damaged_status
    ):
        r = client_logged_in.get(
            reverse('inventory:stock_status_list') + '?status=damaged')
        assert r.status_code == 200
        assert damaged_status.product.sku.encode() in r.content

    def test_detail_cross_tenant_404(
        self, client, other_tenant_user, damaged_status
    ):
        client.force_login(other_tenant_user)
        r = client.get(
            reverse('inventory:stock_status_detail', args=[damaged_status.pk]))
        assert r.status_code == 404
