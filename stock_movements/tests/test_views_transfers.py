import pytest
from django.urls import reverse

from stock_movements.models import StockTransfer, StockTransferItem


def _create_payload(w1, w2, product_pk, qty=5):
    return {
        "transfer_type": "inter_warehouse",
        "source_warehouse": str(w1.pk),
        "destination_warehouse": str(w2.pk),
        "priority": "normal",
        "notes": "",
        "item_product": [str(product_pk)],
        "item_quantity": [str(qty)],
        "item_notes": [""],
    }


@pytest.mark.django_db
class TestTransferCreate:
    def test_happy_create(self, client_logged_in, tenant, w1, w2, product):
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=_create_payload(w1, w2, product.pk, qty=5),
        )
        assert r.status_code == 302
        t = StockTransfer.objects.get(tenant=tenant)
        assert t.transfer_number == "TRF-00001"
        assert t.items.count() == 1
        assert t.items.first().quantity == 5

    def test_D01_cross_tenant_product_rejected(
        self, client_logged_in, tenant, w1, w2, other_product,
    ):
        """Regression for D-01: foreign-tenant product POST must be rejected."""
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=_create_payload(w1, w2, other_product.pk, qty=5),
        )
        assert r.status_code == 200  # form re-rendered
        assert StockTransfer.objects.filter(tenant=tenant).count() == 0

    def test_create_without_items_rejected(self, client_logged_in, tenant, w1, w2):
        payload = _create_payload(w1, w2, 0, qty=5)
        payload["item_product"] = [""]
        payload["item_quantity"] = [""]
        r = client_logged_in.post(reverse("stock_movements:transfer_create"), data=payload)
        assert r.status_code == 200
        assert StockTransfer.objects.filter(tenant=tenant).count() == 0

    def test_create_with_zero_quantity_rejected(
        self, client_logged_in, tenant, w1, w2, product,
    ):
        payload = _create_payload(w1, w2, product.pk, qty=0)
        r = client_logged_in.post(reverse("stock_movements:transfer_create"), data=payload)
        assert r.status_code == 200
        assert StockTransfer.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
class TestTransferEdit:
    def test_edit_replaces_items(self, client_logged_in, tenant, w1, w2, product, transfer_draft):
        StockTransferItem.objects.create(
            tenant=tenant, transfer=transfer_draft, product=product, quantity=99,
        )
        payload = _create_payload(w1, w2, product.pk, qty=7)
        r = client_logged_in.post(
            reverse("stock_movements:transfer_edit", args=[transfer_draft.pk]),
            data=payload,
        )
        assert r.status_code == 302
        items = list(transfer_draft.items.all())
        assert len(items) == 1
        assert items[0].quantity == 7

    def test_D01_edit_cross_tenant_product_rejected(
        self, client_logged_in, tenant, w1, w2, other_product, transfer_draft,
    ):
        payload = _create_payload(w1, w2, other_product.pk, qty=5)
        r = client_logged_in.post(
            reverse("stock_movements:transfer_edit", args=[transfer_draft.pk]),
            data=payload,
        )
        assert r.status_code == 200
        assert transfer_draft.items.count() == 0

    def test_edit_non_editable_status_blocked(
        self, client_logged_in, tenant, w1, w2, product, user,
    ):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="approved", requested_by=user,
        )
        r = client_logged_in.get(reverse("stock_movements:transfer_edit", args=[t.pk]))
        assert r.status_code == 302


@pytest.mark.django_db
class TestTransferDelete:
    def test_delete_draft(self, client_logged_in, transfer_draft):
        r = client_logged_in.post(
            reverse("stock_movements:transfer_delete", args=[transfer_draft.pk]),
        )
        assert r.status_code == 302
        assert not StockTransfer.objects.filter(pk=transfer_draft.pk).exists()

    def test_delete_in_transit_blocked(self, client_logged_in, transfer_in_transit):
        r = client_logged_in.post(
            reverse("stock_movements:transfer_delete", args=[transfer_in_transit.pk]),
        )
        assert r.status_code == 302
        assert StockTransfer.objects.filter(pk=transfer_in_transit.pk).exists()


@pytest.mark.django_db
class TestTransferTransitions:
    def test_D03_complete_with_short_receipt_rejected(
        self, client_logged_in, tenant, w1, w2, product, user,
    ):
        """Regression for D-03: completion must NOT silently overwrite partial receipts."""
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="in_transit", requested_by=user,
        )
        item = StockTransferItem.objects.create(
            tenant=tenant, transfer=t, product=product, quantity=10, received_quantity=4,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_transition", args=[t.pk, "completed"]),
        )
        assert r.status_code == 302
        item.refresh_from_db()
        t.refresh_from_db()
        # Partial receipt preserved; transfer not promoted to completed.
        assert item.received_quantity == 4
        assert t.status == "in_transit"

    def test_complete_when_fully_received_succeeds(
        self, client_logged_in, tenant, w1, w2, product, user,
    ):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="in_transit", requested_by=user,
        )
        StockTransferItem.objects.create(
            tenant=tenant, transfer=t, product=product, quantity=10, received_quantity=10,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_transition", args=[t.pk, "completed"]),
        )
        assert r.status_code == 302
        t.refresh_from_db()
        assert t.status == "completed"
        assert t.completed_at is not None

    def test_D05_requester_cannot_self_approve_via_transition(
        self, client_logged_in, tenant, w1, w2, user,
    ):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="pending_approval", requested_by=user,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_transition", args=[t.pk, "approved"]),
        )
        assert r.status_code == 302
        t.refresh_from_db()
        assert t.status == "pending_approval"

    def test_D05_other_user_can_approve_via_transition(
        self, approver_client, tenant, w1, w2, user,
    ):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="pending_approval", requested_by=user,  # different from approver
        )
        r = approver_client.post(
            reverse("stock_movements:transfer_transition", args=[t.pk, "approved"]),
        )
        assert r.status_code == 302
        t.refresh_from_db()
        assert t.status == "approved"

    def test_invalid_transition_rejected(self, client_logged_in, transfer_draft):
        r = client_logged_in.post(
            reverse("stock_movements:transfer_transition", args=[transfer_draft.pk, "completed"]),
        )
        assert r.status_code == 302
        transfer_draft.refresh_from_db()
        assert transfer_draft.status == "draft"


@pytest.mark.django_db
def test_cross_tenant_detail_404(
    client_logged_in, other_tenant, other_warehouse, other_user,
):
    t = StockTransfer.objects.create(
        tenant=other_tenant, transfer_type="intra_warehouse",
        source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
        requested_by=other_user,
    )
    r = client_logged_in.get(reverse("stock_movements:transfer_detail", args=[t.pk]))
    assert r.status_code == 404
