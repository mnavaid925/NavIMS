import pytest
from django.urls import reverse

from stock_movements.models import StockTransfer, TransferApprovalRule, TransferApproval


@pytest.mark.django_db
class TestApproveView:
    def test_D05_requester_cannot_self_approve(
        self, client_logged_in, tenant, w1, w2, user,
    ):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="pending_approval", requested_by=user,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_approve", args=[t.pk]),
            data={"decision": "approved", "comments": "self-approve"},
        )
        assert r.status_code == 302
        t.refresh_from_db()
        assert t.status == "pending_approval"
        assert TransferApproval.objects.filter(transfer=t).count() == 0

    def test_other_user_can_approve(self, approver_client, tenant, w1, w2, user):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="pending_approval", requested_by=user,
        )
        r = approver_client.post(
            reverse("stock_movements:transfer_approve", args=[t.pk]),
            data={"decision": "approved", "comments": "ok"},
        )
        assert r.status_code == 302
        t.refresh_from_db()
        assert t.status == "approved"
        assert TransferApproval.objects.filter(transfer=t).count() == 1

    def test_other_user_can_reject(self, approver_client, tenant, w1, w2, user):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="pending_approval", requested_by=user,
        )
        r = approver_client.post(
            reverse("stock_movements:transfer_approve", args=[t.pk]),
            data={"decision": "rejected", "comments": "no"},
        )
        assert r.status_code == 302
        t.refresh_from_db()
        assert t.status == "cancelled"

    def test_approve_non_pending_blocked(self, client_logged_in, transfer_draft):
        r = client_logged_in.get(
            reverse("stock_movements:transfer_approve", args=[transfer_draft.pk]),
        )
        assert r.status_code == 302


@pytest.mark.django_db
class TestApprovalRuleConsultation:
    """Regression for D-09: rules now drive initial transfer status."""

    def _payload(self, w1, w2, product_pk, n_items=1):
        return {
            "transfer_type": "inter_warehouse",
            "source_warehouse": str(w1.pk),
            "destination_warehouse": str(w2.pk),
            "priority": "normal",
            "notes": "",
            "item_product": [str(product_pk)] * n_items,
            "item_quantity": ["1"] * n_items,
            "item_notes": [""] * n_items,
        }

    def test_no_matching_rule_starts_draft(
        self, client_logged_in, tenant, w1, w2, product,
    ):
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=self._payload(w1, w2, product.pk, n_items=1),
        )
        assert r.status_code == 302
        t = StockTransfer.objects.get(tenant=tenant)
        assert t.status == "draft"

    def test_rule_no_approval_keeps_draft(
        self, client_logged_in, tenant, w1, w2, product,
    ):
        TransferApprovalRule.objects.create(
            tenant=tenant, name="Small", min_items=0, max_items=3,
            requires_approval=False, is_active=True,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=self._payload(w1, w2, product.pk, n_items=2),
        )
        assert r.status_code == 302
        t = StockTransfer.objects.get(tenant=tenant)
        assert t.status == "draft"

    def test_rule_requires_approval_promotes_status(
        self, client_logged_in, tenant, w1, w2, product,
    ):
        TransferApprovalRule.objects.create(
            tenant=tenant, name="Mid", min_items=2, max_items=10,
            requires_approval=True, is_active=True,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=self._payload(w1, w2, product.pk, n_items=4),
        )
        assert r.status_code == 302
        t = StockTransfer.objects.get(tenant=tenant)
        assert t.status == "pending_approval"

    def test_unbounded_rule_matches_large_transfer(
        self, client_logged_in, tenant, w1, w2, product,
    ):
        TransferApprovalRule.objects.create(
            tenant=tenant, name="Large", min_items=10, max_items=None,
            requires_approval=True, is_active=True,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=self._payload(w1, w2, product.pk, n_items=15),
        )
        assert r.status_code == 302
        t = StockTransfer.objects.get(tenant=tenant)
        assert t.status == "pending_approval"

    def test_inactive_rule_ignored(
        self, client_logged_in, tenant, w1, w2, product,
    ):
        TransferApprovalRule.objects.create(
            tenant=tenant, name="Off", min_items=0, max_items=None,
            requires_approval=True, is_active=False,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data=self._payload(w1, w2, product.pk, n_items=1),
        )
        assert r.status_code == 302
        t = StockTransfer.objects.get(tenant=tenant)
        assert t.status == "draft"
