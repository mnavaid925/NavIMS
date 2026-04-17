"""Regression for D-08, D-09 — state-transition views honour VALID_TRANSITIONS."""
import pytest
from django.urls import reverse

from orders.models import SalesOrder, Shipment, PickList


@pytest.mark.django_db
def test_shipment_dispatch_refuses_from_in_fulfillment(
    client_admin, tenant, warehouse,
):
    """Regression for D-08: in_fulfillment -> shipped is invalid."""
    so = SalesOrder(
        tenant=tenant, customer_name='X',
        order_date='2026-04-18', warehouse=warehouse, status='in_fulfillment',
    )
    so.save()
    sh = Shipment.objects.create(tenant=tenant, sales_order=so, status='pending')
    url = reverse('orders:shipment_dispatch', args=[sh.pk])
    client_admin.post(url)
    so.refresh_from_db()
    sh.refresh_from_db()
    assert so.status != 'shipped'
    # Dispatch should have been refused on the SO state guard
    assert sh.status == 'pending'


@pytest.mark.django_db
def test_shipment_dispatch_allowed_from_packed(client_admin, tenant, warehouse):
    so = SalesOrder(
        tenant=tenant, customer_name='X',
        order_date='2026-04-18', warehouse=warehouse, status='packed',
    )
    so.save()
    sh = Shipment.objects.create(tenant=tenant, sales_order=so, status='pending')
    url = reverse('orders:shipment_dispatch', args=[sh.pk])
    client_admin.post(url)
    so.refresh_from_db()
    sh.refresh_from_db()
    assert sh.status == 'dispatched'
    assert so.status == 'shipped'


@pytest.mark.django_db
def test_so_resume_clamps_to_valid_transition(
    client_admin, tenant, warehouse,
):
    """Regression for D-09: resume target must be in VALID_TRANSITIONS['on_hold']."""
    so = SalesOrder(
        tenant=tenant, customer_name='X',
        order_date='2026-04-18', warehouse=warehouse, status='on_hold',
    )
    so.save()
    # Simulate a fully-fulfilled trail that would have mapped to 'shipped' in
    # the old logic: create a completed PickList + PackingList (no dispatched
    # shipment needed now since we removed that branch).
    pl = PickList.objects.create(
        tenant=tenant, sales_order=so, warehouse=warehouse, status='completed',
    )
    from orders.models import PackingList
    PackingList.objects.create(
        tenant=tenant, sales_order=so, pick_list=pl, status='completed',
    )
    url = reverse('orders:so_resume', args=[so.pk])
    client_admin.post(url)
    so.refresh_from_db()
    # The valid target from 'on_hold' with completed packing is 'packed'.
    assert so.status == 'packed'


@pytest.mark.django_db
def test_so_cancel_forbidden_from_delivered(client_admin, tenant, warehouse):
    so = SalesOrder(
        tenant=tenant, customer_name='X',
        order_date='2026-04-18', warehouse=warehouse, status='delivered',
    )
    so.save()
    url = reverse('orders:so_cancel', args=[so.pk])
    client_admin.post(url)
    so.refresh_from_db()
    assert so.status == 'delivered'
