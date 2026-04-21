"""Form validation tests."""
from datetime import date, timedelta

import pytest

from reporting.forms import ABCForm, TurnoverForm, ValuationForm


@pytest.mark.django_db
def test_abc_rejects_threshold_sum_ge_100(tenant):
    form = ABCForm(data={
        'title': 't', 'a_threshold': 60, 'b_threshold': 50,
    }, tenant=tenant)
    assert not form.is_valid()
    assert any('less than 100' in str(e) for e in form.non_field_errors())


@pytest.mark.django_db
def test_abc_accepts_default_thresholds(tenant):
    form = ABCForm(data={
        'title': 't', 'a_threshold': 80, 'b_threshold': 15,
    }, tenant=tenant)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_turnover_rejects_end_before_start(tenant):
    form = TurnoverForm(data={
        'title': 't',
        'period_start': (date.today()).isoformat(),
        'period_end': (date.today() - timedelta(days=10)).isoformat(),
    }, tenant=tenant)
    assert not form.is_valid()
    assert any('on or after' in str(e) for e in form.non_field_errors())


@pytest.mark.django_db
def test_valuation_form_tenant_scopes_warehouse_choices(tenant, other_tenant, warehouse, other_warehouse):
    """Form's warehouse queryset must only expose the current tenant's warehouses."""
    form = ValuationForm(tenant=tenant)
    wh_pks = list(form.fields['warehouse'].queryset.values_list('pk', flat=True))
    assert warehouse.pk in wh_pks
    assert other_warehouse.pk not in wh_pks


@pytest.mark.django_db
def test_valuation_rejects_foreign_tenant_warehouse(tenant, other_warehouse):
    """Submitting another tenant's warehouse pk must be rejected at form layer."""
    form = ValuationForm(data={
        'title': 't', 'warehouse': other_warehouse.pk,
    }, tenant=tenant)
    assert not form.is_valid()
    assert 'warehouse' in form.errors


@pytest.mark.django_db
def test_valuation_allows_no_warehouse(tenant):
    """warehouse is optional — submitting with blank should pass."""
    form = ValuationForm(data={'title': 't'}, tenant=tenant)
    assert form.is_valid(), form.errors
