"""CRUD + state-transition + PDF-render view tests.

Guards against:
    - CRUD regression (detail 404 for other tenant, delete 405 on GET).
    - State-transition drops (invalid transition must not mutate state).
    - AuditLog rows not being emitted for create/update/delete/transition.
    - Token rotation view not rotating.
    - PDF rendering view not returning application/pdf + '%PDF-' prefix.
"""
import pytest
from django.urls import reverse

from core.models import AuditLog

from barcode_rfid.models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice,
    RFIDTag, RFIDReader,
    BatchScanSession,
)


# ── LabelTemplate CRUD ───────────────────────────────────────────

@pytest.mark.django_db
class TestLabelTemplateViews:
    def test_list_200(self, client_admin, label_template):
        r = client_admin.get(reverse('barcode_rfid:label_template_list'))
        assert r.status_code == 200

    def test_list_search_filter(self, client_admin, label_template):
        r = client_admin.get(reverse('barcode_rfid:label_template_list'), {'q': 'LBL-STD'})
        assert r.status_code == 200
        assert b'LBL-STD' in r.content

    def test_create_post(self, client_admin, tenant):
        r = client_admin.post(reverse('barcode_rfid:label_template_create'), {
            'name': 'New', 'code': 'NEW-CODE',
            'label_type': 'barcode', 'symbology': 'code128', 'paper_size': 'label_medium',
            'width_mm': 60, 'height_mm': 40, 'copies_per_label': 1,
        })
        assert r.status_code == 302
        obj = LabelTemplate.objects.get(tenant=tenant, code='NEW-CODE')
        assert AuditLog.objects.filter(
            tenant=tenant, action='create', model_name='LabelTemplate', object_id=str(obj.pk),
        ).exists()

    def test_detail_200_for_owner(self, client_admin, label_template):
        r = client_admin.get(reverse('barcode_rfid:label_template_detail', args=[label_template.pk]))
        assert r.status_code == 200

    def test_detail_404_for_other_tenant(self, client_other, label_template):
        r = client_other.get(reverse('barcode_rfid:label_template_detail', args=[label_template.pk]))
        assert r.status_code == 404

    def test_edit_post(self, client_admin, tenant, label_template):
        r = client_admin.post(reverse('barcode_rfid:label_template_edit', args=[label_template.pk]), {
            'name': 'Renamed', 'code': 'LBL-STD',
            'label_type': 'barcode', 'symbology': 'code128', 'paper_size': 'label_medium',
            'width_mm': 60, 'height_mm': 40, 'copies_per_label': 1,
        })
        assert r.status_code == 302
        label_template.refresh_from_db()
        assert label_template.name == 'Renamed'
        assert AuditLog.objects.filter(
            tenant=tenant, action='update', model_name='LabelTemplate',
        ).exists()

    def test_delete_post(self, client_admin, tenant, label_template):
        pk = label_template.pk
        r = client_admin.post(reverse('barcode_rfid:label_template_delete', args=[pk]))
        assert r.status_code == 302
        assert not LabelTemplate.objects.filter(pk=pk).exists()
        assert AuditLog.objects.filter(
            tenant=tenant, action='delete', model_name='LabelTemplate', object_id=str(pk),
        ).exists()

    def test_delete_get_rejected(self, client_admin, label_template):
        r = client_admin.get(reverse('barcode_rfid:label_template_delete', args=[label_template.pk]))
        assert r.status_code == 405
        assert LabelTemplate.objects.filter(pk=label_template.pk).exists()


# ── LabelPrintJob CRUD + state transitions ───────────────────────

