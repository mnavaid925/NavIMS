"""D-07: every destructive / financial action must emit an AuditLog row."""
import pytest
from django.urls import reverse

from core.models import AuditLog


pytestmark = pytest.mark.django_db


def _audit_actions():
    return list(AuditLog.objects.values_list('action', flat=True))


class TestRMAAuditEmission:
    def test_submit_emits_audit(self, client_admin, draft_rma):
        AuditLog.objects.all().delete()
        client_admin.post(reverse('returns:rma_submit', args=[draft_rma.pk]))
        assert any('submitted' in a for a in _audit_actions())

    def test_approve_emits_audit(self, client_admin, pending_rma, other_tenant_admin):
        pending_rma.created_by = other_tenant_admin
        pending_rma.save()
        AuditLog.objects.all().delete()
        client_admin.post(reverse('returns:rma_approve', args=[pending_rma.pk]))
        assert any('approved' in a for a in _audit_actions())

    def test_delete_emits_audit(self, client_admin, draft_rma):
        AuditLog.objects.all().delete()
        client_admin.post(reverse('returns:rma_delete', args=[draft_rma.pk]))
        assert any('deleted' in a for a in _audit_actions())


class TestDispositionAuditEmission:
    def test_process_emits_audit(self, client_admin, disposition_pending_restock):
        AuditLog.objects.all().delete()
        client_admin.post(
            reverse('returns:disposition_process', args=[disposition_pending_restock.pk])
        )
        assert any('processed' in a for a in _audit_actions())


class TestRefundAuditEmission:
    def test_process_emits_audit(self, client_admin, pending_refund):
        AuditLog.objects.all().delete()
        client_admin.post(reverse('returns:refund_process', args=[pending_refund.pk]))
        assert any('processed' in a for a in _audit_actions())

    def test_delete_emits_audit(self, client_admin, pending_refund):
        AuditLog.objects.all().delete()
        client_admin.post(reverse('returns:refund_delete', args=[pending_refund.pk]))
        assert any('deleted' in a for a in _audit_actions())
