"""Integration — lot CRUD, transitions, IDOR, filter retention, auto-traceability."""
import pytest
from django.urls import reverse

from lot_tracking.models import LotBatch, TraceabilityLog


@pytest.mark.django_db
class TestLotViews:
    def test_list_login_required(self, client):
        r = client.get(reverse("lot_tracking:lot_list"))
        assert r.status_code == 302

    def test_list_tenant_scoped(
        self, client_logged_in, lot, other_tenant,
    ):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        LotBatch.objects.create(
            tenant=other_tenant, product=p2, warehouse=w2, quantity=1,
            lot_number="LOT-HIDDEN",
        )
        r = client_logged_in.get(reverse("lot_tracking:lot_list"))
        assert lot.lot_number.encode() in r.content
        assert b"LOT-HIDDEN" not in r.content

    def test_list_search(self, client_logged_in, lot):
        r = client_logged_in.get(
            reverse("lot_tracking:lot_list") + f"?q={lot.lot_number}"
        )
        assert lot.lot_number.encode() in r.content

    def test_list_filter_by_status(self, client_logged_in, lot):
        r = client_logged_in.get(reverse("lot_tracking:lot_list") + "?status=active")
        assert lot.lot_number.encode() in r.content

    def test_create_emits_traceability(
        self, client_logged_in, tenant, product, warehouse,
    ):
        r = client_logged_in.post(reverse("lot_tracking:lot_create"), {
            "product": product.pk, "warehouse": warehouse.pk, "grn": "",
            "quantity": 10,
            "manufacturing_date": "", "expiry_date": "",
            "supplier_batch_number": "", "notes": "",
        })
        assert r.status_code == 302
        lot = LotBatch.objects.get(tenant=tenant)
        assert TraceabilityLog.objects.filter(
            lot=lot, event_type="received", quantity=10,
        ).exists()

    def test_transition_emits_traceability(self, client_logged_in, lot):
        r = client_logged_in.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "recalled"])
        )
        assert r.status_code == 302
        lot.refresh_from_db()
        assert lot.status == "recalled"
        assert TraceabilityLog.objects.filter(
            lot=lot, event_type="recalled",
        ).exists()

    def test_invalid_transition_ignored(self, client_logged_in, lot):
        client_logged_in.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "available"]),
        )
        lot.refresh_from_db()
        assert lot.status == "active"

    def test_edit_blocked_after_terminal(self, client_logged_in, lot):
        lot.status = "recalled"
        lot.save()
        r = client_logged_in.get(
            reverse("lot_tracking:lot_edit", args=[lot.pk])
        )
        assert r.status_code == 302

    def test_delete_only_quarantine(self, client_logged_in, lot):
        # status=active — blocked
        r = client_logged_in.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk]), follow=True,
        )
        assert LotBatch.objects.filter(pk=lot.pk).exists()
        # switch to quarantine
        lot.status = "quarantine"
        lot.save()
        r = client_logged_in.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert r.status_code == 302
        assert not LotBatch.objects.filter(pk=lot.pk).exists()

    def test_delete_get_is_no_op(self, client_logged_in, lot):
        lot.status = "quarantine"
        lot.save()
        r = client_logged_in.get(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert r.status_code == 302
        assert LotBatch.objects.filter(pk=lot.pk).exists()

    def test_idor_cross_tenant_detail(self, client_logged_in, other_tenant):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        b_lot = LotBatch.objects.create(tenant=other_tenant, product=p2, warehouse=w2, quantity=1)
        r = client_logged_in.get(
            reverse("lot_tracking:lot_detail", args=[b_lot.pk])
        )
        assert r.status_code == 404

    def test_lot_trace_paginates(self, client_logged_in, lot):
        for i in range(60):
            TraceabilityLog.objects.create(
                tenant=lot.tenant, lot=lot, event_type="adjusted",
                quantity=1, reference_type="T", reference_number=f"R-{i}",
            )
        r = client_logged_in.get(
            reverse("lot_tracking:lot_trace", args=[lot.pk])
        )
        assert r.status_code == 200
        # D-11 — page object must be paginated (50 per page).
        assert r.context['logs'].paginator.num_pages >= 2
