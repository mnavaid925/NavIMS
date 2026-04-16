from datetime import date

import pytest
from receiving.models import GoodsReceiptNote, GoodsReceiptNoteItem


@pytest.mark.django_db
class TestGrnAutoNumber:
    def test_first_grn_numbers_00001(self, tenant, po, user):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            created_by=user,
        )
        assert g.grn_number == "GRN-00001"

    def test_numbers_increment_per_tenant(self, tenant, other_tenant, po, other_po, user, other_user):
        GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1), created_by=user,
        )
        GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 2), created_by=user,
        )
        g_other = GoodsReceiptNote.objects.create(
            tenant=other_tenant, purchase_order=other_po,
            received_date=date(2026, 1, 3), created_by=other_user,
        )
        # Tenant-scoped numbering — other tenant's first GRN must be 00001.
        assert g_other.grn_number == "GRN-00001"
        latest = GoodsReceiptNote.objects.filter(tenant=tenant).order_by('-id').first()
        assert latest.grn_number == "GRN-00002"


@pytest.mark.django_db
class TestGrnTransitions:
    def test_can_transition_draft_to_inspecting(self, grn):
        assert grn.can_transition_to("inspecting") is True
        assert grn.can_transition_to("draft") is False

    def test_completed_is_terminal(self, grn):
        grn.status = "completed"
        grn.save()
        assert grn.can_transition_to("draft") is False
        assert grn.can_transition_to("inspecting") is False
        assert grn.can_transition_to("cancelled") is False

    def test_cancelled_can_reopen_to_draft(self, grn):
        grn.status = "cancelled"
        grn.save()
        assert grn.can_transition_to("draft") is True


@pytest.mark.django_db
class TestGrnItemAggregates:
    def test_quantity_outstanding(self, tenant, po, po_item, product, user):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product, quantity_received=3,
        )
        g2 = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 2), created_by=user,
        )
        item2 = GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g2, po_item=po_item, product=product, quantity_received=0,
        )
        # PO qty=10, 3 received on completed GRN → outstanding = 7 for item2.
        assert item2.quantity_outstanding == 7
        assert item2.quantity_previously_received == 3


@pytest.mark.django_db
class TestUpdatePoStatus:
    def test_all_items_fully_received_marks_po_received(self, tenant, po, po_item, product, user):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product,
            quantity_received=po_item.quantity,
        )
        g.update_po_status()
        po.refresh_from_db()
        assert po.status == "received"

    def test_partial_receipt_marks_po_partially_received(self, tenant, po, po_item, product, user):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product, quantity_received=4,
        )
        g.update_po_status()
        po.refresh_from_db()
        assert po.status == "partially_received"
