"""Variance adjustment critical path — create, approve, reject, post.

Regression guards for D-01 (CSRF), D-02 (atomic), D-03 (double-post),
D-09 (AuditLog), plus IDOR.
"""
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from core.models import AuditLog
from inventory.models import StockLevel, StockAdjustment
from stocktaking.models import (
    StockCount, StockCountItem, StockVarianceAdjustment,
)


@pytest.mark.django_db
class TestAdjustmentCreate:
    def test_create_computes_totals(
        self, client_admin, tenant, counted_count,
    ):
        """counted_count deltas are [-2, 0, +3, 0, -1, 0] unit_cost=10 → net 0, |value| varies."""
        r = client_admin.post(reverse('stocktaking:adjustment_create'), {
            'count': counted_count.pk,
            'reason_code': 'miscount',
            'notes': 'test',
        })
        assert r.status_code == 302
        adj = StockVarianceAdjustment.objects.get(tenant=tenant, count=counted_count)
        # net qty variance = (-2) + 3 + (-1) = 0
        assert adj.total_variance_qty == 0
        # net value variance = 0 × 10 = 0 (signed sum), but each has variance
        assert adj.total_variance_value == Decimal('0.00')
        assert adj.reason_code == 'miscount'
        assert adj.status == 'pending'


@pytest.mark.django_db
class TestAdjustmentApproveReject:
    def test_approve_requires_post(self, client_admin, pending_adj):
        """D-01 regression — approve must reject GET."""
        url = reverse('stocktaking:adjustment_approve', args=[pending_adj.pk])
        r = client_admin.get(url)
        assert r.status_code == 405
        pending_adj.refresh_from_db()
        assert pending_adj.status == 'pending'

    def test_approve_via_post(self, client_admin, pending_adj):
        url = reverse('stocktaking:adjustment_approve', args=[pending_adj.pk])
        r = client_admin.post(url)
        assert r.status_code == 302
        pending_adj.refresh_from_db()
        assert pending_adj.status == 'approved'
        assert pending_adj.approved_by is not None
        assert pending_adj.approved_at is not None

    def test_reject_requires_post(self, client_admin, pending_adj):
        url = reverse('stocktaking:adjustment_reject', args=[pending_adj.pk])
        r = client_admin.get(url)
        assert r.status_code == 405

    def test_reject_via_post(self, client_admin, pending_adj):
        url = reverse('stocktaking:adjustment_reject', args=[pending_adj.pk])
        r = client_admin.post(url)
        assert r.status_code == 302
        pending_adj.refresh_from_db()
        assert pending_adj.status == 'rejected'


