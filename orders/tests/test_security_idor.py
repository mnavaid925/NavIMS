"""OWASP A01 — cross-tenant IDOR across every entity."""
import pytest
from django.urls import reverse

from orders.models import (
    Carrier, ShippingRate, PackingList, Shipment, WavePlan, PickList,
)


@pytest.mark.django_db
def test_so_detail_cross_tenant_returns_404(client_other, draft_so):
    url = reverse('orders:so_detail', args=[draft_so.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_so_edit_cross_tenant_returns_404(client_other, draft_so):
    url = reverse('orders:so_edit', args=[draft_so.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_so_delete_cross_tenant_returns_404(client_other, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    assert client_other.post(url).status_code == 404


@pytest.mark.django_db
def test_carrier_detail_cross_tenant_returns_404(client_other, tenant):
    c = Carrier.objects.create(tenant=tenant, name='X', code='X')
    url = reverse('orders:carrier_detail', args=[c.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_carrier_delete_cross_tenant_returns_404(client_other, tenant):
    c = Carrier.objects.create(tenant=tenant, name='X', code='X')
    url = reverse('orders:carrier_delete', args=[c.pk])
    assert client_other.post(url).status_code == 404


@pytest.mark.django_db
def test_shippingrate_cross_tenant_returns_404(client_other, tenant):
    c = Carrier.objects.create(tenant=tenant, name='X', code='X')
    r = ShippingRate.objects.create(
        tenant=tenant, carrier=c, service_level='Ground',
        base_cost=1, cost_per_kg=0, estimated_transit_days=1,
    )
    url = reverse('orders:shippingrate_edit', args=[r.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_picklist_cross_tenant_returns_404(client_other, picklist_pending):
    url = reverse('orders:picklist_detail', args=[picklist_pending.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_shipment_cross_tenant_returns_404(client_other, tenant, draft_so):
    sh = Shipment.objects.create(tenant=tenant, sales_order=draft_so)
    url = reverse('orders:shipment_detail', args=[sh.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_wave_cross_tenant_returns_404(client_other, tenant, warehouse):
    wave = WavePlan.objects.create(tenant=tenant, warehouse=warehouse)
    url = reverse('orders:wave_detail', args=[wave.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_anonymous_redirect_to_login(client, draft_so):
    url = reverse('orders:so_detail', args=[draft_so.pk])
    resp = client.get(url)
    assert resp.status_code == 302
    assert '/login' in resp['Location'].lower() or 'accounts' in resp['Location']
