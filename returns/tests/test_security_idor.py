"""OWASP A01 — cross-tenant IDOR across detail / edit / delete / transitions."""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


class TestRMAIDOR:
    def test_detail_cross_tenant_404(self, client_other, draft_rma):
        assert client_other.get(reverse('returns:rma_detail', args=[draft_rma.pk])).status_code == 404

    def test_edit_cross_tenant_404(self, client_other, draft_rma):
        assert client_other.get(reverse('returns:rma_edit', args=[draft_rma.pk])).status_code == 404

    def test_delete_cross_tenant_404(self, client_other, draft_rma):
        assert client_other.post(reverse('returns:rma_delete', args=[draft_rma.pk])).status_code == 404

    def test_submit_cross_tenant_404(self, client_other, draft_rma):
        assert client_other.post(reverse('returns:rma_submit', args=[draft_rma.pk])).status_code == 404


class TestInspectionIDOR:
    def test_detail_cross_tenant_404(self, client_other, inspection_in_progress):
        assert client_other.get(
            reverse('returns:inspection_detail', args=[inspection_in_progress.pk])
        ).status_code == 404


class TestDispositionIDOR:
    def test_detail_cross_tenant_404(self, client_other, disposition_pending_restock):
        assert client_other.get(
            reverse('returns:disposition_detail', args=[disposition_pending_restock.pk])
        ).status_code == 404

    def test_process_cross_tenant_404(self, client_other, disposition_pending_restock):
        assert client_other.post(
            reverse('returns:disposition_process', args=[disposition_pending_restock.pk])
        ).status_code == 404


class TestRefundIDOR:
    def test_detail_cross_tenant_404(self, client_other, pending_refund):
        assert client_other.get(
            reverse('returns:refund_detail', args=[pending_refund.pk])
        ).status_code == 404

    def test_process_cross_tenant_404(self, client_other, pending_refund):
        assert client_other.post(
            reverse('returns:refund_process', args=[pending_refund.pk])
        ).status_code == 404


class TestFormsetFKIDOR:
    """D-05: foreign-tenant FK IDs in inline formsets must be rejected at validation."""

    def test_rma_create_rejects_cross_tenant_product(
        self, client_admin, delivered_so, warehouse, product, other_product,
    ):
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
            'items-0-product': other_product.pk,  # cross-tenant
            'items-0-description': '',
            'items-0-qty_requested': '1',
            'items-0-unit_price': '10.00',
            'items-0-reason_note': '',
        }
        resp = client_admin.post(reverse('returns:rma_create'), data)
        # Expected: form invalid → 200 with errors, not 302 redirect.
        assert resp.status_code == 200