@pytest.mark.django_db
class TestLabelJobViews:
    def test_list_200(self, client_admin, print_job):
        r = client_admin.get(reverse('barcode_rfid:label_job_list'))
        assert r.status_code == 200
        assert print_job.job_number.encode() in r.content

    def test_list_status_filter(self, client_admin, print_job):
        r = client_admin.get(reverse('barcode_rfid:label_job_list'), {'status': 'draft'})
        assert r.status_code == 200

    def test_create_post(self, client_admin, tenant, label_template):
        r = client_admin.post(reverse('barcode_rfid:label_job_create'), {
            'template': label_template.pk,
            'target_type': 'product', 'target_display': 'ABC', 'quantity': 2,
            'notes': '',
        })
        assert r.status_code == 302
        assert LabelPrintJob.objects.filter(tenant=tenant, target_display='ABC').exists()

    def test_detail_404_for_other_tenant(self, client_other, print_job):
        r = client_other.get(reverse('barcode_rfid:label_job_detail', args=[print_job.pk]))
        assert r.status_code == 404

    def test_queue_transition_emits_audit(self, client_admin, tenant, print_job):
        r = client_admin.post(reverse('barcode_rfid:label_job_queue', args=[print_job.pk]))
        assert r.status_code == 302
        print_job.refresh_from_db()
        assert print_job.status == 'queued'
        assert AuditLog.objects.filter(
            tenant=tenant, action='queue', model_name='LabelPrintJob',
            changes='draft->queued',
        ).exists()

    def test_invalid_transition_does_not_mutate(self, client_admin, print_job):
        # draft → printed is invalid per VALID_TRANSITIONS.
        r = client_admin.post(reverse('barcode_rfid:label_job_mark_printed', args=[print_job.pk]))
        assert r.status_code == 302
        print_job.refresh_from_db()
        assert print_job.status == 'draft'

    def test_pdf_render_returns_pdf(self, client_admin, print_job):
        r = client_admin.get(reverse('barcode_rfid:label_job_pdf', args=[print_job.pk]))
        assert r.status_code == 200
        assert r['Content-Type'] == 'application/pdf'
        assert r.content.startswith(b'%PDF-')


# ── ScannerDevice CRUD + token rotation ──────────────────────────

@pytest.mark.django_db
class TestDeviceViews:
    def test_list_200(self, client_admin, scanner_device):
        r = client_admin.get(reverse('barcode_rfid:device_list'))
        assert r.status_code == 200

    def test_list_status_filter(self, client_admin, scanner_device):
        r = client_admin.get(reverse('barcode_rfid:device_list'), {'status': 'active'})
        assert r.status_code == 200
        assert scanner_device.device_code.encode() in r.content

    def test_create_post(self, client_admin, tenant):
        r = client_admin.post(reverse('barcode_rfid:device_create'), {
            'device_code': 'SCAN-NEW', 'name': 'New Dev',
            'device_type': 'handheld',
            'manufacturer': '', 'model_number': '', 'os_version': '', 'firmware_version': '',
            'status': 'active', 'is_active': True,
        })
        assert r.status_code == 302
        assert ScannerDevice.objects.filter(tenant=tenant, device_code='SCAN-NEW').exists()

    def test_detail_404_other_tenant(self, client_other, scanner_device):
        r = client_other.get(reverse('barcode_rfid:device_detail', args=[scanner_device.pk]))
        assert r.status_code == 404

    def test_rotate_token_changes_value(self, client_admin, tenant, scanner_device):
        old = scanner_device.api_token
        r = client_admin.post(reverse('barcode_rfid:device_rotate_token', args=[scanner_device.pk]))
        assert r.status_code == 302
        scanner_device.refresh_from_db()
        assert scanner_device.api_token != old
        assert AuditLog.objects.filter(
            tenant=tenant, action='rotate_token', model_name='ScannerDevice',
        ).exists()

    def test_delete_post(self, client_admin, scanner_device):
        pk = scanner_device.pk
        r = client_admin.post(reverse('barcode_rfid:device_delete', args=[pk]))
        assert r.status_code == 302
        assert not ScannerDevice.objects.filter(pk=pk).exists()


# ── ScanEvent ledger ─────────────────────────────────────────────

@pytest.mark.django_db
class TestScanEventViews:
    def test_list_200(self, client_admin):
        r = client_admin.get(reverse('barcode_rfid:scan_event_list'))
        assert r.status_code == 200

    def test_list_filter_scan_type(self, client_admin):
        r = client_admin.get(reverse('barcode_rfid:scan_event_list'), {'scan_type': 'lookup'})
        assert r.status_code == 200


# ── RFIDTag CRUD + transitions ───────────────────────────────────

