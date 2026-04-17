import pytest

from orders.forms import CarrierForm
from orders.models import Carrier


def _base_data(**overrides):
    data = {
        'name': 'Test Carrier', 'code': 'TC',
        'contact_email': '', 'contact_phone': '',
        'api_endpoint': '', 'api_key': '', 'notes': '',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_carrier_form_valid(tenant):
    form = CarrierForm(data=_base_data(code='NEW'), tenant=tenant)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_duplicate_code_same_tenant_rejected(tenant):
    """Regression for D-01 — `unique_together(tenant, code)` without form guard."""
    Carrier.objects.create(tenant=tenant, name='A', code='FEDEX')
    form = CarrierForm(data=_base_data(name='B', code='FEDEX'), tenant=tenant)
    assert not form.is_valid()
    assert 'code' in form.errors


@pytest.mark.django_db
def test_duplicate_code_case_insensitive(tenant):
    Carrier.objects.create(tenant=tenant, name='A', code='FEDEX')
    form = CarrierForm(data=_base_data(code='fedex'), tenant=tenant)
    assert not form.is_valid()


@pytest.mark.django_db
def test_duplicate_code_cross_tenant_allowed(tenant, other_tenant):
    Carrier.objects.create(tenant=tenant, name='A', code='FEDEX')
    form = CarrierForm(data=_base_data(code='FEDEX'), tenant=other_tenant)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_edit_own_carrier_does_not_self_reject(tenant):
    carrier = Carrier.objects.create(tenant=tenant, name='A', code='FEDEX')
    form = CarrierForm(
        data=_base_data(name='A2', code='FEDEX'),
        instance=carrier, tenant=tenant,
    )
    assert form.is_valid(), form.errors
