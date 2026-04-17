from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse, Zone, Aisle, Rack, Bin
from orders.models import SalesOrder, SalesOrderItem
from returns.models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Returns', slug='t-returns')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other-R', slug='t-other-r')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_r', password='x', tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_r', password='x', tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other_r', password='x', tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main', address='', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other', address='', is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Cat', slug='cat')


@pytest.fixture
def other_category(db, other_tenant):
    return Category.objects.create(tenant=other_tenant, name='OC', slug='oc')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku='P1', name='Prod 1',
        status='active', retail_price=Decimal('10.00'),
    )


@pytest.fixture
def other_product(db, other_tenant, other_category):
    return Product.objects.create(
        tenant=other_tenant, category=other_category, sku='OP1',
        name='Other Prod', status='active',
    )


@pytest.fixture
def bin_location(db, tenant, warehouse):
    z = Zone.objects.create(tenant=tenant, warehouse=warehouse, code='Z1', name='Z1')
    a = Aisle.objects.create(tenant=tenant, zone=z, code='A1', name='A1')
    r = Rack.objects.create(tenant=tenant, aisle=a, code='R1', name='R1')
    return Bin.objects.create(
        tenant=tenant, zone=z, rack=r, code='B1', name='B1', is_active=True,
    )


@pytest.fixture
def other_bin(db, other_tenant, other_warehouse):
    z = Zone.objects.create(tenant=other_tenant, warehouse=other_warehouse, code='Z1', name='Z1')
    a = Aisle.objects.create(tenant=other_tenant, zone=z, code='A1', name='A1')
    r = Rack.objects.create(tenant=other_tenant, aisle=a, code='R1', name='R1')
    return Bin.objects.create(
        tenant=other_tenant, zone=z, rack=r, code='B1', name='B1', is_active=True,
    )


@pytest.fixture
def delivered_so(db, tenant, warehouse, tenant_admin, product):
    so = SalesOrder.objects.create(
        tenant=tenant, customer_name='Alice', order_date=date(2026, 4, 18),
        warehouse=warehouse, created_by=tenant_admin, status='delivered',
    )
    SalesOrderItem.objects.create(
        tenant=tenant, sales_order=so, product=product,
        quantity=5, unit_price=Decimal('10.00'),
    )
    return so


@pytest.fixture
def other_delivered_so(db, other_tenant, other_warehouse, other_tenant_admin, other_product):
    so = SalesOrder.objects.create(
        tenant=other_tenant, customer_name='Bob', order_date=date(2026, 4, 18),
        warehouse=other_warehouse, created_by=other_tenant_admin, status='delivered',
    )
    SalesOrderItem.objects.create(
        tenant=other_tenant, sales_order=so, product=other_product,
        quantity=3, unit_price=Decimal('5.00'),
    )
    return so


@pytest.fixture
def draft_rma(db, tenant, delivered_so, warehouse, tenant_admin, product):
    rma = ReturnAuthorization.objects.create(
        tenant=tenant, sales_order=delivered_so, customer_name='Alice',
        reason='defective', requested_date=date(2026, 4, 18),
        warehouse=warehouse, created_by=tenant_admin,
    )
    ReturnAuthorizationItem.objects.create(
        tenant=tenant, rma=rma, product=product,
        qty_requested=2, qty_received=0, unit_price=Decimal('10.00'),
    )
    return rma


@pytest.fixture
def pending_rma(db, draft_rma):
    draft_rma.status = 'pending'
    draft_rma.save()
    return draft_rma


@pytest.fixture
def approved_rma(db, draft_rma):
    draft_rma.status = 'approved'
    draft_rma.save()
    return draft_rma


@pytest.fixture
def received_rma(db, draft_rma):
    draft_rma.status = 'received'
    for i in draft_rma.items.all():
        i.qty_received = i.qty_requested
        i.save()
    draft_rma.save()
    return draft_rma


@pytest.fixture
def other_draft_rma(db, other_tenant, other_delivered_so, other_warehouse,
                    other_tenant_admin, other_product):
    rma = ReturnAuthorization.objects.create(
        tenant=other_tenant, sales_order=other_delivered_so, customer_name='Bob',
        reason='other', requested_date=date(2026, 4, 18),
        warehouse=other_warehouse, created_by=other_tenant_admin,
    )
    ReturnAuthorizationItem.objects.create(
        tenant=other_tenant, rma=rma, product=other_product,
        qty_requested=1, unit_price=Decimal('5.00'),
    )
    return rma


@pytest.fixture
def inspection_in_progress(db, tenant, approved_rma, tenant_admin):
    insp = ReturnInspection.objects.create(
        tenant=tenant, rma=approved_rma,
        status='in_progress', inspector=tenant_admin,
    )
    return insp


@pytest.fixture
def inspection_completed(db, tenant, received_rma, tenant_admin):
    insp = ReturnInspection.objects.create(
        tenant=tenant, rma=received_rma,
        status='completed', overall_result='pass',
        inspector=tenant_admin,
        inspected_date=date(2026, 4, 18),
    )
    rma_item = received_rma.items.first()
    ReturnInspectionItem.objects.create(
        tenant=tenant, inspection=insp, rma_item=rma_item,
        qty_inspected=2, qty_passed=2, qty_failed=0,
        condition='good', restockable=True,
    )
    return insp


@pytest.fixture
def disposition_pending_restock(db, tenant, received_rma, inspection_completed, warehouse):
    disp = Disposition.objects.create(
        tenant=tenant, rma=received_rma, inspection=inspection_completed,
        decision='restock', warehouse=warehouse, status='pending',
    )
    ins_item = inspection_completed.items.first()
    DispositionItem.objects.create(
        tenant=tenant, disposition=disp, inspection_item=ins_item,
        product=ins_item.rma_item.product, qty=2,
    )
    return disp


@pytest.fixture
def pending_refund(db, tenant, received_rma):
    return RefundCredit.objects.create(
        tenant=tenant, rma=received_rma, type='refund', method='card',
        amount=Decimal('10.00'), currency='USD', status='pending',
    )


@pytest.fixture
def client_admin(tenant_admin):
    c = Client()
    c.force_login(tenant_admin)
    return c


@pytest.fixture
def client_user(tenant_user):
    c = Client()
    c.force_login(tenant_user)
    return c


@pytest.fixture
def client_other(other_tenant_admin):
    c = Client()
    c.force_login(other_tenant_admin)
    return c
