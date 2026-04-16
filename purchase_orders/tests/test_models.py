from decimal import Decimal
from datetime import date

import pytest

from purchase_orders.models import (
    PurchaseOrder, PurchaseOrderItem, PurchaseOrderApproval,
)


@pytest.mark.django_db
class TestPurchaseOrderTotals:
    def test_subtotal_sums_line_totals(self, draft_po, product, tenant):
        PurchaseOrderItem.objects.create(
            tenant=tenant, purchase_order=draft_po, product=product,
            quantity=3, unit_price=Decimal("7.50"),
        )
        # refresh to drop cached_property
        draft_po = PurchaseOrder.objects.get(pk=draft_po.pk)
        assert draft_po.subtotal == Decimal("100.00") + Decimal("22.50")

    def test_grand_total_formula(self, draft_po):
        # 2 × 50 = 100; tax 10% × 100 = 10; discount 0 → 110
        assert draft_po.grand_total == Decimal("110.00")

    def test_tax_amount_rounded_to_2dp(self, tenant, draft_po, product):
        item = PurchaseOrderItem.objects.create(
            tenant=tenant, purchase_order=draft_po, product=product,
            quantity=1, unit_price=Decimal("33.33"),
            tax_rate=Decimal("7.5"),
        )
        assert item.tax_amount == Decimal("2.50")


@pytest.mark.django_db
class TestStateMachine:
    @pytest.mark.parametrize("src,dst,ok", [
        ("draft", "pending_approval", True),
        ("draft", "approved", False),
        ("closed", "draft", False),
        ("cancelled", "draft", True),
        ("sent", "received", True),
        ("sent", "partially_received", True),
        ("partially_received", "received", True),
        ("received", "closed", True),
        ("pending_approval", "approved", True),
        ("pending_approval", "draft", True),
    ])
    def test_can_transition_to(self, draft_po, src, dst, ok):
        draft_po.status = src
        assert draft_po.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestPoNumberGeneration:
    def test_first_po_is_PO_00001(self, tenant, vendor):
        po = PurchaseOrder.objects.create(
            tenant=tenant, vendor=vendor, order_date=date.today(),
        )
        assert po.po_number == "PO-00001"

    def test_sequence_increments(self, tenant, vendor):
        PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, order_date=date.today())
        p2 = PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, order_date=date.today())
        assert p2.po_number == "PO-00002"


@pytest.mark.django_db
class TestApprovalStatus:
    def test_rejection_blocks_current_cycle(self, pending_po, approver_user):
        PurchaseOrderApproval.objects.create(
            tenant=pending_po.tenant, purchase_order=pending_po,
            approver=approver_user, decision="rejected",
        )
        assert pending_po.approval_status == "rejected"

    def test_resubmit_after_reject_via_submit_view_clears_approvals(
        self, client, pending_po, admin_user, approver_user
    ):
        """Regression for D-01.

        The submit view must wipe stale approvals so a new cycle starts clean.
        """
        from django.urls import reverse

        # Cycle 1: admin rejects
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_reject', args=[pending_po.pk]),
            {'decision': 'rejected', 'notes': 'try again'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'draft'
        assert pending_po.approvals.filter(decision='rejected').exists()

        # Cycle 2: creator resubmits — stale approvals must be purged
        client.post(reverse('purchase_orders:po_submit', args=[pending_po.pk]))
        pending_po.refresh_from_db()
        assert pending_po.status == 'pending_approval'
        assert pending_po.approvals.count() == 0

        # approver approves — now threshold should be met
        client.force_login(approver_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved', 'notes': 'ok'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'approved'
