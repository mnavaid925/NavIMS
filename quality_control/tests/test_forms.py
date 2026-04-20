"""Form-layer tests for quality_control — clean() rules, scope guards,
zone-vs-warehouse cross-validation, and the D-04 queryset-union regression.
"""
import pytest
from decimal import Decimal

from quality_control.models import QCChecklist, DefectPhoto
from quality_control.forms import (
    QCChecklistForm,
    InspectionRouteForm,
    InspectionRouteRuleFormSet,
    QuarantineRecordForm,
    DefectReportForm,
    DefectPhotoForm,
    ScrapWriteOffForm,
)


# ── Checklist scope guards (R-02) ───────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize('applies_to, fk_field', [
    ('product', 'product'),
    ('vendor', 'vendor'),
    ('category', 'category'),
])
def test_checklist_requires_scope_fk(tenant, applies_to, fk_field):
    form = QCChecklistForm(
        data={'name': 'X', 'applies_to': applies_to, 'is_mandatory': 'on'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert fk_field in form.errors


@pytest.mark.django_db
def test_checklist_all_scope_accepts_empty_fks(tenant):
    form = QCChecklistForm(
        data={'name': 'All scope', 'applies_to': 'all', 'is_mandatory': 'on'},
        tenant=tenant,
    )
    assert form.is_valid(), form.errors


# ── Route zone-vs-warehouse cross-validation (R-03) ─────────────

@pytest.mark.django_db
def test_route_qc_zone_must_belong_to_warehouse(tenant, warehouse, alien_zone):
    form = InspectionRouteForm(
        data={'name': 'R', 'source_warehouse': warehouse.pk,
              'qc_zone': alien_zone.pk, 'priority': 100, 'is_active': 'on'},
        tenant=tenant,
    )
    # alien_zone belongs to another tenant — not in queryset.
    assert not form.is_valid()
    assert 'qc_zone' in form.errors


@pytest.mark.django_db
def test_route_putaway_zone_cross_warehouse_rejected(tenant, warehouse, qc_zone):
    from warehousing.models import Warehouse, Zone
    wh2 = Warehouse.objects.create(tenant=tenant, code='WH2', name='Secondary', is_active=True)
    zone2 = Zone.objects.create(tenant=tenant, warehouse=wh2, code='Z2', name='Storage 2', zone_type='storage')
    form = InspectionRouteForm(
        data={'name': 'R', 'source_warehouse': warehouse.pk,
              'qc_zone': qc_zone.pk, 'putaway_zone': zone2.pk,
              'priority': 100, 'is_active': 'on'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'putaway_zone' in form.errors


# ── Quarantine quantity + zone-of-warehouse ──────────────────────

@pytest.mark.django_db
def test_quarantine_quantity_positive(tenant, product, warehouse, qc_zone):
    form = QuarantineRecordForm(
        data={'product': product.pk, 'warehouse': warehouse.pk, 'zone': qc_zone.pk,
              'quantity': 0, 'reason': 'defect'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'quantity' in form.errors


# ── Scrap boundary checks ────────────────────────────────────────

@pytest.mark.django_db
def test_scrap_unit_cost_non_negative(tenant, product, warehouse):
    form = ScrapWriteOffForm(
        data={'product': product.pk, 'warehouse': warehouse.pk,
              'quantity': 1, 'unit_cost': '-1.0', 'reason': 'x'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'unit_cost' in form.errors


@pytest.mark.django_db
def test_scrap_quantity_positive(tenant, product, warehouse):
    form = ScrapWriteOffForm(
        data={'product': product.pk, 'warehouse': warehouse.pk,
              'quantity': 0, 'unit_cost': '1.00', 'reason': 'x'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'quantity' in form.errors


# ── D-04 regression: queryset union keeps historical records editable ─

@pytest.mark.django_db
def test_D04_checklist_edit_after_product_deactivated(tenant, tenant_admin, product):
    """Deactivating a product must not block re-saving a historical checklist."""
    c = QCChecklist.objects.create(
        tenant=tenant, name='hist', applies_to='product', product=product,
        created_by=tenant_admin,
    )
    product.is_active = False; product.save()

    form = QCChecklistForm(instance=c, tenant=tenant)
    assert product in form.fields['product'].queryset

    form2 = QCChecklistForm(
        data={'code': c.code, 'name': c.name, 'applies_to': 'product',
              'product': product.pk, 'is_mandatory': 'on', 'is_active': 'on'},
        instance=c, tenant=tenant,
    )
    assert form2.is_valid(), form2.errors


# ── D-07 regression: defect form cross-validates lot/serial ─────

@pytest.mark.django_db
def test_D07_defect_lot_must_match_product(tenant, product, product_b, warehouse):
    from lot_tracking.models import LotBatch
    lot_b = LotBatch.objects.create(
        tenant=tenant, product=product_b, lot_number='LOT-B01', status='active',
        warehouse=warehouse, quantity=10, available_quantity=10,
    )
    form = DefectReportForm(
        data={'product': product.pk, 'warehouse': warehouse.pk,
              'quantity_affected': 1, 'defect_type': 'visual',
              'severity': 'minor', 'source': 'receiving',
              'description': 'x', 'lot': lot_b.pk},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'lot' in form.errors


# ── D-08 regression: route rule scope guard ─────────────────────

@pytest.mark.django_db
def test_D08_route_rule_product_scope_requires_product(tenant, route):
    data = {
        'rules-TOTAL_FORMS': '1',
        'rules-INITIAL_FORMS': '0',
        'rules-MIN_NUM_FORMS': '0',
        'rules-MAX_NUM_FORMS': '1000',
        'rules-0-applies_to': 'product',
        'rules-0-product': '',          # missing FK
        'rules-0-vendor': '',
        'rules-0-category': '',
        'rules-0-checklist': '',
        'rules-0-notes': 'scoped rule',
    }
    formset = InspectionRouteRuleFormSet(data, instance=route, form_kwargs={'tenant': tenant})
    assert not formset.is_valid()
    assert any('product' in errs for errs in formset.errors)


# ── D-03 regression: upload hygiene on DefectPhotoForm ──────────

@pytest.mark.django_db
def test_D03_defect_photo_extension_whitelist(tenant):
    from django.core.files.uploadedfile import SimpleUploadedFile
    # Extension is correct but content is clearly not an image.
    bad = SimpleUploadedFile('note.txt', b'hello world', content_type='text/plain')
    form = DefectPhotoForm(data={'caption': 'x'}, files={'image': bad})
    assert not form.is_valid()
    assert 'image' in form.errors


@pytest.mark.django_db
def test_D03_defect_photo_size_cap_via_validator(tenant):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from quality_control.models import DEFECT_PHOTO_MAX_BYTES
    # Build an image-sized payload that trips the size validator without
    # triggering the whole-request DATA_UPLOAD cap (which fires earlier and
    # raises 413). Use a small blob and mock .size.
    big = SimpleUploadedFile('huge.jpg', b'\xff\xd8\xff\xe0' + b'\x00' * 100, content_type='image/jpeg')
    big.size = DEFECT_PHOTO_MAX_BYTES + 1
    form = DefectPhotoForm(data={'caption': 'x'}, files={'image': big})
    assert not form.is_valid()
    assert 'image' in form.errors
