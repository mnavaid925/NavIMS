from decimal import Decimal
from datetime import date

import pytest
from django.urls import reverse

from purchase_orders.models import PurchaseOrder, PurchaseOrderItem


@pytest.mark.django_db
def test_list_view_query_budget(
    client_logged_in, tenant, vendor, product, django_assert_max_num_queries
):
    """Regression for D-10.

    20 POs × 3 items each must not produce an N+1 storm on the list page.
    Budget: auth + tenant + paginator count + POs + prefetch(items) + vendors-for-filter.
    """
    for _ in range(20):
        po = PurchaseOrder.objects.create(
            tenant=tenant, vendor=vendor, order_date=date.today(),
        )
        for _ in range(3):
            PurchaseOrderItem.objects.create(
                tenant=tenant, purchase_order=po, product=product,
                quantity=1, unit_price=Decimal("10"),
            )
    with django_assert_max_num_queries(12):
        resp = client_logged_in.get(reverse('purchase_orders:po_list'))
        assert resp.status_code == 200
