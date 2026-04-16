"""N+1 / performance guardrails."""
from datetime import date

import pytest
from django.urls import reverse

from receiving.models import GoodsReceiptNote, WarehouseLocation, PutawayTask


@pytest.mark.django_db
def test_grn_list_query_count(
    client_logged_in, django_assert_max_num_queries, tenant, po, user,
):
    for _ in range(20):
        GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po,
            received_date=date(2026, 1, 1),
            received_by=user, created_by=user,
        )
    with django_assert_max_num_queries(15):
        r = client_logged_in.get(reverse("receiving:grn_list"))
        assert r.status_code == 200


@pytest.mark.django_db
def test_location_list_query_count(
    client_logged_in, django_assert_max_num_queries, tenant,
):
    for i in range(20):
        WarehouseLocation.objects.create(
            tenant=tenant, name=f"B{i}", code=f"B{i}", location_type="bin",
        )
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse("receiving:location_list"))
        assert r.status_code == 200


@pytest.mark.django_db
def test_putaway_list_query_count(
    client_logged_in, django_assert_max_num_queries, tenant, po, po_item, product, user,
):
    g = GoodsReceiptNote.objects.create(
        tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
        status="completed", received_by=user, created_by=user,
    )
    from receiving.models import GoodsReceiptNoteItem
    for _ in range(10):
        gi = GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product, quantity_received=1,
        )
        PutawayTask.objects.create(
            tenant=tenant, grn=g, grn_item=gi, product=product,
            quantity=1, created_by=user,
        )
    with django_assert_max_num_queries(15):
        r = client_logged_in.get(reverse("receiving:putaway_list"))
        assert r.status_code == 200