@pytest.mark.django_db
class TestRFIDTagViews:
    def test_list_200(self, client_admin, rfid_tag):
        r = client_admin.get(reverse('barcode_rfid:rfid_tag_list'))
        assert r.status_code == 200
        assert rfid_tag.epc_code.encode() in r.content

    def test_create_post(self, client_admin, tenant):
        r = client_admin.post(reverse('barcode_rfid:rfid_tag_create'), {
            'epc_code': 'E200NEW', 'tag_type': 'passive', 'frequency_band': 'uhf',
            'linked_object_type': 'none', 'status': 'unassigned', 'notes': '',
        })
        assert r.status_code == 302
        assert RFIDTag.objects.filter(tenant=tenant, epc_code='E200NEW').exists()

    def test_detail_404_other_tenant(self, client_other, rfid_tag):
        r = client_other.get(reverse('barcode_rfid:rfid_tag_detail', args=[rfid_tag.pk]))
        assert r.status_code == 404

    def test_activate_transition(self, client_admin, tenant, rfid_tag):
        # unassigned → active is valid.
        r = client_admin.post(reverse('barcode_rfid:rfid_tag_activate', args=[rfid_tag.pk]))
        assert r.status_code == 302
        rfid_tag.refresh_from_db()
        assert rfid_tag.status == 'active'
        assert AuditLog.objects.filter(
            tenant=tenant, action='activate', changes='unassigned->active',
        ).exists()

    def test_invalid_transition_keeps_status(self, client_admin, rfid_tag):
        # unassigned → damaged is invalid.
        r = client_admin.post(reverse('barcode_rfid:rfid_tag_mark_damaged', args=[rfid_tag.pk]))
        assert r.status_code == 302
        rfid_tag.refresh_from_db()
        assert rfid_tag.status == 'unassigned'

    def test_delete_post(self, client_admin, rfid_tag):
        pk = rfid_tag.pk
        r = client_admin.post(reverse('barcode_rfid:rfid_tag_delete', args=[pk]))
        assert r.status_code == 302
        assert not RFIDTag.objects.filter(pk=pk).exists()


# ── RFIDReader CRUD ──────────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDReaderViews:
    def test_list_200(self, client_admin, rfid_reader):
        r = client_admin.get(reverse('barcode_rfid:rfid_reader_list'))
        assert r.status_code == 200

    def test_create_post(self, client_admin, tenant, warehouse):
        r = client_admin.post(reverse('barcode_rfid:rfid_reader_create'), {
            'reader_code': 'RDR-NEW', 'name': 'Gate NEW',
            'reader_type': 'fixed_gate', 'warehouse': warehouse.pk,
            'antenna_count': 1, 'frequency_band': 'uhf',
            'status': 'online', 'firmware_version': '', 'is_active': True,
        })
        assert r.status_code == 302
        assert RFIDReader.objects.filter(tenant=tenant, reader_code='RDR-NEW').exists()

    def test_detail_404_other_tenant(self, client_other, rfid_reader):
        r = client_other.get(reverse('barcode_rfid:rfid_reader_detail', args=[rfid_reader.pk]))
        assert r.status_code == 404


# ── RFIDReadEvent ledger ─────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDReadEventViews:
    def test_list_200(self, client_admin):
        r = client_admin.get(reverse('barcode_rfid:rfid_read_list'))
        assert r.status_code == 200


# ── BatchScanSession CRUD + transitions ──────────────────────────

@pytest.mark.django_db
class TestBatchSessionViews:
    def test_list_200(self, client_admin, batch_session):
        r = client_admin.get(reverse('barcode_rfid:batch_session_list'))
        assert r.status_code == 200
        assert batch_session.session_number.encode() in r.content

    def test_create_post(self, client_admin, tenant, warehouse):
        r = client_admin.post(reverse('barcode_rfid:batch_session_create'), {
            'purpose': 'receiving', 'warehouse': warehouse.pk, 'notes': '',
        })
        assert r.status_code == 302
        assert BatchScanSession.objects.filter(tenant=tenant).count() == 1

    def test_detail_404_other_tenant(self, client_other, batch_session):
        r = client_other.get(reverse('barcode_rfid:batch_session_detail', args=[batch_session.pk]))
        assert r.status_code == 404

    def test_complete_transition(self, client_admin, tenant, batch_session):
        r = client_admin.post(reverse('barcode_rfid:batch_session_complete', args=[batch_session.pk]))
        assert r.status_code == 302
        batch_session.refresh_from_db()
        assert batch_session.status == 'completed'
        assert AuditLog.objects.filter(
            tenant=tenant, action='complete', changes='active->completed',
        ).exists()

    def test_complete_after_completed_invalid(self, client_admin, batch_session):
        batch_session.status = 'completed'
        batch_session.save()
        r = client_admin.post(reverse('barcode_rfid:batch_session_complete', args=[batch_session.pk]))
        assert r.status_code == 302  # redirect with error message
        batch_session.refresh_from_db()
        assert batch_session.status == 'completed'  # unchanged
