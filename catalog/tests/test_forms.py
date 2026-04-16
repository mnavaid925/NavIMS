"""Form-validation tests.

Covers:
- TC-PROD-005 / TC-PROD-006  wholesale/cost vs retail cross-checks
- TC-PROD-007                 D-02 fix: negative values rejected
- TC-PROD-016                 D-04 fix: user-entered markup=0 preserved
- TC-CAT-003 / TC-CAT-004     hierarchy depth & circular prevention
"""
from decimal import Decimal

import pytest

from catalog.forms import CategoryForm, ProductForm


def _prod_payload(**overrides):
    data = dict(
        sku="TC-001",
        name="Test Product",
        status="draft",
        purchase_cost="100.00",
        retail_price="150.00",
        wholesale_price="120.00",
        markup_percentage="",
        is_active="on",
    )
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestProductFormPricingCrossChecks:
    def test_wholesale_exceeds_retail_rejected(self, tenant):
        form = ProductForm(
            data=_prod_payload(wholesale_price="200.00"), tenant=tenant,
        )
        assert not form.is_valid()
        assert "wholesale_price" in form.errors

    def test_cost_exceeds_retail_rejected(self, tenant):
        form = ProductForm(
            data=_prod_payload(purchase_cost="200.00"), tenant=tenant,
        )
        assert not form.is_valid()
        assert "purchase_cost" in form.errors


@pytest.mark.django_db
class TestD02NegativeValuesBlocked:
    """Regression guard for D-02 (MinValueValidator fix)."""

    @pytest.mark.parametrize("field", [
        "purchase_cost",
        "wholesale_price",
        "retail_price",
        "markup_percentage",
    ])
    def test_negative_pricing_rejected(self, tenant, field):
        form = ProductForm(
            data=_prod_payload(**{field: "-1.00"}, ),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert field in form.errors

    @pytest.mark.parametrize("field", ["weight", "length", "width", "height"])
    def test_negative_dimensions_rejected(self, tenant, field):
        form = ProductForm(
            data=_prod_payload(
                markup_percentage="50.00",
                **{field: "-1.0"},
            ),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert field in form.errors


@pytest.mark.django_db
class TestD04MarkupOverwrite:
    """Regression guard for D-04 (auto-compute only when blank)."""

    def test_explicit_zero_markup_preserved(self, tenant):
        form = ProductForm(
            data=_prod_payload(
                purchase_cost="100.00",
                retail_price="150.00",
                markup_percentage="0",
            ),
            tenant=tenant,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["markup_percentage"] == 0

    def test_blank_markup_auto_computed(self, tenant):
        form = ProductForm(
            data=_prod_payload(
                purchase_cost="100.00",
                retail_price="150.00",
                markup_percentage="",
            ),
            tenant=tenant,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["markup_percentage"] == Decimal("50.00")

    def test_user_explicit_markup_preserved(self, tenant):
        form = ProductForm(
            data=_prod_payload(
                purchase_cost="100.00",
                retail_price="150.00",
                markup_percentage="42.50",
            ),
            tenant=tenant,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["markup_percentage"] == Decimal("42.50")


@pytest.mark.django_db
class TestCategoryFormHierarchy:
    def test_only_dept_and_cat_allowed_as_parent(self, tenant, category):
        category.children.create(tenant=tenant, name="Gaming")
        form = CategoryForm(tenant=tenant)
        allowed_levels = set(
            form.fields["parent"].queryset.values_list("level", flat=True)
        )
        assert "subcategory" not in allowed_levels

    def test_self_and_descendants_excluded_from_parent_choices(
        self, tenant, department, category,
    ):
        form = CategoryForm(instance=department, tenant=tenant)
        parent_pks = set(
            form.fields["parent"].queryset.values_list("pk", flat=True)
        )
        assert department.pk not in parent_pks
        assert category.pk not in parent_pks
