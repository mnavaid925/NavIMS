from datetime import date
from decimal import Decimal

import pytest

from returns.forms import (
    ReturnAuthorizationForm, ReturnAuthorizationItemFormSet,
)
from returns.models import ReturnAuthorizationItem


pytestmark = pytest.mark.django_db


def _rma_form_data(delivered_so, warehouse):
    return {
        'sales_order': delivered_so.pk,
        'customer_name': 'Alice',
        'customer_email': '',
        'customer_phone': '',
        'return_address': '',
        'reason': 'defective',
        'requested_date': '2026-04-18',
        'expected_return_date': '',
        'warehouse': warehouse.pk,
        'notes': '',
    }


def _item_formset_data(product, qty=1, price='10.00'):
    return {
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-product': product.pk,
        'items-0-description': '',
        'items-0-qty_requested': str(qty),
        'items-0-unit_price': price,
        'items-0-reason_note': '',
    }


class TestReturnAuthorizationForm:
    def test_valid_form(self, tenant, delivered_so, warehouse):
        form = ReturnAuthorizationForm(
            data=_rma_form_data(delivered_so, warehouse), tenant=tenant,
        )
        assert form.is_valid(), form.errors

    def test_sales_order_queryset_scoped_to_tenant(self, tenant, delivered_so,
                                                   other_delivered_so):
        form = ReturnAuthorizationForm(tenant=tenant)
        assert delivered_so in form.fields['sales_order'].queryset
        assert other_delivered_so not in form.fields['sales_order'].queryset

    def test_warehouse_queryset_scoped_to_tenant(self, tenant, warehouse, other_warehouse):
        form = ReturnAuthorizationForm(tenant=tenant)
        assert warehouse in form.fields['warehouse'].queryset
        assert other_warehouse not in form.fields['warehouse'].queryset

    def test_expected_return_date_before_requested_rejected(self, tenant, delivered_so, warehouse):
        data = _rma_form_data(delivered_so, warehouse)
        data['expected_return_date'] = '2026-04-17'  # before requested_date
        form = ReturnAuthorizationForm(data=data, tenant=tenant)
        assert not form.is_valid()
        assert 'expected_return_date' in form.errors


class TestReturnAuthorizationItemFormSet:
    def test_formset_scopes_product_queryset_to_tenant(self, tenant, product, other_product):
        """D-05: on POST-time validation, product queryset must be tenant-filtered."""
        fs = ReturnAuthorizationItemFormSet(prefix='items', form_kwargs={'tenant': tenant})
        qs = fs.forms[0].fields['product'].queryset
        assert product in qs
        assert other_product not in qs

    def test_formset_rejects_cross_tenant_product_on_post(
        self, tenant, delivered_so, warehouse, product, other_product,
    ):
        """D-05 regression: POSTing a foreign tenant's product pk must fail validation."""
        data = _item_formset_data(product)
        data['items-0-product'] = other_product.pk  # cross-tenant!
        fs = ReturnAuthorizationItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_qty_requested_zero_rejected(self, tenant, product):
        data = _item_formset_data(product, qty=0)
        fs = ReturnAuthorizationItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_unit_price_negative_rejected(self, tenant, product):
        data = _item_formset_data(product, price='-1')
        fs = ReturnAuthorizationItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()
