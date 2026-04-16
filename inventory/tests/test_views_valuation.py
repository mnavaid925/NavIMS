"""D-04 correctness regression: FIFO vs LIFO vs Weighted-Avg must differ."""

from decimal import Decimal

import pytest
from django.urls import reverse

from inventory.models import InventoryValuation


@pytest.mark.django_db
class TestValuationCorrectness:
    """Canonical fixture:

    Layer A (old): qty=5, unit_cost=$10
    Layer B (new): qty=5, unit_cost=$20
    StockLevel.on_hand = 5  (5 units were issued at some point)

    Under each method, the REMAINING 5 units are valued as follows:
      - FIFO: oldest issued first → remaining are newest layer → $20.00
      - LIFO: newest issued first → remaining are oldest layer → $10.00
      - WAVG: remaining valued at blended average $15.00
    """

    def _set_on_hand(self, stock_level, on_hand):
        stock_level.on_hand = on_hand
        stock_level.save()

    def test_fifo_values_on_hand_at_newest_layer_cost(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        self._set_on_hand(stock_level, 5)
        valuation_config.method = 'fifo'
        valuation_config.save()

        client.force_login(admin_user)
        resp = client.post(reverse('inventory:valuation_recalculate'))
        assert resp.status_code == 302
        v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
        assert v.unit_cost == Decimal('20.00')
        assert v.total_quantity == 5
        assert v.total_value == Decimal('100.00')

    def test_lifo_values_on_hand_at_oldest_layer_cost(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        self._set_on_hand(stock_level, 5)
        valuation_config.method = 'lifo'
        valuation_config.save()

        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
        assert v.unit_cost == Decimal('10.00')
        assert v.total_value == Decimal('50.00')

    def test_weighted_avg_blends_layers(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        self._set_on_hand(stock_level, 10)
        valuation_config.method = 'weighted_avg'
        valuation_config.save()

        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
        assert v.unit_cost == Decimal('15.00')
        assert v.total_value == Decimal('150.00')

    def test_methods_produce_distinct_unit_cost_on_partial_consumption(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        """The core regression: same fixture → THREE different answers."""
        self._set_on_hand(stock_level, 5)
        results = {}
        client.force_login(admin_user)
        for method in ('fifo', 'lifo', 'weighted_avg'):
            valuation_config.method = method
            valuation_config.save()
            client.post(reverse('inventory:valuation_recalculate'))
            v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
            results[method] = v.unit_cost
        assert results['fifo'] != results['lifo']
        assert results['fifo'] != results['weighted_avg']
        assert results['lifo'] != results['weighted_avg']
        assert results == {
            'fifo': Decimal('20.00'),
            'lifo': Decimal('10.00'),
            'weighted_avg': Decimal('15.00'),
        }


@pytest.mark.django_db
class TestValuationEdgeCases:
    def test_zero_on_hand_no_valuation_row(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        stock_level.on_hand = 0
        stock_level.save()
        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        assert InventoryValuation.objects.filter(tenant=tenant).count() == 0

    def test_no_layers_skips_product(
        self, client, admin_user, tenant, stock_level, valuation_config
    ):
        # no cost_layers fixture
        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        assert InventoryValuation.objects.filter(tenant=tenant).count() == 0
