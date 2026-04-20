"""Integration tests for Quarantine views — CRUD, state transitions,
scrap auto-creation on disposition=scrap release, soft-delete.
"""
import pytest
from django.urls import reverse

from quality_control.models import QuarantineRecord, ScrapWriteOff


@pytest.mark.django_db
def test_quarantine_list_renders(client_admin):
    r = client_admin.get(reverse('quality_control:quarantine_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_quarantine_create(client_admin, tenant, product, warehouse, qc_zone):
    r = client_admin.post(
        reverse('quality_control:quarantine_create'),
        data={'product': product.pk, 'warehouse': warehouse.pk, 'zone': qc_zone.pk,
              'quantity': 3, 'reason': 'defect', 'reason_notes': 'demo'},
    )
    assert r.status_code == 302
    obj = QuarantineRecord.objects.get(tenant=tenant, product=product)
    assert obj.status == 'active'
    assert obj.quantity == 3
    assert obj.quarantine_number == 'QR-00001'


@pytest.mark.django_db
def test_quarantine_review_transition(client_admin, active_quarantine):
    r = client_admin.post(reverse('quality_control:quarantine_review', args=[active_quarantine.pk]))
    assert r.status_code == 302
    active_quarantine.refresh_from_db()
    assert active_quarantine.status == 'under_review'


@pytest.mark.django_db
def test_quarantine_release_return_to_stock(client_admin, active_quarantine):
    r = client_admin.post(
        reverse('quality_control:quarantine_release', args=[active_quarantine.pk]),
        data={'disposition': 'return_to_stock', 'notes': 'OK'},
    )
    assert r.status_code == 302
    active_quarantine.refresh_from_db()
    assert active_quarantine.status == 'released'
    assert active_quarantine.release_disposition == 'return_to_stock'
    assert ScrapWriteOff.objects.filter(quarantine_record=active_quarantine).count() == 0


@pytest.mark.django_db
def test_quarantine_release_scrap_auto_creates_scrap(client_admin, active_quarantine, tenant):
    r = client_admin.post(
        reverse('quality_control:quarantine_release', args=[active_quarantine.pk]),
        data={'disposition': 'scrap', 'notes': 'damage beyond repair'},
    )
    assert r.status_code == 302
    active_quarantine.refresh_from_db()
    assert active_quarantine.status == 'scrapped'
    scrap = ScrapWriteOff.objects.get(
        tenant=tenant, quarantine_record=active_quarantine,
    )
    assert scrap.approval_status == 'pending'
    assert scrap.quantity == active_quarantine.quantity


@pytest.mark.django_db
def test_quarantine_release_from_terminal_rejected(client_admin, active_quarantine):
    active_quarantine.status = 'released'
    active_quarantine.save(update_fields=['status'])
    r = client_admin.post(
        reverse('quality_control:quarantine_release', args=[active_quarantine.pk]),
        data={'disposition': 'return_to_stock', 'notes': ''},
    )
    # redirect with error message; state unchanged
    assert r.status_code == 302
    active_quarantine.refresh_from_db()
    assert active_quarantine.status == 'released'
    assert active_quarantine.released_at is None


@pytest.mark.django_db
def test_quarantine_soft_delete_only_while_active(client_admin, active_quarantine):
    r = client_admin.post(reverse('quality_control:quarantine_delete', args=[active_quarantine.pk]))
    assert r.status_code == 302
    active_quarantine.refresh_from_db()
    assert active_quarantine.deleted_at is not None


@pytest.mark.django_db
def test_quarantine_delete_while_released_rejected(client_admin, active_quarantine):
    active_quarantine.status = 'released'
    active_quarantine.save(update_fields=['status'])
    r = client_admin.post(reverse('quality_control:quarantine_delete', args=[active_quarantine.pk]))
    assert r.status_code == 302
    active_quarantine.refresh_from_db()
    assert active_quarantine.deleted_at is None


@pytest.mark.django_db
def test_quarantine_cross_tenant_404(client_other, active_quarantine):
    r = client_other.get(reverse('quality_control:quarantine_detail', args=[active_quarantine.pk]))
    assert r.status_code == 404