@pytest.mark.django_db
class TestAdjustmentPost:
    def test_post_requires_post(self, client_admin, approved_adj):
        """D-01 regression — post via GET must be rejected. Any authenticated
        user visiting `<img src="/stocktaking/adjustments/<pk>/post/">` would
        otherwise mutate stock."""
        url = reverse('stocktaking:adjustment_post', args=[approved_adj.pk])
        r = client_admin.get(url)
        assert r.status_code == 405
        approved_adj.refresh_from_db()
        assert approved_adj.status == 'approved'

    def test_post_updates_stock_and_flips_status(
        self, client_admin, tenant, counted_count, approved_adj, stock_levels,
    ):
        """Critical happy path — post mutates StockLevel and emits audit rows."""
        url = reverse('stocktaking:adjustment_post', args=[approved_adj.pk])
        r = client_admin.post(url)
        assert r.status_code == 302

        approved_adj.refresh_from_db()
        counted_count.refresh_from_db()
        assert approved_adj.status == 'posted'
        assert counted_count.status == 'adjusted'
        assert approved_adj.posted_by is not None
        assert approved_adj.posted_at is not None
        assert counted_count.adjusted_at is not None

        # Item 0 delta=-2 ⇒ on_hand 98
        stock_levels[0].refresh_from_db()
        assert stock_levels[0].on_hand == 98
        # Item 2 delta=+3 ⇒ on_hand 103
        stock_levels[2].refresh_from_db()
        assert stock_levels[2].on_hand == 103
        # Item 4 delta=-1 ⇒ on_hand 99
        stock_levels[4].refresh_from_db()
        assert stock_levels[4].on_hand == 99
        # Non-variance items untouched
        stock_levels[1].refresh_from_db()
        assert stock_levels[1].on_hand == 100

        # StockAdjustment rows: one per variance item (3)
        assert StockAdjustment.objects.filter(tenant=tenant).count() == 3

    def test_D06_uses_correction_adjustment_type(
        self, client_admin, tenant, counted_count, approved_adj, stock_levels,
    ):
        """D-06 regression — ledger rows must use the canonical
        `apply_adjustment()` write path via adjustment_type='correction'
        with quantity=counted_qty. Ensures ledger.quantity and resulting
        on_hand are arithmetically reconcilable (both equal counted_qty)."""
        url = reverse('stocktaking:adjustment_post', args=[approved_adj.pk])
        client_admin.post(url)
        rows = StockAdjustment.objects.filter(tenant=tenant).order_by('stock_level__product__sku')
        for row in rows:
            assert row.adjustment_type == 'correction', (
                'D-06 regression: posting must use correction-type adjustments, '
                'not increase/decrease — otherwise ledger drifts from on_hand.'
            )
            # quantity in the ledger equals the final on_hand of that product.
            assert row.quantity == row.stock_level.on_hand

    def test_post_blocked_when_pending(self, client_admin, pending_adj):
        url = reverse('stocktaking:adjustment_post', args=[pending_adj.pk])
        r = client_admin.post(url)
        assert r.status_code == 302
        pending_adj.refresh_from_db()
        assert pending_adj.status == 'pending'

    def test_D03_double_post_blocked(
        self, client_admin, tenant, counted_count, stock_levels,
    ):
        """D-03 regression — two approved adjustments on the same count
        must NOT both post. Second one must be rejected after first flips
        the count to status=adjusted."""
        adj1 = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        adj2 = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        client_admin.post(reverse('stocktaking:adjustment_post', args=[adj1.pk]))
        r2 = client_admin.post(
            reverse('stocktaking:adjustment_post', args=[adj2.pk]),
        )

        adj1.refresh_from_db()
        adj2.refresh_from_db()
        assert adj1.status == 'posted'
        assert adj2.status != 'posted', (
            'D-03 regression: same count was adjusted twice — '
            'StockLevel would be overwritten and audit ledger inflated.'
        )
        msgs = [str(m) for m in get_messages(r2.wsgi_request)]
        assert any('already been adjusted' in m for m in msgs)

        # StockAdjustment ledger must show exactly one set of rows (from adj1).
        assert StockAdjustment.objects.filter(tenant=tenant).count() == 3

    def test_D02_atomic_rollback_on_failure(
        self, client_admin, tenant, counted_count, approved_adj, stock_levels,
    ):
        """D-02 regression — if any StockAdjustment.save() raises mid-loop,
        the whole transaction must roll back and StockLevel.on_hand must be
        untouched."""
        url = reverse('stocktaking:adjustment_post', args=[approved_adj.pk])
        with mock.patch(
            'stocktaking.views.StockAdjustment.objects.create',
            side_effect=[
                # First variance item succeeds (mock returns dummy), then raise
                # on the second variance call to simulate mid-loop failure.
                mock.MagicMock(),
                RuntimeError('simulated DB failure'),
            ],
        ):
            with pytest.raises(RuntimeError):
                client_admin.post(url)

        # Nothing committed: adj still approved, count still counted,
        # stock untouched.
        approved_adj.refresh_from_db()
        counted_count.refresh_from_db()
        assert approved_adj.status == 'approved'
        assert counted_count.status == 'counted'
        for sl in stock_levels:
            sl.refresh_from_db()
            assert sl.on_hand == 100, 'D-02 regression — StockLevel partially mutated'
        assert StockAdjustment.objects.filter(tenant=tenant).count() == 0

    def test_D09_audit_log_emitted(
        self, client_admin, tenant, approved_adj,
    ):
        """D-09 regression — posting must emit a `core.AuditLog` row."""
        url = reverse('stocktaking:adjustment_post', args=[approved_adj.pk])
        client_admin.post(url)
        logs = AuditLog.objects.filter(
            tenant=tenant, action='post',
            model_name='StockVarianceAdjustment',
            object_id=str(approved_adj.pk),
        )
        assert logs.exists(), 'D-09 regression: no AuditLog emitted for post'

    def test_idor_cross_tenant(self, client_other, approved_adj):
        url = reverse('stocktaking:adjustment_post', args=[approved_adj.pk])
        r = client_other.post(url)
        assert r.status_code == 404


@pytest.mark.django_db
class TestAdjustmentDeleteEdit:
    def test_cannot_edit_posted(
        self, client_admin, tenant, counted_count, stock_levels,
    ):
        adj = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        client_admin.post(reverse('stocktaking:adjustment_post', args=[adj.pk]))
        r = client_admin.get(reverse('stocktaking:adjustment_edit', args=[adj.pk]))
        assert r.status_code == 302
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        assert any('Cannot edit a posted adjustment' in m for m in msgs)

    def test_cannot_delete_posted(
        self, client_admin, tenant, counted_count, stock_levels,
    ):
        adj = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        client_admin.post(reverse('stocktaking:adjustment_post', args=[adj.pk]))
        r = client_admin.post(reverse('stocktaking:adjustment_delete', args=[adj.pk]))
        adj.refresh_from_db()
        assert adj.status == 'posted'
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        assert any('Cannot delete a posted adjustment' in m for m in msgs)
