from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Category, Product
from forecasting.models import DemandForecast, ReorderAlert, ReorderPoint, SafetyStock
from inventory.models import StockLevel


@pytest.mark.django_db
def test_forecast_list_query_budget(
    client_logged_in, tenant, warehouse, django_assert_max_num_queries,
):
    cat = Category.objects.create(tenant=tenant, name="Bulk")
    for i in range(20):
        p = Product.objects.create(
            tenant=tenant, sku=f"FB-{i:03}", name=f"Bulk {i}",
            category=cat, purchase_cost=1, retail_price=1, status="active",
        )
        DemandForecast.objects.create(
            tenant=tenant, name=f"F{i}", product=p, warehouse=warehouse,
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("forecasting:forecast_list"))
    assert r.status_code == 200


@pytest.mark.django_db
def test_alert_list_query_budget(
    client_logged_in, tenant, warehouse, rop, product, django_assert_max_num_queries,
):
    for i in range(20):
        ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse,
            status="new",
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("forecasting:alert_list"))
    assert r.status_code == 200


@pytest.mark.django_db
def test_rop_list_query_budget(
    client_logged_in, tenant, warehouse, django_assert_max_num_queries,
):
    cat = Category.objects.create(tenant=tenant, name="Bulk")
    for i in range(20):
        p = Product.objects.create(
            tenant=tenant, sku=f"RB-{i:03}", name=f"R{i}",
            category=cat, purchase_cost=1, retail_price=1, status="active",
        )
        rp = ReorderPoint(
            tenant=tenant, product=p, warehouse=warehouse,
            avg_daily_usage=Decimal("1"), lead_time_days=1, safety_stock_qty=5,
        )
        rp.recalc_rop(); rp.save()
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("forecasting:rop_list"))
    assert r.status_code == 200


@pytest.mark.django_db
def test_safety_stock_list_query_budget(
    client_logged_in, tenant, warehouse, django_assert_max_num_queries,
):
    cat = Category.objects.create(tenant=tenant, name="Bulk")
    for i in range(20):
        p = Product.objects.create(
            tenant=tenant, sku=f"SB-{i:03}", name=f"S{i}",
            category=cat, purchase_cost=1, retail_price=1, status="active",
        )
        SafetyStock.objects.create(
            tenant=tenant, product=p, warehouse=warehouse, method="fixed", fixed_qty=5,
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("forecasting:safety_stock_list"))
    assert r.status_code == 200
