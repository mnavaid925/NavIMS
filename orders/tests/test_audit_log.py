"""Regression for D-05 — destructive + state-transition ops emit AuditLog."""
import pytest
from django.urls import reverse

from core.models import AuditLog
from orders.models import Carrier, Shipment


@pytest.mark.django_db
def test_so_delete_writes_audit_row(client_admin, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    client_admin.post(url)
    assert AuditLog.objects.filter(
        tenant=draft_so.tenant, model_name='SalesOrder', action='delete',
    ).exists()


@pytest.mark.django_db
def test_so_cancel_writes_audit_row(client_admin, tenant, warehouse, product):
    from orders.models import SalesOrder, SalesOrderItem
    so = SalesOrder(
        tenant=tenant, customer_name='X',
        order_date='2026-04-18', warehouse=warehouse, status='confirmed',
    )
    so.save()
    SalesOrderItem.objects.create(
        tenant=tenant, sales_order=so, product=product, quantity=1, unit_price=1,
    )
    url = reverse('orders:so_cancel', args=[so.pk])
    client_admin.post(url)
    assert AuditLog.objects.filter(
        tenant=tenant, model_name='SalesOrder', action='cancel',
    ).exists()


@pytest.mark.django_db
def test_carrier_create_writes_audit(client_admin, tenant):
    url = reverse('orders:carrier_create')
    resp = client_admin.post(url, {
        'name': 'FedEx', 'code': 'FEDEX',
        'contact_email': '', 'contact_phone': '',
        'api_endpoint': '', 'api_key': '', 'notes': '',
    })
    assert resp.status_code == 302
    assert AuditLog.objects.filter(
        tenant=tenant, model_name='Carrier', action='create',
    ).exists()


@pytest.mark.django_db
def test_carrier_delete_writes_audit(client_admin, tenant):
    c = Carrier.objects.create(tenant=tenant, name='X', code='X')
    url = reverse('orders:carrier_delete', args=[c.pk])
    client_admin.post(url)
    assert AuditLog.objects.filter(
        tenant=tenant, model_name='Carrier', action='delete',
    ).exists()


@pytest.mark.django_db
def test_shipment_cancel_writes_audit(client_admin, tenant, draft_so):
    sh = Shipment.objects.create(tenant=tenant, sales_order=draft_so, status='pending')
    url = reverse('orders:shipment_cancel', args=[sh.pk])
    client_admin.post(url)
    assert AuditLog.objects.filter(
        tenant=tenant, model_name='Shipment', action='cancel',
    ).exists()
