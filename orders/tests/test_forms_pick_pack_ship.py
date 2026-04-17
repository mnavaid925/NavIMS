from datetime import timedelta

import pytest
from django.utils import timezone

from orders.forms import (
    PickListItemFormSet, PickListAssignForm, ShipmentTrackingForm,
)


def _pl_data(**items):
    data = {
        'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
    }
    defaults = {
        'ordered_quantity': '10', 'picked_quantity': '5', 'notes': '',
    }
    for k, v in {**defaults, **items}.items():
        data[f'items-0-{k}'] = str(v)
    return data


@pytest.mark.django_db
def test_picklist_item_cross_tenant_product_rejected(
    tenant, picklist_pending, other_product, bin_location,
):
    """Regression for D-03 — IDOR through product FK."""
    data = _pl_data(product=other_product.pk, bin_location=bin_location.pk)
    fs = PickListItemFormSet(
        data, instance=picklist_pending, prefix='items',
        form_kwargs={'tenant': tenant},
    )
    assert not fs.is_valid()


@pytest.mark.django_db
def test_picklist_item_cross_tenant_bin_rejected(
    tenant, picklist_pending, product, other_bin,
):
    """Regression for D-03 — IDOR through bin_location FK."""
    data = _pl_data(product=product.pk, bin_location=other_bin.pk)
    fs = PickListItemFormSet(
        data, instance=picklist_pending, prefix='items',
        form_kwargs={'tenant': tenant},
    )
    assert not fs.is_valid()


@pytest.mark.django_db
def test_picklist_picked_exceeds_ordered_rejected(
    tenant, picklist_pending, product, bin_location,
):
    """Regression for D-04d."""
    data = _pl_data(
        product=product.pk, bin_location=bin_location.pk,
        ordered_quantity=10, picked_quantity=999,
    )
    fs = PickListItemFormSet(
        data, instance=picklist_pending, prefix='items',
        form_kwargs={'tenant': tenant},
    )
    assert not fs.is_valid()


@pytest.mark.django_db
def test_picklist_picked_within_ordered_accepted(
    tenant, picklist_pending, product, bin_location,
):
    data = _pl_data(
        product=product.pk, bin_location=bin_location.pk,
        ordered_quantity=10, picked_quantity=5,
    )
    fs = PickListItemFormSet(
        data, instance=picklist_pending, prefix='items',
        form_kwargs={'tenant': tenant},
    )
    assert fs.is_valid(), fs.errors


@pytest.mark.django_db
def test_tracking_event_future_date_rejected(tenant):
    """Regression for D-12."""
    form = ShipmentTrackingForm(data={
        'status': 'In Transit', 'location': '', 'description': '',
        'event_date': (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M'),
    })
    assert not form.is_valid()


@pytest.mark.django_db
def test_picklist_assign_form_filters_by_tenant(tenant, tenant_user, other_tenant_admin):
    form = PickListAssignForm(tenant=tenant)
    qs = form.fields['assigned_to'].queryset
    assert tenant_user in qs
    assert other_tenant_admin not in qs
