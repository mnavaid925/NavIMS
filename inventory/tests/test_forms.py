import pytest

from inventory.forms import (
    StockAdjustmentForm, StockStatusTransitionForm, InventoryReservationForm,
)


@pytest.mark.django_db
class TestAdjustmentForm:
    def test_qty_zero_rejected(self, tenant, stock_level):
        """Regression for D-13."""
        form = StockAdjustmentForm(
            data={'adjustment_type': 'increase', 'quantity': '0',
                  'reason': 'other', 'notes': ''},
            tenant=tenant, stock_level=stock_level,
        )
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_over_decrement_rejected(self, tenant, stock_level):
        """Regression for D-01."""
        form = StockAdjustmentForm(
            data={'adjustment_type': 'decrease', 'quantity': '9999',
                  'reason': 'damage', 'notes': ''},
            tenant=tenant, stock_level=stock_level,
        )
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_valid_increase(self, tenant, stock_level):
        form = StockAdjustmentForm(
            data={'adjustment_type': 'increase', 'quantity': '10',
                  'reason': 'return', 'notes': ''},
            tenant=tenant, stock_level=stock_level,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestTransitionForm:
    def _data(self, product, warehouse, **over):
        d = {
            'product': product.pk, 'warehouse': warehouse.pk,
            'from_status': 'damaged', 'to_status': 'active',
            'quantity': 5, 'reason': 'x',
        }
        d.update(over)
        return d

    def test_same_from_to_status_rejected(self, tenant, product, warehouse):
        form = StockStatusTransitionForm(
            data=self._data(product, warehouse, from_status='active', to_status='active'),
            tenant=tenant,
        )
        assert not form.is_valid()

    def test_phantom_source_rejected(self, tenant, product, warehouse):
        """Regression for D-02 — no StockStatus(damaged) exists."""
        form = StockStatusTransitionForm(
            data=self._data(product, warehouse, quantity=50),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'from_status' in form.errors

    def test_under_stocked_source_rejected(
        self, tenant, damaged_status, product, warehouse
    ):
        """damaged=10; try to transition 50."""
        form = StockStatusTransitionForm(
            data=self._data(product, warehouse, quantity=50),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_valid_transition_accepted(
        self, tenant, damaged_status, product, warehouse
    ):
        form = StockStatusTransitionForm(
            data=self._data(product, warehouse, quantity=5),
            tenant=tenant,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestReservationForm:
    def _data(self, product, warehouse, qty):
        return {
            'product': product.pk, 'warehouse': warehouse.pk,
            'quantity': qty, 'reference_type': '', 'reference_number': '',
            'expires_at': '', 'notes': '',
        }

    def test_over_reserve_rejected(self, tenant, stock_level, product, warehouse):
        """Regression for D-03 — reserve > available."""
        form = InventoryReservationForm(
            data=self._data(product, warehouse, qty=9999), tenant=tenant,
        )
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_no_stock_level_rejected(self, tenant, product, warehouse):
        """No StockLevel for (product, warehouse)."""
        form = InventoryReservationForm(
            data=self._data(product, warehouse, qty=1), tenant=tenant,
        )
        assert not form.is_valid()
        # The error may land on product OR quantity depending on clean() order
        assert form.errors

    def test_valid_reserve_accepted(self, tenant, stock_level, product, warehouse):
        form = InventoryReservationForm(
            data=self._data(product, warehouse, qty=5), tenant=tenant,
        )
        assert form.is_valid(), form.errors

    def test_qty_zero_rejected(self, tenant, stock_level, product, warehouse):
        form = InventoryReservationForm(
            data=self._data(product, warehouse, qty=0), tenant=tenant,
        )
        assert not form.is_valid()
