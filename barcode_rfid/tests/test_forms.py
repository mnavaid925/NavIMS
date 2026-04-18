"""Form-layer validation — TenantUniqueCodeMixin, tenant-scoped querysets,
cross-warehouse zone guard, passive/battery rule.

Guards against:
    - Lesson #6: `unique_together(tenant, X)` bypassed when tenant isn't a form field.
    - Cross-tenant FK forgery via POST (lesson #9 — "forms filter only in GET").
    - Zone-vs-warehouse mismatch (multi-tenant single-tenant cross-warehouse).
"""
from decimal import Decimal

import pytest

from warehousing.models import Warehouse, Zone

from barcode_rfid.forms import (
    LabelTemplateForm, LabelPrintJobForm,
    ScannerDeviceForm,
    RFIDTagForm, RFIDReaderForm,
    BatchScanSessionForm,
)
from barcode_rfid.models import LabelTemplate, ScannerDevice, RFIDTag


# ── LabelTemplateForm ────────────────────────────────────────────

@pytest.mark.django_db
class TestLabelTemplateForm:
    def test_duplicate_code_same_tenant_rejected(self, tenant, label_template):
        form = LabelTemplateForm(
            {'name': 'Dup', 'code': 'LBL-STD',
             'label_type': 'barcode', 'symbology': 'code128', 'paper_size': 'label_medium',
             'width_mm': 60, 'height_mm': 40, 'copies_per_label': 1},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'code' in form.errors

    def test_same_code_different_tenant_allowed(self, other_tenant, label_template):
        form = LabelTemplateForm(
            {'name': 'Also', 'code': 'LBL-STD',
             'label_type': 'barcode', 'symbology': 'code128', 'paper_size': 'label_medium',
             'width_mm': 60, 'height_mm': 40, 'copies_per_label': 1},
            tenant=other_tenant,
        )
        assert form.is_valid(), form.errors

    def test_save_injects_tenant(self, tenant):
        form = LabelTemplateForm(
            {'name': 'X', 'code': 'NEW',
             'label_type': 'barcode', 'symbology': 'code128', 'paper_size': 'label_medium',
             'width_mm': 60, 'height_mm': 40, 'copies_per_label': 1},
            tenant=tenant,
        )
        assert form.is_valid(), form.errors
        obj = form.save()
        assert obj.tenant_id == tenant.pk


# ── LabelPrintJobForm ────────────────────────────────────────────

@pytest.mark.django_db
class TestLabelPrintJobForm:
    def test_template_queryset_filtered_to_tenant(
        self, tenant, other_tenant, label_template, other_label_template,
    ):
        form = LabelPrintJobForm(tenant=tenant)
        qs = form.fields['template'].queryset
        pks = set(qs.values_list('pk', flat=True))
        assert label_template.pk in pks
        assert other_label_template.pk not in pks

    def test_template_queryset_excludes_inactive(self, tenant, label_template):
        inactive = LabelTemplate.objects.create(
            tenant=tenant, code='LBL-INACTIVE', name='Off', is_active=False,
        )
        form = LabelPrintJobForm(tenant=tenant)
        pks = set(form.fields['template'].queryset.values_list('pk', flat=True))
        assert label_template.pk in pks
        assert inactive.pk not in pks

    def test_quantity_rejects_zero(self, tenant, label_template):
        form = LabelPrintJobForm(
            {'template': label_template.pk, 'target_type': 'product',
             'target_display': 'X', 'quantity': 0, 'notes': ''},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_save_injects_tenant(self, tenant, label_template):
        form = LabelPrintJobForm(
            {'template': label_template.pk, 'target_type': 'product',
             'target_display': 'X', 'quantity': 3, 'notes': ''},
            tenant=tenant,
        )
        assert form.is_valid(), form.errors
        obj = form.save()
        assert obj.tenant_id == tenant.pk


# ── ScannerDeviceForm ────────────────────────────────────────────

@pytest.mark.django_db
class TestScannerDeviceForm:
    def test_duplicate_device_code_rejected(self, tenant, scanner_device):
        form = ScannerDeviceForm(
            {'device_code': 'SCAN-001', 'name': 'Dup',
             'device_type': 'handheld', 'manufacturer': '', 'model_number': '',
             'os_version': '', 'firmware_version': '',
             'status': 'active', 'is_active': True},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'device_code' in form.errors

    def test_assigned_warehouse_queryset_filtered_to_tenant(
        self, tenant, warehouse, other_warehouse,
    ):
        form = ScannerDeviceForm(tenant=tenant)
        pks = set(form.fields['assigned_warehouse'].queryset.values_list('pk', flat=True))
        assert warehouse.pk in pks
        assert other_warehouse.pk not in pks


# ── RFIDTagForm ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDTagForm:
    def test_duplicate_epc_same_tenant_rejected(self, tenant, rfid_tag):
        form = RFIDTagForm(
            {'epc_code': 'E200001', 'tag_type': 'passive', 'frequency_band': 'uhf',
             'linked_object_type': 'none', 'status': 'unassigned', 'notes': ''},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'epc_code' in form.errors

    def test_passive_with_battery_rejected(self, tenant):
        form = RFIDTagForm(
            {'epc_code': 'E200NEW', 'tag_type': 'passive', 'frequency_band': 'uhf',
             'linked_object_type': 'none', 'status': 'unassigned',
             'battery_voltage': '3.00', 'notes': ''},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'battery_voltage' in form.errors

    def test_active_with_battery_allowed(self, tenant):
        form = RFIDTagForm(
            {'epc_code': 'E200A', 'tag_type': 'active', 'frequency_band': 'uhf',
             'linked_object_type': 'none', 'status': 'unassigned',
             'battery_voltage': '3.30', 'notes': ''},
            tenant=tenant,
        )
        assert form.is_valid(), form.errors


# ── RFIDReaderForm ───────────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDReaderForm:
    def test_duplicate_reader_code_rejected(self, tenant, rfid_reader, warehouse):
        form = RFIDReaderForm(
            {'reader_code': 'RDR-01', 'name': 'Dup',
             'reader_type': 'fixed_gate', 'warehouse': warehouse.pk,
             'antenna_count': 1, 'frequency_band': 'uhf',
             'status': 'online', 'firmware_version': '', 'is_active': True},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'reader_code' in form.errors

    def test_zone_from_other_warehouse_rejected(self, tenant, warehouse):
        # Build a second warehouse in the SAME tenant, with its own zone.
        wh2 = Warehouse.objects.create(
            tenant=tenant, code='WH2', name='Second WH', is_active=True,
        )
        zone2 = Zone.objects.create(
            tenant=tenant, warehouse=wh2, code='Z2', name='Zone 2',
        )
        form = RFIDReaderForm(
            {'reader_code': 'RDR-02', 'name': 'Gate 2',
             'reader_type': 'fixed_gate',
             'warehouse': warehouse.pk, 'zone': zone2.pk,
             'antenna_count': 1, 'frequency_band': 'uhf',
             'status': 'online', 'firmware_version': '', 'is_active': True},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'zone' in form.errors


# ── BatchScanSessionForm ─────────────────────────────────────────

@pytest.mark.django_db
class TestBatchScanSessionForm:
    def test_zone_from_other_warehouse_rejected(self, tenant, warehouse):
        wh2 = Warehouse.objects.create(
            tenant=tenant, code='WH2', name='Second WH', is_active=True,
        )
        zone2 = Zone.objects.create(
            tenant=tenant, warehouse=wh2, code='Z2', name='Zone 2',
        )
        form = BatchScanSessionForm(
            {'purpose': 'receiving', 'warehouse': warehouse.pk, 'zone': zone2.pk,
             'notes': ''},
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'zone' in form.errors

    def test_warehouse_queryset_scoped_to_tenant(
        self, tenant, warehouse, other_warehouse,
    ):
        form = BatchScanSessionForm(tenant=tenant)
        pks = set(form.fields['warehouse'].queryset.values_list('pk', flat=True))
        assert warehouse.pk in pks
        assert other_warehouse.pk not in pks
