"""OWASP-mapped security tests for the quality_control module.

A01 Access Control — cross-tenant IDOR returns 404; non-admins blocked
                     from mutations.
A03 XSS           — user-supplied fields are escaped.
A08 Data integrity / upload — defect photo extension/size/magic guards.
A09 Logging       — `core.AuditLog` emitted on mutations.
CSRF              — state-changing endpoints reject GET.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog
from quality_control.models import (
    QCChecklist, QuarantineRecord, DefectReport, ScrapWriteOff,
)


# ── A01 Broken Access Control ────────────────────────────────────

@pytest.mark.django_db
class TestA01AccessControl:
    def test_checklist_cross_tenant_detail_404(self, client_other, checklist):
        r = client_other.get(reverse('quality_control:checklist_detail', args=[checklist.pk]))
        assert r.status_code == 404

    def test_checklist_cross_tenant_delete_404(self, client_other, checklist):
        r = client_other.post(reverse('quality_control:checklist_delete', args=[checklist.pk]))
        assert r.status_code == 404
        assert QCChecklist.objects.filter(pk=checklist.pk).exists()

    def test_quarantine_cross_tenant_release_404(self, client_other, active_quarantine):
        r = client_other.post(
            reverse('quality_control:quarantine_release', args=[active_quarantine.pk]),
            data={'disposition': 'return_to_stock'},
        )
        assert r.status_code == 404
        active_quarantine.refresh_from_db()
        assert active_quarantine.status == 'active'

    def test_defect_cross_tenant_resolve_404(self, client_other, open_defect):
        r = client_other.post(reverse('quality_control:defect_resolve', args=[open_defect.pk]))
        assert r.status_code == 404
        open_defect.refresh_from_db()
        assert open_defect.status == 'open'

    def test_scrap_cross_tenant_approve_404(self, client_other, tenant, tenant_admin, product, warehouse):
        from decimal import Decimal
        s = ScrapWriteOff.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, unit_cost=Decimal('1.00'), reason='x',
            requested_by=tenant_admin,
        )
        r = client_other.post(reverse('quality_control:scrap_approve', args=[s.pk]))
        assert r.status_code == 404
        s.refresh_from_db()
        assert s.approval_status == 'pending'

    def test_non_admin_create_forbidden(self, client_user):
        r = client_user.post(
            reverse('quality_control:checklist_create'),
            data={'name': 'X', 'applies_to': 'all'},
        )
        assert r.status_code in (302, 403)


# ── A03 XSS ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestA03XSSEscape:
    def test_xss_in_checklist_name_escaped(self, client_admin, tenant, tenant_admin):
        c = QCChecklist.objects.create(
            tenant=tenant, name='<script>alert(1)</script>',
            applies_to='all', created_by=tenant_admin,
        )
        r = client_admin.get(reverse('quality_control:checklist_detail', args=[c.pk]))
        assert r.status_code == 200
        body = r.content.decode()
        assert '<script>alert(1)</script>' not in body
        assert '&lt;script&gt;' in body


# ── A08 Data integrity / file upload ─────────────────────────────

@pytest.mark.django_db
class TestA08Upload:
    def test_defect_photo_rejects_pe_executable(self, client_admin, open_defect, tenant, product, warehouse):
        bad = SimpleUploadedFile('bad.jpg', b'MZ\x90\x00' + b'A' * 100, content_type='image/jpeg')
        r = client_admin.post(
            reverse('quality_control:defect_edit', args=[open_defect.pk]),
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity_affected': 1, 'defect_type': 'visual',
                'severity': 'minor', 'source': 'receiving',
                'description': 'x',
                'photos-TOTAL_FORMS': '1', 'photos-INITIAL_FORMS': '0',
                'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '1000',
                'photos-0-image': bad, 'photos-0-caption': '',
            },
            format='multipart',
        )
        # Edit either re-renders (200) with errors or redirects; in both
        # cases no photo should have been created.
        assert open_defect.photos.count() == 0

    def test_defect_photo_rejects_svg(self, client_admin, open_defect, product, warehouse):
        svg = SimpleUploadedFile(
            'logo.svg',
            b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            content_type='image/svg+xml',
        )
        client_admin.post(
            reverse('quality_control:defect_edit', args=[open_defect.pk]),
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity_affected': 1, 'defect_type': 'visual',
                'severity': 'minor', 'source': 'receiving',
                'description': 'x',
                'photos-TOTAL_FORMS': '1', 'photos-INITIAL_FORMS': '0',
                'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '1000',
                'photos-0-image': svg, 'photos-0-caption': '',
            },
            format='multipart',
        )
        assert open_defect.photos.count() == 0


# ── A09 Audit logging ───────────────────────────────────────────

@pytest.mark.django_db
class TestA09Audit:
    def test_scrap_post_emits_audit_with_adjustment_info(
        self, client_admin, tenant, tenant_admin, product, warehouse, stock_level,
    ):
        """D-09: audit payload must reference the resulting adjustment number."""
        from decimal import Decimal
        s = ScrapWriteOff.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=2, unit_cost=Decimal('1.00'), reason='x',
            approval_status='approved', requested_by=tenant_admin,
        )
        r = client_admin.post(reverse('quality_control:scrap_post', args=[s.pk]))
        assert r.status_code == 302
        entry = AuditLog.objects.filter(model_name='ScrapWriteOff', action='post').latest('id')
        assert 'adj=' in entry.changes
        assert 'on_hand' in entry.changes


# ── CSRF / require_POST ─────────────────────────────────────────

@pytest.mark.django_db
class TestCSRF:
    def test_scrap_approve_requires_post(self, client_admin, tenant, product, warehouse):
        from decimal import Decimal
        s = ScrapWriteOff.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, unit_cost=Decimal('1.00'), reason='x',
        )
        r = client_admin.get(reverse('quality_control:scrap_approve', args=[s.pk]))
        assert r.status_code == 405

    def test_quarantine_delete_requires_post(self, client_admin, active_quarantine):
        r = client_admin.get(reverse('quality_control:quarantine_delete', args=[active_quarantine.pk]))
        assert r.status_code == 405
