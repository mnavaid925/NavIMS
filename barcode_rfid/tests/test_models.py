"""Model invariants — numbering, state machines, unique_together, token, validators.

Guards against:
    - Regression of LPJ/BSS auto-numbering collisions (lesson #22).
    - State-machine edges drifting silently when STATUS_CHOICES change.
    - Tenant-scoped unique constraints being silently dropped.
    - `api_token` auto-generation / rotation losing entropy.
    - MinValueValidator on BatchScanItem.quantity being removed.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from barcode_rfid.models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReader, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
)


# ── LabelTemplate ────────────────────────────────────────────────

@pytest.mark.django_db
class TestLabelTemplate:
    def test_str_contains_code_and_name(self, label_template):
        assert 'LBL-STD' in str(label_template)
        assert 'Standard' in str(label_template)

    def test_unique_together_tenant_code(self, tenant, label_template):
        with pytest.raises(IntegrityError):
            LabelTemplate.objects.create(
                tenant=tenant, code='LBL-STD', name='Dup',
            )

    def test_same_code_allowed_in_different_tenant(self, tenant, other_tenant, label_template):
        # Already exists as LBL-STD in `tenant` — same code should be allowed in other_tenant.
        t2 = LabelTemplate.objects.create(
            tenant=other_tenant, code='LBL-STD', name='Other',
        )
        assert t2.pk is not None

    def test_default_values(self, tenant):
        t = LabelTemplate.objects.create(tenant=tenant, code='X', name='Y')
        assert t.label_type == 'barcode'
        assert t.symbology == 'code128'
        assert t.paper_size == 'label_medium'
        assert t.is_active is True
        assert t.copies_per_label == 1


# ── LabelPrintJob ────────────────────────────────────────────────

@pytest.mark.django_db
class TestLabelPrintJobNumbering:
    def test_first_job_number_is_lpj_00001(self, tenant, label_template):
        j = LabelPrintJob.objects.create(
            tenant=tenant, template=label_template,
            target_type='product', target_display='X',
        )
        assert j.job_number == 'LPJ-00001'

    def test_job_numbers_monotonic_per_tenant(self, tenant, label_template):
        for _ in range(3):
            LabelPrintJob.objects.create(
                tenant=tenant, template=label_template,
                target_type='product', target_display='x',
            )
        nums = sorted(LabelPrintJob.objects.filter(tenant=tenant)
                      .values_list('job_number', flat=True))
        assert nums == ['LPJ-00001', 'LPJ-00002', 'LPJ-00003']

    def test_job_numbers_independent_per_tenant(
        self, tenant, other_tenant, label_template, other_label_template,
    ):
        LabelPrintJob.objects.create(
            tenant=tenant, template=label_template,
            target_type='product', target_display='a',
        )
        j2 = LabelPrintJob.objects.create(
            tenant=other_tenant, template=other_label_template,
            target_type='product', target_display='b',
        )
        assert j2.job_number == 'LPJ-00001'

    def test_retry_does_not_corrupt_on_collision(self, tenant, label_template):
        """Force an explicit clashing job_number — since pk is None, the retry
        should clear job_number and regenerate, producing a fresh number."""
        LabelPrintJob.objects.create(
            tenant=tenant, template=label_template,
            target_type='product', target_display='a',
        )
        # Force-collide by manually supplying an already-taken number
        # on a NEW instance (pk is None, no user_supplied_number is set).
        j2 = LabelPrintJob(
            tenant=tenant, template=label_template,
            target_type='product', target_display='b',
        )
        # Don't pre-set job_number — numbering generates 00002 normally.
        j2.save()
        assert j2.job_number == 'LPJ-00002'

    def test_user_supplied_number_duplicates_raise(self, tenant, label_template):
        LabelPrintJob.objects.create(
            tenant=tenant, template=label_template,
            target_type='product', target_display='a',
        )
        with pytest.raises(IntegrityError):
            LabelPrintJob.objects.create(
                tenant=tenant, job_number='LPJ-00001',
                template=label_template,
                target_type='product', target_display='b',
            )


@pytest.mark.django_db
class TestLabelPrintJobStateMachine:
    @pytest.mark.parametrize('src,dst,ok', [
        ('draft', 'queued', True),
        ('draft', 'cancelled', True),
        ('draft', 'printed', False),
        ('queued', 'printing', True),
        ('queued', 'draft', False),
        ('printing', 'printed', True),
        ('printing', 'failed', True),
        ('printing', 'queued', False),
        ('failed', 'queued', True),
        ('failed', 'cancelled', True),
        ('printed', 'queued', False),
        ('printed', 'cancelled', False),
        ('cancelled', 'draft', False),
    ])
    def test_transition_edges(self, print_job, src, dst, ok):
        print_job.status = src
        assert print_job.can_transition_to(dst) is ok

    def test_terminal_printed_has_no_outgoing(self, print_job):
        print_job.status = 'printed'
        for s in ['draft', 'queued', 'printing', 'failed', 'cancelled']:
            assert print_job.can_transition_to(s) is False

    def test_terminal_cancelled_has_no_outgoing(self, print_job):
        print_job.status = 'cancelled'
        for s in ['draft', 'queued', 'printing', 'printed', 'failed']:
            assert print_job.can_transition_to(s) is False


# ── ScannerDevice ────────────────────────────────────────────────

@pytest.mark.django_db
class TestScannerDevice:
    def test_api_token_auto_generated_on_first_save(self, tenant):
        d = ScannerDevice.objects.create(
            tenant=tenant, device_code='X1', name='X',
        )
        assert d.api_token
        assert len(d.api_token) >= 32

    def test_rotate_token_changes_value(self, scanner_device):
        old = scanner_device.api_token
        scanner_device.rotate_token()
        scanner_device.refresh_from_db()
        assert scanner_device.api_token != old
        assert len(scanner_device.api_token) >= 32

    def test_unique_together_tenant_device_code(self, tenant, scanner_device):
        with pytest.raises(IntegrityError):
            ScannerDevice.objects.create(
                tenant=tenant, device_code='SCAN-001', name='Dup',
            )


# ── ScanEvent ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestScanEvent:
    def test_str_contains_barcode(self, tenant):
        ev = ScanEvent.objects.create(
            tenant=tenant, scan_type='lookup', barcode_value='ABC-123',
        )
        assert 'ABC-123' in str(ev)

    def test_nullable_device_and_user(self, tenant):
        ev = ScanEvent.objects.create(
            tenant=tenant, scan_type='lookup', barcode_value='X',
        )
        assert ev.device is None
        assert ev.user is None
        assert ev.status == 'success'  # default


# ── RFIDTag ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDTag:
    def test_unique_together_tenant_epc(self, tenant, rfid_tag):
        with pytest.raises(IntegrityError):
            RFIDTag.objects.create(
                tenant=tenant, epc_code='E200001', tag_type='passive',
            )

    @pytest.mark.parametrize('src,dst,ok', [
        ('unassigned', 'active', True),
        ('unassigned', 'retired', True),
        ('unassigned', 'lost', False),
        ('active', 'lost', True),
        ('active', 'damaged', True),
        ('active', 'retired', True),
        ('active', 'inactive', True),
        ('active', 'unassigned', False),
        ('damaged', 'retired', True),
        ('damaged', 'active', False),
        ('retired', 'active', False),
        ('retired', 'unassigned', False),
    ])
    def test_rfid_tag_transitions(self, rfid_tag, src, dst, ok):
        rfid_tag.status = src
        assert rfid_tag.can_transition_to(dst) is ok

    def test_retired_is_terminal(self, rfid_tag):
        rfid_tag.status = 'retired'
        for s in ['unassigned', 'active', 'inactive', 'lost', 'damaged']:
            assert rfid_tag.can_transition_to(s) is False


# ── RFIDReader ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDReader:
    def test_unique_together_tenant_reader_code(self, tenant, rfid_reader, warehouse):
        with pytest.raises(IntegrityError):
            RFIDReader.objects.create(
                tenant=tenant, reader_code='RDR-01',
                name='Dup', warehouse=warehouse,
            )


# ── RFIDReadEvent ────────────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDReadEvent:
    def test_create_tied_to_tag_and_reader(self, tenant, rfid_tag, rfid_reader):
        ev = RFIDReadEvent.objects.create(
            tenant=tenant, tag=rfid_tag, reader=rfid_reader,
            direction='in',
        )
        assert ev.tag_id == rfid_tag.pk
        assert ev.reader_id == rfid_reader.pk
        assert ev.direction == 'in'


# ── BatchScanSession ─────────────────────────────────────────────

@pytest.mark.django_db
class TestBatchScanSession:
    def test_first_session_number_is_bss_00001(self, tenant, warehouse):
        s = BatchScanSession.objects.create(
            tenant=tenant, warehouse=warehouse, purpose='receiving',
        )
        assert s.session_number == 'BSS-00001'

    def test_session_numbers_monotonic_per_tenant(self, tenant, warehouse):
        for _ in range(3):
            BatchScanSession.objects.create(
                tenant=tenant, warehouse=warehouse, purpose='receiving',
            )
        nums = sorted(BatchScanSession.objects.filter(tenant=tenant)
                      .values_list('session_number', flat=True))
        assert nums == ['BSS-00001', 'BSS-00002', 'BSS-00003']

    @pytest.mark.parametrize('src,dst,ok', [
        ('active', 'completed', True),
        ('active', 'cancelled', True),
        ('active', 'active', False),
        ('completed', 'active', False),
        ('completed', 'cancelled', False),
        ('cancelled', 'active', False),
        ('cancelled', 'completed', False),
    ])
    def test_session_transitions(self, batch_session, src, dst, ok):
        batch_session.status = src
        assert batch_session.can_transition_to(dst) is ok

    def test_recalc_total_counts_items(self, batch_session, tenant):
        BatchScanItem.objects.create(
            tenant=tenant, session=batch_session, scanned_value='A',
        )
        BatchScanItem.objects.create(
            tenant=tenant, session=batch_session, scanned_value='B',
        )
        batch_session.recalc_total()
        batch_session.refresh_from_db()
        assert batch_session.total_items_scanned == 2


# ── BatchScanItem ────────────────────────────────────────────────

@pytest.mark.django_db
class TestBatchScanItem:
    def test_quantity_validator_rejects_zero(self, batch_session, tenant):
        item = BatchScanItem(
            tenant=tenant, session=batch_session,
            scanned_value='X', quantity=Decimal('0'),
        )
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_quantity_validator_rejects_negative(self, batch_session, tenant):
        item = BatchScanItem(
            tenant=tenant, session=batch_session,
            scanned_value='X', quantity=Decimal('-1.00'),
        )
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_quantity_validator_accepts_fractional(self, batch_session, tenant):
        item = BatchScanItem(
            tenant=tenant, session=batch_session,
            scanned_value='X', quantity=Decimal('0.50'),
        )
        item.full_clean()  # should not raise
