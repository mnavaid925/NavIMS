"""N+1 / performance guardrails for stock_movements."""
import pytest
from django.urls import reverse

from stock_movements.models import StockTransfer, TransferRoute


@pytest.mark.django_db
def test_transfer_list_query_count(
    client_logged_in, django_assert_max_num_queries, tenant, w1, w2, user,
):
    for _ in range(20):
        StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse("stock_movements:transfer_list"))
        assert r.status_code == 200


@pytest.mark.django_db
def test_route_list_query_count(
    client_logged_in, django_assert_max_num_queries, tenant, w1, w2,
):
    for i in range(15):
        TransferRoute.objects.create(
            tenant=tenant, name=f"R{i}", source_warehouse=w1, destination_warehouse=w2,
            transit_method="truck", estimated_duration_hours=1,
        )
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse("stock_movements:route_list"))
        assert r.status_code == 200


@pytest.mark.django_db
def test_D07_route_detail_no_n_plus_one(
    client_logged_in, django_assert_max_num_queries, tenant, w1, w2, user,
):
    """Regression for D-07: related_transfers must use select_related."""
    route = TransferRoute.objects.create(
        tenant=tenant, name="R", source_warehouse=w1, destination_warehouse=w2,
        transit_method="truck", estimated_duration_hours=1,
    )
    for _ in range(10):
        StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
    with django_assert_max_num_queries(15):
        r = client_logged_in.get(
            reverse("stock_movements:route_detail", args=[route.pk]),
        )
        assert r.status_code == 200
