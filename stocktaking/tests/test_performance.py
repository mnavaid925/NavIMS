"""N+1 guards for list pages."""
from datetime import date

import pytest
from django.urls import reverse

from stocktaking.models import StockCount


@pytest.mark.django_db
def test_count_list_no_n_plus_one(
    client_admin, tenant, warehouse, django_assert_max_num_queries,
):
    # 50 counts → list page must stay bounded.
    for _ in range(50):
        StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
    with django_assert_max_num_queries(20):
        r = client_admin.get(reverse('stocktaking:count_list'))
        assert r.status_code == 200
