"""Performance — N+1 guards on list views."""
import pytest
from django.urls import reverse

from lot_tracking.models import LotBatch


@pytest.mark.django_db
def test_lot_list_no_n_plus_one(
    client_logged_in, tenant, product, warehouse, django_assert_max_num_queries,
):
    for i in range(50):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
            lot_number=f"LOT-PERF-{i:05d}",
        )
    with django_assert_max_num_queries(15):
        r = client_logged_in.get(reverse("lot_tracking:lot_list"))
    assert r.status_code == 200


@pytest.mark.django_db
def test_lot_trace_view_budget(
    client_logged_in, lot, django_assert_max_num_queries,
):
    from lot_tracking.models import TraceabilityLog
    for i in range(100):
        TraceabilityLog.objects.create(
            tenant=lot.tenant, lot=lot, event_type="adjusted",
            quantity=1, reference_type="Test", reference_number=f"R-{i}",
        )
    with django_assert_max_num_queries(20):
        r = client_logged_in.get(reverse("lot_tracking:lot_trace", args=[lot.pk]))
    assert r.status_code == 200
