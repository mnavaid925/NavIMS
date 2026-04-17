import pytest
from django.urls import reverse

from orders.models import SalesOrder, SalesOrderItem


@pytest.mark.django_db
def test_so_list_query_budget(
    django_assert_max_num_queries, client_admin, tenant, warehouse, product,
):
    for _ in range(20):
        so = SalesOrder(
            tenant=tenant, customer_name='X',
            order_date='2026-04-18', warehouse=warehouse,
        )
        so.save()
        for _ in range(3):
            SalesOrderItem.objects.create(
                tenant=tenant, sales_order=so, product=product,
                quantity=1, unit_price=1,
            )
    # 20 SOs × 3 items → grand_total property walks items.
    # Budget generous to catch regression, not perfection.
    with django_assert_max_num_queries(70):
        resp = client_admin.get(reverse('orders:so_list'))
    assert resp.status_code == 200
