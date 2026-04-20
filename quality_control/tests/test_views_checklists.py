"""Integration tests for the QC Checklist views.

Covers: CRUD happy paths, tenant scoping (IDOR 404), toggle-active,
non-admin forbidden, audit log emission.
"""
import pytest
from django.urls import reverse

from core.models import AuditLog
from quality_control.models import QCChecklist


@pytest.mark.django_db
def test_checklist_list_renders(client_admin):
    r = client_admin.get(reverse('quality_control:checklist_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_checklist_create_auto_numbers(client_admin, tenant):
    r = client_admin.post(
        reverse('quality_control:checklist_create'),
        data={
            'name': 'New Checklist', 'description': 'x',
            'applies_to': 'all', 'is_mandatory': 'on', 'is_active': 'on',
            'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        },
    )
    assert r.status_code == 302
    obj = QCChecklist.objects.get(tenant=tenant, name='New Checklist')
    assert obj.code == 'QCC-00001'
    assert obj.tenant == tenant


@pytest.mark.django_db
def test_checklist_create_emits_audit(client_admin, tenant):
    before = AuditLog.objects.count()
    client_admin.post(
        reverse('quality_control:checklist_create'),
        data={
            'name': 'Audit probe', 'applies_to': 'all',
            'is_mandatory': 'on', 'is_active': 'on',
            'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        },
    )
    assert AuditLog.objects.count() == before + 1
    entry = AuditLog.objects.latest('id')
    assert entry.model_name == 'QCChecklist'
    assert entry.action == 'create'


@pytest.mark.django_db
def test_checklist_detail_cross_tenant_404(client_other, checklist):
    r = client_other.get(reverse('quality_control:checklist_detail', args=[checklist.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
def test_checklist_edit_cross_tenant_404(client_other, checklist):
    r = client_other.get(reverse('quality_control:checklist_edit', args=[checklist.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
def test_checklist_delete_cross_tenant_404(client_other, checklist):
    r = client_other.post(reverse('quality_control:checklist_delete', args=[checklist.pk]))
    assert r.status_code == 404
    assert QCChecklist.objects.filter(pk=checklist.pk).exists()


@pytest.mark.django_db
def test_checklist_toggle_active(client_admin, checklist):
    assert checklist.is_active is True
    r = client_admin.post(reverse('quality_control:checklist_toggle_active', args=[checklist.pk]))
    assert r.status_code == 302
    checklist.refresh_from_db()
    assert checklist.is_active is False


@pytest.mark.django_db
def test_checklist_non_admin_cannot_create(client_user):
    r = client_user.post(
        reverse('quality_control:checklist_create'),
        data={'name': 'X', 'applies_to': 'all'},
    )
    assert r.status_code in (302, 403)
