import pytest

from stock_movements.models import (
    StockTransfer, StockTransferItem, TransferApprovalRule,
)


@pytest.mark.django_db
class TestStockTransferAutoNumber:
    def test_first_transfer_numbers_00001(self, tenant, w1, w2, user):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
        assert t.transfer_number == "TRF-00001"

    def test_increments_within_tenant(self, tenant, w1, w2, user):
        for _ in range(3):
            StockTransfer.objects.create(
                tenant=tenant, transfer_type="inter_warehouse",
                source_warehouse=w1, destination_warehouse=w2, requested_by=user,
            )
        latest = StockTransfer.objects.filter(tenant=tenant).order_by("-id").first()
        assert latest.transfer_number == "TRF-00003"

    def test_isolated_per_tenant(self, tenant, other_tenant, w1, w2, other_warehouse, user, other_user):
        StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
        t2 = StockTransfer.objects.create(
            tenant=other_tenant, transfer_type="intra_warehouse",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            requested_by=other_user,
        )
        assert t2.transfer_number == "TRF-00001"


@pytest.mark.django_db
class TestStatusMachine:
    def test_completed_is_terminal(self, transfer_draft):
        transfer_draft.status = "completed"
        transfer_draft.save()
        for s in ["draft", "pending_approval", "approved", "in_transit", "cancelled"]:
            assert transfer_draft.can_transition_to(s) is False

    def test_cancelled_can_reopen_to_draft(self, transfer_draft):
        transfer_draft.status = "cancelled"
        transfer_draft.save()
        assert transfer_draft.can_transition_to("draft") is True

    def test_draft_paths(self, transfer_draft):
        assert transfer_draft.can_transition_to("pending_approval") is True
        assert transfer_draft.can_transition_to("approved") is True
        assert transfer_draft.can_transition_to("cancelled") is True
        assert transfer_draft.can_transition_to("completed") is False


@pytest.mark.django_db
class TestAggregates:
    def test_totals(self, transfer_draft, product):
        StockTransferItem.objects.create(
            tenant=transfer_draft.tenant, transfer=transfer_draft,
            product=product, quantity=10, received_quantity=4,
        )
        StockTransferItem.objects.create(
            tenant=transfer_draft.tenant, transfer=transfer_draft,
            product=product, quantity=5, received_quantity=5,
        )
        assert transfer_draft.total_items == 2
        assert transfer_draft.total_quantity == 15
        assert transfer_draft.total_received == 9

    def test_is_fully_received(self, transfer_draft, product):
        item = StockTransferItem.objects.create(
            tenant=transfer_draft.tenant, transfer=transfer_draft,
            product=product, quantity=10, received_quantity=10,
        )
        assert item.is_fully_received is True


@pytest.mark.django_db
class TestApprovalRule:
    def test_str_with_max(self, tenant):
        r = TransferApprovalRule.objects.create(
            tenant=tenant, name="Mid", min_items=5, max_items=10,
        )
        assert "5–10" in str(r)

    def test_str_without_max(self, tenant):
        r = TransferApprovalRule.objects.create(
            tenant=tenant, name="Big", min_items=11, max_items=None,
        )
        assert "∞" in str(r)
