import pytest
from django.urls import reverse

from inventory.models import StockLevel, StockAdjustment


@pytest.mark.django_db
class TestStockLevelList:
    def test_anonymous_redirected(self, client):
        r = client.get(reverse('inventory:stock_level_list'))
        assert r.status_code == 302
        assert '/accounts/login/' in r['Location']

    def test_list_renders(self, client_logged_in, stock_level):
        r = client_logged_in.get(reverse('inventory:stock_level_list'))
        assert r.status_code == 200
        assert stock_level.product.sku.encode() in r.content

    def test_invalid_warehouse_param_ignored(self, client_logged_in, stock_level):
        """Regression for D-11 — coerce int or ignore."""
        r = client_logged_in.get(
            reverse('inventory:stock_level_list') + '?warehouse=abc')
        assert r.status_code == 200
        assert stock_level.product.sku.encode() in r.content

    def test_tenant_isolation(
        self, client_logged_in, stock_level, other_tenant, product, warehouse
    ):
        # Other-tenant stock should not appear
        from warehousing.models import Warehouse
        from catalog.models import Category, Product
        other_cat = Category.objects.create(tenant=other_tenant, name="Cat")
        other_product = Product.objects.create(
            tenant=other_tenant, sku='OTHER-X', name='Other',
            category=other_cat, purchase_cost=1, retail_price=1, status='active',
        )
        other_wh = Warehouse.objects.create(
            tenant=other_tenant, code='OWH', name='Other', is_active=True,
        )
        StockLevel.objects.create(
            tenant=other_tenant, product=other_product, warehouse=other_wh,
            on_hand=7,
        )
        r = client_logged_in.get(reverse('inventory:stock_level_list'))
        assert b'OTHER-X' not in r.content


@pytest.mark.django_db
class TestStockLevelDetail:
    def test_cross_tenant_returns_404(
        self, client, other_tenant_user, stock_level
    ):
        client.force_login(other_tenant_user)
        r = client.get(reverse('inventory:stock_level_detail', args=[stock_level.pk]))
        assert r.status_code == 404


@pytest.mark.django_db
class TestStockAdjust:
    def test_admin_increase_happy_path(self, client, admin_user, stock_level):
        client.force_login(admin_user)
        r = client.post(
            reverse('inventory:stock_adjust', args=[stock_level.pk]),
            {'adjustment_type': 'increase', 'quantity': '10', 'reason': 'return', 'notes': ''},
        )
        assert r.status_code == 302
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 60
        assert StockAdjustment.objects.filter(stock_level=stock_level).count() == 1

    def test_admin_over_decrement_form_invalid(self, client, admin_user, stock_level):
        """Regression for D-01 — form rejects, no StockAdjustment persists, no clamp."""
        client.force_login(admin_user)
        r = client.post(
            reverse('inventory:stock_adjust', args=[stock_level.pk]),
            {'adjustment_type': 'decrease', 'quantity': '9999', 'reason': 'theft', 'notes': ''},
        )
        # Form invalid → template re-renders (200), no redirect
        assert r.status_code == 200
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 50
        assert StockAdjustment.objects.count() == 0

    def test_atomic_rolls_back_on_model_error(
        self, client, admin_user, stock_level, monkeypatch
    ):
        """Regression for D-06 — if apply_adjustment raises, the adjustment row rolls back."""
        client.force_login(admin_user)

        def boom(self):
            raise RuntimeError('DB down')
        monkeypatch.setattr(StockAdjustment, 'apply_adjustment', boom)

        with pytest.raises(RuntimeError):
            client.post(
                reverse('inventory:stock_adjust', args=[stock_level.pk]),
                {'adjustment_type': 'increase', 'quantity': '5', 'reason': 'return'},
            )
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 50
        assert StockAdjustment.objects.count() == 0
