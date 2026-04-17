"""Regression for D-06 — destructive/state-change views require tenant admin."""
import pytest
from django.urls import reverse

from orders.models import Carrier, SalesOrder


@pytest.mark.django_db
def test_so_delete_requires_tenant_admin(client_user, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    resp = client_user.post(url)
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', [
    'orders:so_confirm', 'orders:so_cancel', 'orders:so_hold',
    'orders:so_resume', 'orders:so_close', 'orders:so_reopen',
    'orders:so_generate_picklist', 'orders:so_delete', 'orders:so_edit',
])
def test_so_mutations_require_tenant_admin(client_user, draft_so, url_name):
    url = reverse(url_name, args=[draft_so.pk])
    resp = client_user.post(url)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_carrier_create_requires_tenant_admin(client_user):
    url = reverse('orders:carrier_create')
    resp = client_user.post(url, {'name': 'X', 'code': 'X'})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_carrier_delete_requires_tenant_admin(client_user, tenant):
    c = Carrier.objects.create(tenant=tenant, name='X', code='X')
    url = reverse('orders:carrier_delete', args=[c.pk])
    resp = client_user.post(url)
    assert resp.status_code == 403
    # Not deleted
    assert Carrier.objects.filter(pk=c.pk).exists()


@pytest.mark.django_db
def test_so_list_does_not_require_tenant_admin(client_user):
    # Read-only endpoints stay on @login_required only
    url = reverse('orders:so_list')
    resp = client_user.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_tenant_admin_can_delete_so(client_admin, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    resp = client_admin.post(url)
    assert resp.status_code == 302
    assert not SalesOrder.objects.filter(pk=draft_so.pk).exists()
