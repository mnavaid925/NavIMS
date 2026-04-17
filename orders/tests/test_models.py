from decimal import Decimal

import pytest

from orders.models import SalesOrder, SalesOrderItem, PickList, PackingList, Shipment


@pytest.mark.django_db
def test_order_number_auto_generated(draft_so):
    assert draft_so.order_number.startswith('SO-')
    assert len(draft_so.order_number) == 8


@pytest.mark.django_db
def test_order_numbers_increment_within_tenant(tenant, warehouse):
    so1 = SalesOrder(tenant=tenant, customer_name='A',
                     order_date='2026-04-18', warehouse=warehouse)
    so1.save()
    so2 = SalesOrder(tenant=tenant, customer_name='B',
                     order_date='2026-04-18', warehouse=warehouse)
    so2.save()
    n1 = int(so1.order_number.split('-')[1])
    n2 = int(so2.order_number.split('-')[1])
    assert n2 == n1 + 1


@pytest.mark.django_db
def test_order_number_sequence_isolated_per_tenant(
    tenant, warehouse, other_tenant, other_warehouse,
):
    SalesOrder(tenant=tenant, customer_name='A',
               order_date='2026-04-18', warehouse=warehouse).save()
    so_other = SalesOrder(tenant=other_tenant, customer_name='B',
                          order_date='2026-04-18', warehouse=other_warehouse)
    so_other.save()
    # Each tenant starts from 1 independently
    assert so_other.order_number == 'SO-00001'


@pytest.mark.django_db
def test_grand_total_combines_subtotal_tax_discount(draft_so, product):
    SalesOrderItem.objects.create(
        tenant=draft_so.tenant, sales_order=draft_so, product=product,
        quantity=2, unit_price=Decimal('10.00'),
        tax_rate=Decimal('10.00'), discount=Decimal('1.00'),
    )
    draft_so.refresh_from_db()
    assert draft_so.subtotal == Decimal('20.00')
    assert draft_so.discount_total == Decimal('2.00')
    assert draft_so.tax_total == Decimal('1.80')
    assert draft_so.grand_total == Decimal('19.80')


@pytest.mark.django_db
@pytest.mark.parametrize('from_status,to_status,expected', [
    ('draft', 'confirmed', True),
    ('draft', 'shipped', False),
    ('packed', 'shipped', True),
    ('picked', 'shipped', False),
    ('in_fulfillment', 'shipped', False),
    ('shipped', 'draft', False),
    ('cancelled', 'draft', True),
    ('delivered', 'closed', True),
    ('closed', 'draft', False),
    ('on_hold', 'shipped', False),
    ('on_hold', 'confirmed', True),
])
def test_sales_order_state_machine(from_status, to_status, expected):
    so = SalesOrder(status=from_status)
    assert so.can_transition_to(to_status) is expected


@pytest.mark.django_db
def test_picklist_number_auto(picklist_pending):
    assert picklist_pending.pick_number.startswith('PK-')


@pytest.mark.django_db
def test_packinglist_number_auto(tenant, picklist_pending, draft_so):
    pl = PackingList.objects.create(
        tenant=tenant, pick_list=picklist_pending, sales_order=draft_so,
    )
    assert pl.packing_number.startswith('PL-')


@pytest.mark.django_db
def test_shipment_number_auto(tenant, draft_so):
    sh = Shipment.objects.create(tenant=tenant, sales_order=draft_so)
    assert sh.shipment_number.startswith('SH-')
