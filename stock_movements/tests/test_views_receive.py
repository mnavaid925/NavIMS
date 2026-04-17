import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestReceiveView:
    def test_receive_only_allowed_in_in_transit(self, client_logged_in, transfer_draft):
        r = client_logged_in.get(
            reverse("stock_movements:transfer_receive", args=[transfer_draft.pk]),
        )
        assert r.status_code == 302  # warning + redirect

    def test_partial_receive_keeps_in_transit(
        self, client_logged_in, transfer_in_transit,
    ):
        item = transfer_in_transit.items.first()
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[transfer_in_transit.pk]),
            data={f"received_qty_{item.pk}": "4"},
        )
        assert r.status_code == 302
        item.refresh_from_db()
        transfer_in_transit.refresh_from_db()
        assert item.received_quantity == 4
        assert transfer_in_transit.status == "in_transit"

    def test_full_receive_auto_completes(
        self, client_logged_in, transfer_in_transit,
    ):
        item = transfer_in_transit.items.first()
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[transfer_in_transit.pk]),
            data={f"received_qty_{item.pk}": str(item.quantity)},
        )
        assert r.status_code == 302
        transfer_in_transit.refresh_from_db()
        assert transfer_in_transit.status == "completed"
        assert transfer_in_transit.completed_at is not None

    def test_D06_over_receive_rejected_with_error(
        self, client_logged_in, transfer_in_transit,
    ):
        """Regression for D-06: over-receive must surface a field-level error, not silently clamp."""
        item = transfer_in_transit.items.first()
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[transfer_in_transit.pk]),
            data={f"received_qty_{item.pk}": "999"},
        )
        assert r.status_code == 200  # form re-rendered with errors
        item.refresh_from_db()
        assert item.received_quantity == 0  # unchanged

    def test_D06_non_int_input_surfaces_error(
        self, client_logged_in, transfer_in_transit,
    ):
        item = transfer_in_transit.items.first()
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[transfer_in_transit.pk]),
            data={f"received_qty_{item.pk}": "abc"},
        )
        assert r.status_code == 200
        item.refresh_from_db()
        assert item.received_quantity == 0

    def test_D06_negative_input_rejected(
        self, client_logged_in, transfer_in_transit,
    ):
        item = transfer_in_transit.items.first()
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[transfer_in_transit.pk]),
            data={f"received_qty_{item.pk}": "-3"},
        )
        assert r.status_code == 200
        item.refresh_from_db()
        assert item.received_quantity == 0

    def test_empty_input_skipped(self, client_logged_in, transfer_in_transit):
        item = transfer_in_transit.items.first()
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[transfer_in_transit.pk]),
            data={f"received_qty_{item.pk}": ""},
        )
        assert r.status_code == 302
        item.refresh_from_db()
        assert item.received_quantity == 0

    def test_cross_tenant_receive_404(
        self, client_logged_in, other_tenant, other_warehouse, other_user,
    ):
        from stock_movements.models import StockTransfer
        t = StockTransfer.objects.create(
            tenant=other_tenant, transfer_type="intra_warehouse",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            status="in_transit", requested_by=other_user,
        )
        r = client_logged_in.get(
            reverse("stock_movements:transfer_receive", args=[t.pk]),
        )
        assert r.status_code == 404
