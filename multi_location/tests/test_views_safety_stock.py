import pytest
from django.urls import reverse

from multi_location.models import LocationSafetyStockRule


@pytest.mark.django_db
class TestSafetyStockList:
    def test_list_200(self, client_logged_in):
        assert client_logged_in.get(
            reverse("multi_location:safety_stock_rule_list")
        ).status_code == 200

    @pytest.mark.parametrize("param", ["location", "product"])
    @pytest.mark.parametrize("value", ["abc", "9" * 25])
    def test_non_numeric_filter(self, client_logged_in, param, value):
        """Regression for D-01."""
        r = client_logged_in.get(f"/multi-location/safety-stock-rules/?{param}={value}")
        assert r.status_code == 200

    def test_filter_by_product(self, client_logged_in, tenant, store, product):
        LocationSafetyStockRule.objects.create(
            tenant=tenant, location=store, product=product,
            safety_stock_qty=1, reorder_point=2,
        )
        r = client_logged_in.get(
            f"/multi-location/safety-stock-rules/?product={product.pk}"
        )
        assert r.status_code == 200
        assert len(list(r.context["rules"])) == 1

    def test_pagination_retains_filters(self, client_logged_in, tenant, store, category):
        """Regression for D-10."""
        from catalog.models import Product
        for i in range(25):
            p = Product.objects.create(
                tenant=tenant, sku=f"SK{i}", name=f"P{i}",
                category=category, purchase_cost=1, retail_price=2, status="active",
            )
            LocationSafetyStockRule.objects.create(
                tenant=tenant, location=store, product=p,
                safety_stock_qty=1, reorder_point=2,
            )
        r = client_logged_in.get(
            f"/multi-location/safety-stock-rules/?location={store.pk}"
        )
        assert b"page=2" in r.content
        assert f"location={store.pk}".encode() in r.content


@pytest.mark.django_db
class TestSafetyStockMutations:
    def test_admin_can_create(self, client_logged_in, tenant, store, product):
        r = client_logged_in.post(
            reverse("multi_location:safety_stock_rule_create"),
            data={
                'location': store.pk, 'product': product.pk,
                'safety_stock_qty': 5, 'reorder_point': 10, 'max_stock_qty': 100,
                'notes': '',
            },
        )
        assert r.status_code == 302
        assert LocationSafetyStockRule.objects.filter(tenant=tenant).count() == 1

    def test_bounds_rejected_at_view_layer(self, client_logged_in, tenant, store, product):
        """Regression for D-04 — hit the full view path."""
        r = client_logged_in.post(
            reverse("multi_location:safety_stock_rule_create"),
            data={
                'location': store.pk, 'product': product.pk,
                'safety_stock_qty': 999, 'reorder_point': 10, 'max_stock_qty': 100,
                'notes': '',
            },
        )
        assert r.status_code == 200
        assert LocationSafetyStockRule.objects.filter(tenant=tenant).count() == 0

    def test_duplicate_friendly_error_not_500(self, client_logged_in, tenant, store, product):
        """Regression for D-11."""
        LocationSafetyStockRule.objects.create(
            tenant=tenant, location=store, product=product,
            safety_stock_qty=1, reorder_point=2,
        )
        r = client_logged_in.post(
            reverse("multi_location:safety_stock_rule_create"),
            data={
                'location': store.pk, 'product': product.pk,
                'safety_stock_qty': 5, 'reorder_point': 10, 'max_stock_qty': 100,
                'notes': '',
            },
        )
        assert r.status_code == 200
        assert b'already exists' in r.content
        assert LocationSafetyStockRule.objects.filter(tenant=tenant).count() == 1

    def test_non_admin_blocked_from_delete(self, staff_client, tenant, store, product):
        rule = LocationSafetyStockRule.objects.create(
            tenant=tenant, location=store, product=product,
            safety_stock_qty=1, reorder_point=2,
        )
        r = staff_client.post(
            reverse("multi_location:safety_stock_rule_delete", args=[rule.pk])
        )
        assert r.status_code == 403
        assert LocationSafetyStockRule.objects.filter(pk=rule.pk).exists()
