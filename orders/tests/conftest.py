from datetime import date

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse, Zone, Aisle, Rack, Bin
from orders.models import Carrier, SalesOrder, SalesOrderItem, PickList


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Orders', slug='t-orders')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other', slug='t-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_orders', password='x', tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_orders', password='x', tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other', password='x', tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main', address='', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other-Main', address='', is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Cat', slug='cat')


@pytest.fixture
def other_category(db, other_tenant):
    return Category.objects.create(tenant=other_tenant, name='OCat', slug='ocat')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku='P1', name='Prod 1', status='active',
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
def draft_so(db, tenant, warehouse, tenant_admin):
    so = SalesOrder(
        tenant=tenant, customer_name='Alice',
        order_date=date(2026, 4, 18), warehouse=warehouse,
        created_by=tenant_admin,
    )
    so.save()
    return so


@pytest.fixture
def draft_so_with_item(db, draft_so, product):
    SalesOrderItem.objects.create(
        tenant=draft_so.tenant, sales_order=draft_so, product=product,
        quantity=2, unit_price=10,
    )
    return draft_so


@pytest.fixture
def picklist_pending(db, tenant, warehouse, tenant_admin):
    return PickList.objects.create(
        tenant=tenant, warehouse=warehouse, created_by=tenant_admin,
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
