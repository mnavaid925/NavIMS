from decimal import Decimal

import pytest
from django.urls import reverse

from returns.models import (
    ReturnAuthorization, ReturnAuthorizationItem, RefundCredit,
)


pytestmark = pytest.mark.django_db


class TestRMAList:
    def test_list_shows_rma(self, client_admin, draft_rma):
        resp = client_admin.get(reverse('returns:rma_list'))
        assert resp.status_code == 200
        assert draft_rma.rma_number.encode() in resp.content

    def test_list_status_filter(self, client_admin, tenant, delivered_so, warehouse):
        ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='A',
            requested_date='2026-04-18', warehouse=warehouse, status='draft',
        )
        ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='B',
            requested_date='2026-04-18', warehouse=warehouse, status='cancelled',
        )
        resp = client_admin.get(reverse('returns:rma_list') + '?status=cancelled')
        assert b'B' in resp.content
        # 'A' is also in 'RMA-00001' numbering, so assert count of RMAs instead
        assert resp.context['rmas'].paginator.count == 1

    def test_list_preserves_filters_in_pagination(self, client_admin, tenant, delivered_so, warehouse):
        # create 25 draft RMAs → 2 pages of 20
        for i in range(25):
            ReturnAuthorization.objects.create(
                tenant=tenant, sales_order=delivered_so, customer_name=f'c{i}',
                requested_date='2026-04-18', warehouse=warehouse,
                reason='warranty', status='draft',
            )
        resp = client_admin.get(
            reverse('returns:rma_list') + '?status=draft&reason=warranty&page=1'
        )
        assert resp.status_code == 200
        # The next-page URL must carry the filter querystring. HTML escapes
        # '&' as '&amp;', so assert on the literal key=value substrings.
        assert b'status=draft' in resp.content
        assert b'reason=warranty' in resp.content

    def test_list_cross_tenant_invisible(self, client_admin, other_draft_rma):
        resp = client_admin.get(reverse('returns:rma_list'))
        assert other_draft_rma.rma_number.encode() not in resp.content


class TestRMACreateEdit:
    def test_create_draft_rma(self, client_admin, delivered_so, warehouse, product):
        url = reverse('returns:rma_create')
        data = {
            'sales_order': delivered_so.pk,
            'customer_name': 'Alice',
            'customer_email': '', 'customer_phone': '', 'return_address': '',
            'reason': 'defective',
            'requested_date': '2026-04-18',
            'expected_return_date': '',
            'warehouse': warehouse.pk,
            'notes': '',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': product.pk,
            'items-0-description': '',
            'items-0-qty_requested': '1',
            'items-0-unit_price': '10.00',
            'items-0-reason_note': '',
        }
        resp = client_admin.post(url, data)
        assert resp.status_code == 302
        assert ReturnAuthorization.objects.filter(customer_name='Alice').exists()

    def test_edit_blocked_for_approved_rma(self, client_admin, approved_rma):
        resp = client_admin.get(reverse('returns:rma_edit', args=[approved_rma.pk]))
        assert resp.status_code == 302


class TestRMADelete:
    def test_delete_draft_rma_soft_deletes(self, client_admin, draft_rma):
        """D-15: delete sets deleted_at instead of hard-deleting the row."""
        resp = client_admin.post(reverse('returns:rma_delete', args=[draft_rma.pk]))
        assert resp.status_code == 302
        draft_rma.refresh_from_db()
        assert draft_rma.deleted_at is not None

    def test_delete_hides_rma_from_list_and_detail(self, client_admin, draft_rma):
        """D-15: soft-deleted RMA is invisible through user-facing surface."""
        post_resp = client_admin.post(reverse('returns:rma_delete', args=[draft_rma.pk]))
        assert post_resp.status_code == 302
        draft_rma.refresh_from_db()
        assert draft_rma.deleted_at is not None, 'delete view did not set deleted_at'
        list_resp = client_admin.get(reverse('returns:rma_list'))
        assert list_resp.context['rmas'].paginator.count == 0, (
            'soft-deleted RMA must not appear in the list queryset'
        )
        detail_resp = client_admin.get(reverse('returns:rma_detail', args=[draft_rma.pk]))
        assert detail_resp.status_code == 404

    def test_delete_non_draft_blocked(self, client_admin, approved_rma):
        """D-16: only draft RMAs can be deleted."""
        resp = client_admin.post(reverse('returns:rma_delete', args=[approved_rma.pk]))
        assert resp.status_code == 302
        approved_rma.refresh_from_db()
        assert approved_rma.deleted_at is None

    def test_delete_with_processed_refund_blocked(self, client_admin, tenant, received_rma):
        """D-19: cannot delete RMA with processed refunds."""
        RefundCredit.objects.create(
            tenant=tenant, rma=received_rma, amount=Decimal('5.00'),
            currency='USD', status='processed',
        )
        # Move to draft to isolate the processed-refund guard from the status guard.
        received_rma.status = 'draft'
        received_rma.save()
        resp = client_admin.post(reverse('returns:rma_delete', args=[received_rma.pk]))
        assert resp.status_code == 302
        received_rma.refresh_from_db()
        assert received_rma.deleted_at is None


class TestRMATransitions:
    def test_submit_draft_to_pending(self, client_admin, draft_rma):
        resp = client_admin.post(reverse('returns:rma_submit', args=[draft_rma.pk]))
        assert resp.status_code == 302
        draft_rma.refresh_from_db()
        assert draft_rma.status == 'pending'

    def test_approve_pending_sets_approver(self, client_admin, pending_rma, other_tenant_admin):
        # Swap created_by to another user so client_admin can approve (segregation of duties).
        pending_rma.created_by = other_tenant_admin
        pending_rma.save()
        resp = client_admin.post(reverse('returns:rma_approve', args=[pending_rma.pk]))
        assert resp.status_code == 302
        pending_rma.refresh_from_db()
        assert pending_rma.status == 'approved'
        assert pending_rma.approved_by is not None
        assert pending_rma.approved_at is not None

    def test_creator_cannot_approve_own_rma(self, client_admin, tenant_admin, pending_rma):
        """Segregation of duties: creator ≠ approver."""
        pending_rma.created_by = tenant_admin
        pending_rma.save()
        resp = client_admin.post(reverse('returns:rma_approve', args=[pending_rma.pk]))
        pending_rma.refresh_from_db()
        assert pending_rma.status == 'pending'

    def test_invalid_transition_leaves_state_unchanged(self, client_admin, draft_rma):
        resp = client_admin.post(reverse('returns:rma_approve', args=[draft_rma.pk]))
        assert resp.status_code == 302
        draft_rma.refresh_from_db()
        assert draft_rma.status == 'draft'

    def test_receive_does_not_autofill_qty_received(self, client_admin, approved_rma):
        """D-09: receive view no longer overrides qty_received silently."""
        item = approved_rma.items.first()
        item.qty_received = 0
        item.save()
        client_admin.post(reverse('returns:rma_receive', args=[approved_rma.pk]))
        item.refresh_from_db()
        # Must remain 0 — operator is expected to key actuals before receiving.
        assert item.qty_received == 0
