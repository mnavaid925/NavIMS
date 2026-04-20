"""Integration tests for Scrap Write-Off views — approval workflow,
SoD, posting (atomic StockAdjustment), reject branches.

D-01 threaded race regression lives in test_regression.py to keep suite
execution monotonic when transactional_db tests run.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from quality_control.models import ScrapWriteOff
from inventory.models import StockAdjustment


@pytest.mark.django_db
def test_scrap_list_renders(client_admin):
    r = client_admin.get(reverse('quality_control:scrap_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_scrap_create(client_admin, tenant, product, warehouse):
    r = client_admin.post(
        reverse('quality_control:scrap_create'),
        data={'product': product.pk, 'warehouse': warehouse.pk,
              'quantity': 2, 'unit_cost': '5.00', 'reason': 'damage'},
    )
    assert r.status_code == 302
    s = ScrapWriteOff.objects.get(tenant=tenant, reason='damage')
    assert s.approval_status == 'pending'
    assert s.total_value == Decimal('10.00')


@pytest.mark.django_db
def test_scrap_self_approval_forbidden(client_admin, tenant, product, warehouse, tenant_admin):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='self',
        requested_by=tenant_admin,
    )
    r = client_admin.post(reverse('quality_control:scrap_approve', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.approval_status == 'pending'


@pytest.mark.django_db
def test_scrap_approval_by_different_admin(client, tenant, tenant_admin, tenant_admin_two, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='two-step',
        requested_by=tenant_admin,
    )
    client.force_login(tenant_admin_two)
    r = client.post(reverse('quality_control:scrap_approve', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.approval_status == 'approved'
    assert s.approved_by == tenant_admin_two


@pytest.mark.django_db
def test_scrap_post_decrements_stock_and_writes_adjustment(client_admin, tenant, product, warehouse, stock_level, tenant_admin):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=4, unit_cost=Decimal('2.50'), reason='test-post',
        approval_status='approved', requested_by=tenant_admin,
        approved_by=tenant_admin,
    )
    r = client_admin.post(reverse('quality_control:scrap_post', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    stock_level.refresh_from_db()
    assert s.approval_status == 'posted'
    assert stock_level.on_hand == 96  # 100 - 4
    assert s.stock_adjustment is not None
    assert s.stock_adjustment.adjustment_type == 'decrease'
    assert s.stock_adjustment.reason == 'damage'
    assert s.stock_adjustment.quantity == 4


@pytest.mark.django_db
def test_scrap_post_insufficient_stock_rolls_back(client_admin, tenant, product, warehouse, stock_level, tenant_admin):
    stock_level.on_hand = 2; stock_level.save()
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=5, unit_cost=Decimal('1.00'), reason='overflow',
        approval_status='approved', requested_by=tenant_admin,
    )
    r = client_admin.post(reverse('quality_control:scrap_post', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    stock_level.refresh_from_db()
    assert s.approval_status == 'approved'      # unchanged
    assert stock_level.on_hand == 2             # unchanged
    assert StockAdjustment.objects.filter(stock_level=stock_level).count() == 0


@pytest.mark.django_db
def test_scrap_reject_from_approved(client, tenant, tenant_admin, tenant_admin_two, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='x',
        approval_status='approved', requested_by=tenant_admin,
    )
    client.force_login(tenant_admin_two)
    r = client.post(reverse('quality_control:scrap_reject', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.approval_status == 'rejected'


@pytest.mark.django_db
def test_scrap_post_from_rejected_refused(client_admin, tenant, tenant_admin, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='x',
        approval_status='rejected', requested_by=tenant_admin,
    )
    r = client_admin.post(reverse('quality_control:scrap_post', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.approval_status == 'rejected'
    assert s.stock_adjustment is None


@pytest.mark.django_db
def test_scrap_delete_while_posted_rejected(client_admin, tenant, tenant_admin, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='x',
        approval_status='posted', requested_by=tenant_admin,
    )
    r = client_admin.post(reverse('quality_control:scrap_delete', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.deleted_at is None


@pytest.mark.django_db
def test_scrap_cross_tenant_post_404(client_other, approved_scrap):
    r = client_other.post(reverse('quality_control:scrap_post', args=[approved_scrap.pk]))
    assert r.status_code == 404
    approved_scrap.refresh_from_db()
    assert approved_scrap.approval_status == 'approved'
