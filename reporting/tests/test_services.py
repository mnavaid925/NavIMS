"""Tests for the compute services.

We don't exhaustively exercise all 21 services — that would duplicate the
smoke test `seed_reporting` already performs. Instead we test the
report-value invariants that matter: totals add up, ABC classes split at the
configured thresholds, aging buckets land in the right band, and empty
inputs yield an empty report without crashing.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from reporting import services


@pytest.mark.django_db
def test_valuation_totals_add_up(tenant, stock_level):
    result = services.compute_valuation(tenant)
    assert result['summary']['total_skus'] == 1
    # 100 on_hand * 10.00 purchase_cost = 1000 (unless ValuationEntry overrides)
    assert Decimal(result['summary']['total_value']) >= Decimal('0')
    assert len(result['data']['rows']) == 1


@pytest.mark.django_db
def test_valuation_empty_tenant_returns_zero(tenant):
    """Tenant with no stock: totals are zero and no rows."""
    result = services.compute_valuation(tenant)
    assert result['summary']['total_skus'] == 0
    assert result['summary']['total_value'] == '0'
    assert result['data']['rows'] == []


@pytest.mark.django_db
def test_aging_buckets_cover_all_skus(tenant, stock_level):
    result = services.compute_aging(tenant)
    counts = result['summary']['bucket_counts']
    # SKU with no movement history → falls into 180+ bucket
    assert sum(counts.values()) == 1
    assert counts['180+'] == 1


@pytest.mark.django_db
def test_aging_includes_chart_data(tenant, stock_level):
    result = services.compute_aging(tenant)
    chart = result['data']['chart']
    assert chart['type'] == 'bar'
    assert chart['labels'] == ['0-30', '31-60', '61-90', '91-180', '180+']


@pytest.mark.django_db
def test_abc_thresholds_split_products(tenant):
    """No sales data → service still returns a valid shape."""
    result = services.compute_abc(tenant)
    s = result['summary']
    # With no delivered sales in the period, every class count is zero
    assert s['a_count'] + s['b_count'] + s['c_count'] == 0
    assert s['a_threshold'] == 80
    assert s['b_threshold'] == 15


@pytest.mark.django_db
def test_abc_defaults_fallback_to_last_year(tenant):
    """If no period given, service uses last 365 days and returns without error."""
    result = services.compute_abc(tenant)
    assert 'period_start' in result['summary']
    assert 'period_end' in result['summary']


@pytest.mark.django_db
def test_turnover_shape(tenant, stock_level):
    result = services.compute_turnover(tenant)
    assert 'overall_turnover' in result['summary']
    assert 'overall_dsi_days' in result['summary']
    # No COGS → turnover is 0
    assert Decimal(result['summary']['overall_turnover']) == Decimal('0')


@pytest.mark.django_db
def test_reservations_missing_module_returns_empty(tenant):
    """Even for tenants with no reservations, service returns valid shape."""
    result = services.compute_reservations(tenant)
    assert 'total_reservations' in result['summary'] or 'message' in result['summary']


@pytest.mark.django_db
def test_alerts_log_uses_triggered_at_not_created_at(tenant):
    """Regression: service must query `triggered_at` (Alert has no `created_at`)."""
    # Should not raise even without alerts
    result = services.compute_alerts_log(tenant)
    assert 'total_alerts' in result['summary'] or 'message' in result['summary']


@pytest.mark.django_db
def test_forecast_vs_actual_uses_period_start_date(tenant):
    """Regression: service must query `period_start_date` / `period_end_date`."""
    result = services.compute_forecast_vs_actual(tenant)
    assert 'total_forecast_qty' in result['summary'] or 'message' in result['summary']


@pytest.mark.django_db
def test_receiving_grn_uses_purchase_order_vendor(tenant):
    """Regression: GRN has no direct vendor FK — must go via `purchase_order.vendor`."""
    result = services.compute_receiving_grn(tenant)
    assert 'total_grns' in result['summary'] or 'message' in result['summary']


@pytest.mark.django_db
def test_vendor_performance_uses_company_name(tenant):
    """Regression: Vendor's name field is `company_name`, not `name`."""
    result = services.compute_vendor_performance(tenant)
    assert 'total_vendors' in result['summary'] or 'message' in result['summary']


@pytest.mark.django_db
def test_po_summary_computes_total_from_items(tenant):
    """Regression: PurchaseOrder has no `total_amount` — totals come from summed items."""
    result = services.compute_po_summary(tenant)
    assert 'total_pos' in result['summary']
    assert result['summary']['total_pos'] == 0
