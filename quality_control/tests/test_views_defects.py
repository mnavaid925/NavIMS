"""Integration tests for Defect Report views — CRUD, state transitions,
photo deletion (D-11 gate), cross-tenant isolation.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from io import BytesIO

from quality_control.models import DefectReport, DefectPhoto


def _png_bytes():
    buf = BytesIO()
    Image.new('RGB', (4, 4), color='red').save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


@pytest.mark.django_db
def test_defect_list_renders(client_admin):
    r = client_admin.get(reverse('quality_control:defect_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_defect_create(client_admin, tenant, product, warehouse):
    r = client_admin.post(
        reverse('quality_control:defect_create'),
        data={
            'product': product.pk, 'warehouse': warehouse.pk,
            'quantity_affected': 1, 'defect_type': 'visual',
            'severity': 'minor', 'source': 'receiving',
            'description': 'cosmetic issue',
            'photos-TOTAL_FORMS': '0', 'photos-INITIAL_FORMS': '0',
            'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '1000',
        },
    )
    assert r.status_code == 302
    d = DefectReport.objects.get(tenant=tenant, description='cosmetic issue')
    assert d.status == 'open'
    assert d.defect_number == 'DEF-00001'


@pytest.mark.django_db
def test_defect_investigate_then_resolve(client_admin, open_defect):
    r = client_admin.post(reverse('quality_control:defect_investigate', args=[open_defect.pk]))
    assert r.status_code == 302
    open_defect.refresh_from_db()
    assert open_defect.status == 'investigating'

    r = client_admin.post(reverse('quality_control:defect_resolve', args=[open_defect.pk]))
    open_defect.refresh_from_db()
    assert open_defect.status == 'resolved'
    assert open_defect.resolved_by is not None
    assert open_defect.resolved_at is not None


@pytest.mark.django_db
def test_defect_resolve_from_terminal_rejected(client_admin, open_defect):
    open_defect.status = 'resolved'
    open_defect.save(update_fields=['status'])
    r = client_admin.post(reverse('quality_control:defect_investigate', args=[open_defect.pk]))
    assert r.status_code == 302
    open_defect.refresh_from_db()
    assert open_defect.status == 'resolved'


@pytest.mark.django_db
def test_defect_delete_only_while_open(client_admin, open_defect):
    open_defect.status = 'investigating'
    open_defect.save(update_fields=['status'])
    r = client_admin.post(reverse('quality_control:defect_delete', args=[open_defect.pk]))
    assert r.status_code == 302
    open_defect.refresh_from_db()
    assert open_defect.deleted_at is None  # not deleted


@pytest.mark.django_db
def test_D11_photo_delete_blocked_when_resolved(client_admin, tenant, open_defect):
    photo = DefectPhoto.objects.create(
        tenant=tenant, defect_report=open_defect,
        image=SimpleUploadedFile('p.png', _png_bytes(), content_type='image/png'),
    )
    open_defect.status = 'resolved'
    open_defect.save(update_fields=['status'])
    r = client_admin.post(
        reverse('quality_control:defect_photo_delete', args=[open_defect.pk, photo.pk]),
    )
    assert r.status_code == 302
    assert DefectPhoto.objects.filter(pk=photo.pk).exists(), 'Photo should remain — defect is resolved'


@pytest.mark.django_db
def test_D11_photo_delete_allowed_while_open(client_admin, tenant, open_defect):
    photo = DefectPhoto.objects.create(
        tenant=tenant, defect_report=open_defect,
        image=SimpleUploadedFile('p.png', _png_bytes(), content_type='image/png'),
    )
    r = client_admin.post(
        reverse('quality_control:defect_photo_delete', args=[open_defect.pk, photo.pk]),
    )
    assert r.status_code == 302
    assert not DefectPhoto.objects.filter(pk=photo.pk).exists()


@pytest.mark.django_db
def test_defect_cross_tenant_404(client_other, open_defect):
    r = client_other.get(reverse('quality_control:defect_detail', args=[open_defect.pk]))
    assert r.status_code == 404
