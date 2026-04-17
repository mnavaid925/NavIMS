import pytest

from orders.forms import SalesOrderForm, SalesOrderItemFormSet


def _so_data(warehouse, **overrides):
    data = {
        'customer_name': 'Alice', 'customer_email': '', 'customer_phone': '',
        'shipping_address': '', 'billing_address': '',
        'order_date': '2026-04-18',
        'required_date': '',
        'warehouse': warehouse.pk,
        'priority': 'normal', 'notes': '',
    }
    data.update(overrides)
    return data


def _formset_data(**items):
    data = {
        'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
    }
    defaults = {
        'description': '', 'quantity': '1', 'unit_price': '10.00',
        'tax_rate': '0', 'discount': '0',
    }
    for k, v in {**defaults, **items}.items():
        data[f'items-0-{k}'] = str(v)
    return data


@pytest.mark.django_db
def test_so_form_valid(tenant, warehouse):
    form = SalesOrderForm(data=_so_data(warehouse), tenant=tenant)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_required_date_before_order_date_rejected(tenant, warehouse):
    """Regression for D-04a."""
    form = SalesOrderForm(
        data=_so_data(warehouse, order_date='2026-05-01', required_date='2025-01-01'),
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'required_date' in form.errors


@pytest.mark.django_db
def test_required_date_equal_order_date_allowed(tenant, warehouse):
    form = SalesOrderForm(
        data=_so_data(warehouse, order_date='2026-05-01', required_date='2026-05-01'),
        tenant=tenant,
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
@pytest.mark.parametrize('qty,price,passes', [
    (1, '10.00', True),
    (0, '10.00', False),   # D-04b
    (-1, '10.00', False),
    (1, '0.00', True),
    (1, '-5.00', False),   # D-04c
])
def test_line_item_quantity_price_validation(
    tenant, draft_so, product, qty, price, passes,
):
    data = _formset_data(product=product.pk, quantity=qty, unit_price=price)
    fs = SalesOrderItemFormSet(
        data, instance=draft_so, prefix='items', form_kwargs={'tenant': tenant},
    )
    assert fs.is_valid() is passes


@pytest.mark.django_db
def test_line_item_tax_rate_over_100_rejected(tenant, draft_so, product):
    data = _formset_data(product=product.pk, tax_rate='150')
    fs = SalesOrderItemFormSet(
        data, instance=draft_so, prefix='items', form_kwargs={'tenant': tenant},
    )
    assert not fs.is_valid()


@pytest.mark.django_db
def test_item_formset_rejects_cross_tenant_product(
    tenant, draft_so, other_product,
):
    """Regression for D-02 — cross-tenant IDOR via inline formset."""
    data = _formset_data(product=other_product.pk)
    fs = SalesOrderItemFormSet(
        data, instance=draft_so, prefix='items', form_kwargs={'tenant': tenant},
    )
    assert not fs.is_valid()


@pytest.mark.django_db
def test_item_formset_accepts_own_tenant_product(tenant, draft_so, product):
    data = _formset_data(product=product.pk)
    fs = SalesOrderItemFormSet(
        data, instance=draft_so, prefix='items', form_kwargs={'tenant': tenant},
    )
    assert fs.is_valid(), fs.errors
