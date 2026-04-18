from decimal import Decimal

import pytest

from multi_location.forms import (
    LocationForm, LocationPricingRuleForm,
    LocationTransferRuleForm, LocationSafetyStockRuleForm,
)
from multi_location.models import Location, LocationTransferRule, LocationSafetyStockRule


def _base_location_data(**overrides):
    data = {
        'name': 'Hub',
        'location_type': 'retail_store',
        'parent': '',
        'warehouse': '',
        'address': '', 'city': '', 'state': '', 'country': '',
        'postal_code': '', 'manager_name': '',
        'contact_email': '', 'contact_phone': '',
        'is_active': 'on', 'notes': '',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestLocationForm:
    def test_create_minimal(self, tenant):
        f = LocationForm(data=_base_location_data(), tenant=tenant)
        assert f.is_valid(), f.errors
        loc = f.save()
        assert loc.tenant == tenant
        assert loc.code.startswith("LOC-")

    def test_rejects_cross_tenant_parent(self, tenant, other_location):
        f = LocationForm(
            data=_base_location_data(parent=other_location.pk),
            tenant=tenant,
        )
        assert not f.is_valid()
        assert 'parent' in f.errors

    def test_rejects_cross_tenant_warehouse(self, tenant, other_tenant):
        from warehousing.models import Warehouse
        w = Warehouse.objects.create(tenant=other_tenant, code='W', name='W', is_active=True)
        f = LocationForm(data=_base_location_data(warehouse=w.pk), tenant=tenant)
        assert not f.is_valid()
        assert 'warehouse' in f.errors

    def test_excludes_self_and_descendants_on_edit(self, company, dc, tenant):
        """Cannot reparent HQ under one of its descendants."""
        f = LocationForm(
            instance=company,
            data=_base_location_data(
                name='HQ', location_type='company', parent=dc.pk,
            ),
            tenant=tenant,
        )
        assert not f.is_valid()
        assert 'parent' in f.errors

    def test_tenant_none_locks_querysets_to_empty(self, other_location):
        """Regression for D-03: superuser path must not cross-tenant select."""
        f = LocationForm(
            data=_base_location_data(parent=other_location.pk),
            tenant=None,
        )
        # parent queryset is .none(), so the choice is invalid
        assert not f.is_valid()
        assert 'parent' in f.errors


@pytest.mark.django_db
class TestPricingRuleForm:
    def _base(self, location, **overrides):
        data = {
            'location': location.pk, 'product': '', 'category': '',
            'rule_type': 'markup_pct', 'value': '10',
            'priority': 1, 'is_active': 'on',
            'effective_from': '', 'effective_to': '', 'notes': '',
        }
        data.update(overrides)
        return data

    def test_create_minimal(self, tenant, store):
        f = LocationPricingRuleForm(data=self._base(store), tenant=tenant)
        assert f.is_valid(), f.errors
        rule = f.save()
        assert rule.tenant == tenant

    def test_product_and_category_both_rejected(self, tenant, store, product, category):
        f = LocationPricingRuleForm(
            data=self._base(store, product=product.pk, category=category.pk),
            tenant=tenant,
        )
        assert not f.is_valid()

    @pytest.mark.parametrize("rule_type,value", [
        ("override_price", "-10"),    # D-06
        ("override_price", "0"),      # Must be > 0
        ("markup_pct", "-1"),         # D-06
        ("markup_pct", "1001"),       # D-07
        ("markdown_pct", "-1"),       # D-06
        ("markdown_pct", "101"),      # D-07
    ])
    def test_value_bounds_enforced(self, tenant, store, rule_type, value):
        f = LocationPricingRuleForm(
            data=self._base(store, rule_type=rule_type, value=value),
            tenant=tenant,
        )
        assert not f.is_valid()
        assert 'value' in f.errors

    @pytest.mark.parametrize("rule_type,value", [
        ("override_price", "0.01"),
        ("override_price", "999.99"),
        ("markup_pct", "0"),
        ("markup_pct", "1000"),
        ("markdown_pct", "0"),
        ("markdown_pct", "100"),
        ("fixed_adjustment", "-5.50"),  # Signed allowed for fixed adjustment
        ("fixed_adjustment", "5.50"),
    ])
    def test_value_bounds_allow_valid(self, tenant, store, rule_type, value):
        f = LocationPricingRuleForm(
            data=self._base(store, rule_type=rule_type, value=value),
            tenant=tenant,
        )
        assert f.is_valid(), f.errors

    def test_effective_from_after_to_rejected(self, tenant, store):
        """Regression for D-05."""
        f = LocationPricingRuleForm(
            data=self._base(store,
                            effective_from='2026-12-31',
                            effective_to='2026-01-01'),
            tenant=tenant,
        )
        assert not f.is_valid()
        assert 'effective_to' in f.errors

    def test_effective_from_equals_to_allowed(self, tenant, store):
        f = LocationPricingRuleForm(
            data=self._base(store,
                            effective_from='2026-06-01',
                            effective_to='2026-06-01'),
            tenant=tenant,
        )
        assert f.is_valid()

    def test_tenant_none_locks_querysets(self, other_location):
        f = LocationPricingRuleForm(
            data={'location': other_location.pk, 'product': '', 'category': '',
                  'rule_type': 'markup_pct', 'value': '5', 'priority': 1,
                  'is_active': 'on', 'effective_from': '', 'effective_to': '',
                  'notes': ''},
            tenant=None,
        )
        assert not f.is_valid()
        assert 'location' in f.errors


@pytest.mark.django_db
class TestTransferRuleForm:
    def _base(self, src, dst, **overrides):
        data = {
            'source_location': src.pk, 'destination_location': dst.pk,
            'allowed': 'on', 'max_transfer_qty': 0, 'lead_time_days': 0,
            'requires_approval': '', 'priority': 1,
            'is_active': 'on', 'notes': '',
        }
        data.update(overrides)
        return data

    def test_source_equals_destination_rejected(self, tenant, dc):
        f = LocationTransferRuleForm(data=self._base(dc, dc), tenant=tenant)
        assert not f.is_valid()

    def test_valid_source_to_destination(self, tenant, dc, store):
        f = LocationTransferRuleForm(data=self._base(dc, store), tenant=tenant)
        assert f.is_valid(), f.errors

    def test_duplicate_pair_rejected_by_form(self, tenant, dc, store):
        """Regression for D-11: unique_together trap caught at form layer."""
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc, destination_location=store,
        )
        f = LocationTransferRuleForm(data=self._base(dc, store), tenant=tenant)
        assert not f.is_valid()
        assert any('already exists' in str(e).lower() for e in f.non_field_errors())

    def test_duplicate_but_own_row_allowed_on_edit(self, tenant, dc, store):
        rule = LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc, destination_location=store,
        )
        f = LocationTransferRuleForm(
            instance=rule,
            data=self._base(dc, store, priority=2),
            tenant=tenant,
        )
        assert f.is_valid(), f.errors

    def test_tenant_none_locks_querysets(self, other_location):
        other2 = Location.objects.create(tenant=other_location.tenant, name='F2')
        f = LocationTransferRuleForm(
            data={'source_location': other_location.pk,
                  'destination_location': other2.pk,
                  'allowed': 'on', 'max_transfer_qty': 0, 'lead_time_days': 0,
                  'requires_approval': '', 'priority': 1,
                  'is_active': 'on', 'notes': ''},
            tenant=None,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestSafetyStockRuleForm:
    def _base(self, loc, p, **overrides):
        data = {
            'location': loc.pk, 'product': p.pk,
            'safety_stock_qty': 5, 'reorder_point': 10, 'max_stock_qty': 100,
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_create_minimal(self, tenant, store, product):
        f = LocationSafetyStockRuleForm(data=self._base(store, product), tenant=tenant)
        assert f.is_valid(), f.errors

    def test_safety_gt_reorder_rejected(self, tenant, store, product):
        """Regression for D-04."""
        f = LocationSafetyStockRuleForm(
            data=self._base(store, product, safety_stock_qty=100, reorder_point=10),
            tenant=tenant,
        )
        assert not f.is_valid()
        assert 'reorder_point' in f.errors

    def test_reorder_gt_max_rejected_when_max_nonzero(self, tenant, store, product):
        f = LocationSafetyStockRuleForm(
            data=self._base(store, product,
                            safety_stock_qty=5, reorder_point=50, max_stock_qty=10),
            tenant=tenant,
        )
        assert not f.is_valid()
        assert 'max_stock_qty' in f.errors

    def test_max_zero_means_no_ceiling(self, tenant, store, product):
        f = LocationSafetyStockRuleForm(
            data=self._base(store, product,
                            safety_stock_qty=5, reorder_point=999_999, max_stock_qty=0),
            tenant=tenant,
        )
        assert f.is_valid()

    def test_duplicate_location_product_rejected(self, tenant, store, product):
        """Regression for D-11."""
        LocationSafetyStockRule.objects.create(
            tenant=tenant, location=store, product=product,
            safety_stock_qty=1, reorder_point=2,
        )
        f = LocationSafetyStockRuleForm(data=self._base(store, product), tenant=tenant)
        assert not f.is_valid()
        assert any('already exists' in str(e).lower() for e in f.non_field_errors())

    def test_tenant_none_locks_querysets(self, other_location, other_product):
        f = LocationSafetyStockRuleForm(
            data={'location': other_location.pk, 'product': other_product.pk,
                  'safety_stock_qty': 5, 'reorder_point': 10, 'max_stock_qty': 100,
                  'notes': ''},
            tenant=None,
        )
        assert not f.is_valid()
