"""D-06: destructive / state-transition endpoints require is_tenant_admin."""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


class TestRMARBAC:
    def test_non_admin_cannot_submit(self, client_user, draft_rma):
        resp = client_user.post(reverse('returns:rma_submit', args=[draft_rma.pk]))
        assert resp.status_code == 403
        draft_rma.refresh_from_db()
        assert draft_rma.status == 'draft'

    def test_non_admin_cannot_approve(self, client_user, pending_rma):
        resp = client_user.post(reverse('returns:rma_approve', args=[pending_rma.pk]))
        assert resp.status_code == 403
        pending_rma.refresh_from_db()
        assert pending_rma.status == 'pending'

    def test_non_admin_cannot_delete(self, client_user, draft_rma):
        resp = client_user.post(reverse('returns:rma_delete', args=[draft_rma.pk]))
        assert resp.status_code == 403


class TestDispositionRBAC:
    def test_non_admin_cannot_process(self, client_user, disposition_pending_restock):
        resp = client_user.post(
            reverse('returns:disposition_process', args=[disposition_pending_restock.pk])
        )
        assert resp.status_code == 403
        disposition_pending_restock.refresh_from_db()
        assert disposition_pending_restock.status == 'pending'


class TestRefundRBAC:
    def test_non_admin_cannot_process_refund(self, client_user, pending_refund):
        resp = client_user.post(reverse('returns:refund_process', args=[pending_refund.pk]))
        assert resp.status_code == 403
        pending_refund.refresh_from_db()
        assert pending_refund.status == 'pending'
