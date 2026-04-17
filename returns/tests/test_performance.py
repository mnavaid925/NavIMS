import pytest
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.db import connection


pytestmark = pytest.mark.django_db


def test_rma_list_query_budget(client_admin, tenant, delivered_so, warehouse):
    from returns.models import ReturnAuthorization
    for i in range(40):
        ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name=f'c{i}',
            requested_date='2026-04-18', warehouse=warehouse,
        )
    with CaptureQueriesContext(connection) as ctx:
        resp = client_admin.get(reverse('returns:rma_list'))
    assert resp.status_code == 200
    # 20-row page should not trigger N+1 — budget generously to avoid flakes.
    assert len(ctx.captured_queries) < 20, (
        f'Query count {len(ctx.captured_queries)} exceeds budget 20'
    )
