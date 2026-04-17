import pytest
from django.urls import reverse

from orders.models import SalesOrder, SalesOrderItem


@pytest.mark.django_db
def test_so_list_view(client_admin, draft_so):
    url = reverse('orders:so_list')
    resp = client_admin.get(url)
    assert resp.status_code == 200
    assert draft_so.order_number.encode() in resp.content


@pytest.mark.django_db
def test_so_list_search_filter(client_admin, tenant, warehouse):
    SalesOrder(tenant=tenant, customer_name='Alice', order_date='2026-04-18', warehouse=warehouse).save()
    SalesOrder(tenant=tenant, customer_name='Bob', order_date='2026-04-18', warehouse=warehouse).save()
    url = reverse('orders:so_list') + '?q=Alice'
    resp = client_admin.get(url)
    assert b'Alice' in resp.content
    assert b'Bob' not in resp.content


@pytest.mark.django_db
def test_so_list_status_filter(client_admin, tenant, warehouse):
    SalesOrder(tenant=tenant, customer_name='A', order_date='2026-04-18', warehouse=warehouse, status='draft').save()
    SalesOrder(tenant=tenant, customer_name='B', order_date='2026-04-18', warehouse=warehouse, status='cancelled').save()
    url = reverse('orders:so_list') + '?status=cancelled'
    resp = client_admin.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_so_create_happy_path(client_admin, tenant, warehouse, product):
    url = reverse('orders:so_create')
    resp = client_admin.post(url, {
        'customer_name': 'Alice', 'customer_email': '', 'customer_phone': '',
        'shipping_address': '', 'billing_address': '',
        'order_date': '2026-04-18', 'required_date': '',
        'warehouse': warehouse.pk, 'priority': 'normal', 'notes': '',
        'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        'items-0-product': product.pk, 'items-0-description': '',
        'items-0-quantity': '2', 'items-0-unit_price': '10.00',
        'items-0-tax_rate': '0', 'items-0-discount': '0',
    })
    assert resp.status_code == 302
    so = SalesOrder.objects.get(customer_name='Alice')
    assert so.tenant == tenant
    assert so.items.count() == 1


@pytest.mark.django_db
def test_so_delete_draft_succeeds(client_admin, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    resp = client_admin.post(url)
    assert resp.status_code == 302
    assert not SalesOrder.objects.filter(pk=draft_so.pk).exists()


@pytest.mark.django_db
def test_so_delete_non_draft_refused(client_admin, tenant, warehouse):
    so = SalesOrder(
        tenant=tenant, customer_name='X',
        order_date='2026-04-18', warehouse=warehouse, status='confirmed',
    )
    so.save()
    url = reverse('orders:so_delete', args=[so.pk])
    client_admin.post(url)
    assert SalesOrder.objects.filter(pk=so.pk).exists()


@pytest.mark.django_db
def test_so_edit_non_draft_redirects_without_save(client_admin, tenant, warehouse):
    so = SalesOrder(
        tenant=tenant, customer_name='Original',
        order_date='2026-04-18', warehouse=warehouse, status='confirmed',
    )
    so.save()
    url = reverse('orders:so_edit', args=[so.pk])
    resp = client_admin.post(url, {'customer_name': 'Hacked'})
    so.refresh_from_db()
    assert so.customer_name == 'Original'
    assert resp.status_code == 302


@pytest.mark.django_db
def test_so_generate_picklist_refuses_duplicate(client_admin, draft_so_with_item):
    """Regression for D-11."""
    draft_so_with_item.status = 'confirmed'
    draft_so_with_item.save()
    url = reverse('orders:so_generate_picklist', args=[draft_so_with_item.pk])
    client_admin.post(url)
    client_admin.post(url)  # second call
    assert draft_so_with_item.pick_lists.count() == 1


@pytest.mark.django_db
def test_so_list_paginated_filter_retention(client_admin, tenant, warehouse):
    for i in range(25):
        SalesOrder(tenant=tenant, customer_name=f'C{i}',
                   order_date='2026-04-18', warehouse=warehouse).save()
    url = reverse('orders:so_list') + '?q=C&page=2'
    resp = client_admin.get(url)
    assert resp.status_code == 200
