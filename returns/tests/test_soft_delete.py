"""D-15: soft-delete behaviour for the four top-level RMA-family models.

Soft-delete is implemented via a `deleted_at` DateTimeField — when set, the
record is hidden from every user-facing view (list, detail, edit, transitions)
while retaining an immutable audit trail in the row plus an `AuditLog` entry.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from returns.models import Disposition, RefundCredit, ReturnInspection


pytestmark = pytest.mark.django_db


class TestInspectionSoftDelete:
    def test_delete_soft_deletes_inspection(
        self, client_admin, tenant, approved_rma, tenant_admin,
    ):
        insp = ReturnInspection.objects.create(
            tenant=tenant, rma=approved_rma,
            status='pending', inspector=tenant_admin,
        )
        resp = client_admin.post(reverse('returns:inspection_delete', args=[insp.pk]))
        assert resp.status_code == 302
        insp.refresh_from_db()
        assert insp.deleted_at is not None

    def test_soft_deleted_inspection_hidden_from_detail(
        self, client_admin, tenant, approved_rma, tenant_admin,
    ):
        insp = ReturnInspection.objects.create(
            tenant=tenant, rma=approved_rma,
            status='pending', inspector=tenant_admin,
        )
        client_admin.post(reverse('returns:inspection_delete', args=[insp.pk]))
        resp = client_admin.get(reverse('returns:inspection_detail', args=[insp.pk]))
        assert resp.status_code == 404


class TestDispositionSoftDelete:
    def test_delete_soft_deletes_disposition(
        self, client_admin, disposition_pending_restock,
    ):
        resp = client_admin.post(
            reverse('returns:disposition_delete', args=[disposition_pending_restock.pk])
        )
        assert resp.status_code == 302
        disposition_pending_restock.refresh_from_db()
        assert disposition_pending_restock.deleted_at is not None

    def test_cannot_process_soft_deleted_disposition(
        self, client_admin, disposition_pending_restock,
    ):
        client_admin.post(
            reverse('returns:disposition_delete', args=[disposition_pending_restock.pk])
        )
        resp = client_admin.post(
            reverse('returns:disposition_process', args=[disposition_pending_restock.pk])
        )
        assert resp.status_code == 404


class TestRefundSoftDelete:
    def test_delete_soft_deletes_refund(self, client_admin, pending_refund):
        resp = client_admin.post(reverse('returns:refund_delete', args=[pending_refund.pk]))
        assert resp.status_code == 302
        pending_refund.refresh_from_db()
        assert pending_refund.deleted_at is not None

    def test_soft_deleted_refund_hidden_from_list(self, client_admin, pending_refund):
        client_admin.post(reverse('returns:refund_delete', args=[pending_refund.pk]))
        resp = client_admin.get(reverse('returns:refund_list'))
        assert resp.context['refunds'].paginator.count == 0

    def test_processed_refund_cannot_be_deleted(self, client_admin, pending_refund):
        pending_refund.status = 'processed'
        pending_refund.save()
        resp = client_admin.post(reverse('returns:refund_delete', args=[pending_refund.pk]))
        assert resp.status_code == 302
        pending_refund.refresh_from_db()
        assert pending_refund.deleted_at is None
