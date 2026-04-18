import pytest
from django.urls import reverse

from inventory.models import StockLevel


@pytest.mark.django_db
class TestStockVisibility:
    def test_empty_tenant(self, client_logged_in):
        r = client_logged_in.get(reverse("multi_location:stock_visibility"))
        assert r.status_code == 200
        assert r.context["stats"]["total_on_hand"] == 0

    def test_stats_roll_up(self, client_logged_in, tenant, dc, product, warehouse):
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=50, allocated=5, reorder_point=10,
        )
        r = client_logged_in.get(reverse("multi_location:stock_visibility"))
        stats = r.context["stats"]
        assert stats["total_on_hand"] == 50
        assert stats["total_allocated"] == 5
        assert stats["total_available"] == 45

    def test_low_stock_filter(self, client_logged_in, tenant, dc, product, warehouse):
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=5, allocated=0, reorder_point=10,
        )
        r = client_logged_in.get("/multi-location/stock-visibility/?low_stock=1")
        assert r.context["stats"]["low_stock_count"] == 1

    def test_location_filter_by_tree(self, client_logged_in, tenant, region, dc, product, warehouse):
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=20, reorder_point=5,
        )
        r = client_logged_in.get(
            f"/multi-location/stock-visibility/?location={region.pk}"
        )
        assert r.status_code == 200
        assert r.context["stats"]["total_on_hand"] == 20

    @pytest.mark.parametrize("value", ["abc", "../etc/passwd", "9" * 25])
    def test_non_numeric_location_filter(self, client_logged_in, value):
        """Regression for D-01."""
        r = client_logged_in.get(f"/multi-location/stock-visibility/?location={value}")
        assert r.status_code == 200

    def test_superuser_tenant_none_returns_200(self, client, db):
        """Regression: superuser (tenant=None) must not 500."""
        from django.contrib.auth import get_user_model
        U = get_user_model()
        su = U.objects.create_user("suv", password="x", tenant=None, is_superuser=True)
        client.force_login(su)
        r = client.get(reverse("multi_location:stock_visibility"))
        assert r.status_code == 200
