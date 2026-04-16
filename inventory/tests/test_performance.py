from decimal import Decimal

import pytest
from django.urls import reverse

from inventory.models import StockLevel


@pytest.mark.django_db
def test_stock_level_list_query_budget(
    client_logged_in, tenant, warehouse, django_assert_max_num_queries
):
    """20 stock levels with 20 distinct products should not N+1 the list page."""
    from catalog.models import Category, Product
    cat = Category.objects.create(tenant=tenant, name="Bulk")
    for i in range(20):
        p = Product.objects.create(
            tenant=tenant, sku=f"B-{i:03}", name=f"B{i}",
            category=cat, purchase_cost=1, retail_price=1, status="active",
        )
        StockLevel.objects.create(
            tenant=tenant, product=p, warehouse=warehouse, on_hand=i,
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse('inventory:stock_level_list'))
        assert r.status_code == 200
