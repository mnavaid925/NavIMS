"""Integration — traceability list + create + filters + IDOR."""
import pytest
from django.urls import reverse

from lot_tracking.models import TraceabilityLog


@pytest.mark.django_db
class TestTraceabilityViews:
    def test_list_renders(self, client_logged_in, lot, tenant):
        TraceabilityLog.objects.create(
            tenant=tenant, lot=lot, event_type="adjusted", quantity=1,
        )
        r = client_logged_in.get(reverse("lot_tracking:traceability_list"))
        assert r.status_code == 200

    def test_filter_by_event(self, client_logged_in, lot, tenant):
        TraceabilityLog.objects.create(
            tenant=tenant, lot=lot, event_type="sold", quantity=1,
            reference_number="R-SOLD",
        )
        TraceabilityLog.objects.create(
            tenant=tenant, lot=lot, event_type="adjusted", quantity=1,
            reference_number="R-ADJ",
        )
        r = client_logged_in.get(
            reverse("lot_tracking:traceability_list") + "?event=sold"
        )
        assert b"R-SOLD" in r.content
        assert b"R-ADJ" not in r.content

    def test_create_traceability_log(self, client_logged_in, lot, tenant):
        r = client_logged_in.post(reverse("lot_tracking:traceability_create"), {
            "lot": lot.pk, "serial_number": "",
            "event_type": "adjusted",
            "from_warehouse": "", "to_warehouse": "",
            "quantity": 5,
            "reference_type": "Test", "reference_number": "R-TEST",
            "notes": "",
        })
        assert r.status_code == 302
        assert TraceabilityLog.objects.filter(
            tenant=tenant, reference_number="R-TEST",
        ).exists()

    def test_idor_cross_tenant(self, client_logged_in, other_tenant):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        from lot_tracking.models import LotBatch
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        b_lot = LotBatch.objects.create(tenant=other_tenant, product=p2, warehouse=w2, quantity=1)
        log = TraceabilityLog.objects.create(
            tenant=other_tenant, lot=b_lot, event_type="adjusted", quantity=1,
        )
        r = client_logged_in.get(
            reverse("lot_tracking:traceability_detail", args=[log.pk])
        )
        assert r.status_code == 404
