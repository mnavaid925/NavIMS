"""Integration tests for Inspection Route views."""
import pytest
from django.urls import reverse

from quality_control.models import InspectionRoute


@pytest.mark.django_db
def test_route_list_renders(client_admin):
    r = client_admin.get(reverse('quality_control:route_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_route_create_auto_numbers(client_admin, tenant, warehouse, qc_zone, storage_zone):
    r = client_admin.post(
        reverse('quality_control:route_create'),
        data={
            'name': 'Standard', 'source_warehouse': warehouse.pk,
            'qc_zone': qc_zone.pk, 'putaway_zone': storage_zone.pk,
            'priority': 100, 'is_active': 'on',
            'rules-TOTAL_FORMS': '0', 'rules-INITIAL_FORMS': '0',
            'rules-MIN_NUM_FORMS': '0', 'rules-MAX_NUM_FORMS': '1000',
        },
    )
    assert r.status_code == 302
    obj = InspectionRoute.objects.get(tenant=tenant, name='Standard')
    assert obj.code == 'IR-00001'


@pytest.mark.django_db
def test_route_detail_cross_tenant_404(client_other, route):
    r = client_other.get(reverse('quality_control:route_detail', args=[route.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
def test_route_delete_cascades_rules(client_admin, route, checklist, product):
    from quality_control.models import InspectionRouteRule
    InspectionRouteRule.objects.create(
        tenant=route.tenant, route=route, applies_to='product',
        product=product, checklist=checklist,
    )
    assert route.rules.count() == 1
    r = client_admin.post(reverse('quality_control:route_delete', args=[route.pk]))
    assert r.status_code == 302
    assert not InspectionRoute.objects.filter(pk=route.pk).exists()
    assert InspectionRouteRule.objects.count() == 0
