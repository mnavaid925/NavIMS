from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone

from inventory.models import (
    StockLevel, StockAdjustment, StockStatus, StockStatusTransition,
    InventoryReservation,
)


@pytest.mark.django_db
class TestStockLevelProperties:
    def test_available_caps_at_zero(self, stock_level):
        stock_level.on_hand = 5
        stock_level.allocated = 10
        assert stock_level.available == 0

    def test_available_is_on_hand_minus_allocated(self, stock_level):
        stock_level.on_hand = 20
        stock_level.allocated = 5
        assert stock_level.available == 15

    def test_needs_reorder_respects_reorder_point(self, stock_level):
        stock_level.on_hand = 5
        stock_level.allocated = 0
        stock_level.reorder_point = 10
        assert stock_level.needs_reorder is True

    def test_needs_reorder_disabled_when_point_is_zero(self, stock_level):
        stock_level.on_hand = 0
        stock_level.reorder_point = 0
        assert stock_level.needs_reorder is False


@pytest.mark.django_db
class TestApplyAdjustment:
    def test_increase(self, tenant, stock_level):
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='increase', quantity=10, reason='return',
        )
        adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 60

    def test_decrease_within_bounds(self, tenant, stock_level):
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='decrease', quantity=10, reason='damage',
        )
        adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 40

    def test_decrease_over_bounds_raises(self, tenant, stock_level):
        """Regression for D-01 — no silent clamp to 0."""
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='decrease', quantity=9999, reason='theft',
        )
        with pytest.raises(ValueError):
            adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 50  # unchanged

    def test_correction(self, tenant, stock_level):
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='correction', quantity=23, reason='count',
        )
        adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 23


@pytest.mark.django_db
class TestApplyTransition:
    def test_phantom_source_raises(self, tenant, product, warehouse):
        """Regression for D-02 — no fabricated inventory from a non-existent source."""
        tr = StockStatusTransition.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            from_status='damaged', to_status='active', quantity=50,
        )
        with pytest.raises(ValueError):
            tr.apply_transition()
        # No active bucket credit
        assert not StockStatus.objects.filter(
            tenant=tenant, product=product, warehouse=warehouse, status='active',
        ).exists()

    def test_under_stocked_source_raises(
        self, tenant, damaged_status, product, warehouse
    ):
        # damaged_status has quantity=10
        tr = StockStatusTransition.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            from_status='damaged', to_status='active', quantity=50,
        )
        with pytest.raises(ValueError):
            tr.apply_transition()
        damaged_status.refresh_from_db()
        assert damaged_status.quantity == 10  # unchanged

    def test_valid_transition_preserves_sum(
        self, tenant, damaged_status, product, warehouse
    ):
        tr = StockStatusTransition.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            from_status='damaged', to_status='active', quantity=6,
        )
        tr.apply_transition()
        damaged_status.refresh_from_db()
        active = StockStatus.objects.get(
            tenant=tenant, product=product, warehouse=warehouse, status='active',
        )
        assert damaged_status.quantity == 4
        assert active.quantity == 6


@pytest.mark.django_db
class TestReservationStateMachine:
    @pytest.mark.parametrize("src,dst,ok", [
        ("pending", "confirmed", True),
        ("pending", "released", True),
        ("pending", "cancelled", True),
        ("pending", "expired", False),
        ("confirmed", "released", True),
        ("confirmed", "expired", True),
        ("confirmed", "pending", False),
        ("released", "pending", False),
        ("cancelled", "pending", True),
    ])
    def test_can_transition_to(self, pending_reservation, src, dst, ok):
        pending_reservation.status = src
        assert pending_reservation.can_transition_to(dst) is ok

    def test_is_expired_false_when_no_expires_at(self, pending_reservation):
        pending_reservation.expires_at = None
        # Property short-circuits to the falsy first operand (None), not the bool False.
        assert not pending_reservation.is_expired

    def test_is_expired_false_when_terminal(self, pending_reservation):
        pending_reservation.expires_at = timezone.now() - timedelta(hours=1)
        pending_reservation.status = 'released'
        assert pending_reservation.is_expired is False

    def test_is_expired_true_when_past_and_active(self, pending_reservation):
        pending_reservation.expires_at = timezone.now() - timedelta(hours=1)
        pending_reservation.status = 'pending'
        assert pending_reservation.is_expired is True


@pytest.mark.django_db
class TestSequenceGeneration:
    def test_adj_sequence(self, tenant, stock_level):
        a = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='increase', quantity=1, reason='other',
        )
        b = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='increase', quantity=1, reason='other',
        )
        assert a.adjustment_number == 'ADJ-00001'
        assert b.adjustment_number == 'ADJ-00002'

    def test_res_sequence(self, tenant, product, warehouse):
        r1 = InventoryReservation.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
        r2 = InventoryReservation.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
        assert r1.reservation_number == 'RES-00001'
        assert r2.reservation_number == 'RES-00002'
