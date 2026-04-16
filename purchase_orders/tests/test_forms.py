from decimal import Decimal
from datetime import date, timedelta

import pytest

from purchase_orders.forms import (
    PurchaseOrderForm, PurchaseOrderItemFormSet, ApprovalRuleForm,
)


@pytest.mark.django_db
class TestApprovalRuleForm:
    def test_min_greater_than_max_rejected(self, tenant):
        """Regression for D-06."""
        form = ApprovalRuleForm(
            data={
                'name': 'Bad', 'min_amount': '1000', 'max_amount': '10',
                'required_approvals': '1', 'is_active': 'on',
            },
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'max_amount' in form.errors

    def test_valid_range_accepted(self, tenant):
        form = ApprovalRuleForm(
            data={
                'name': 'Normal', 'min_amount': '0', 'max_amount': '1000',
                'required_approvals': '1', 'is_active': 'on',
            },
            tenant=tenant,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestPurchaseOrderForm:
    def test_vendor_queryset_is_tenant_scoped(self, tenant, other_tenant):
        from vendors.models import Vendor
        v_mine = Vendor.objects.create(
            tenant=tenant, company_name="Mine", is_active=True, status="active")
        v_other = Vendor.objects.create(
            tenant=other_tenant, company_name="Theirs", is_active=True, status="active")
        form = PurchaseOrderForm(tenant=tenant)
        qs = form.fields['vendor'].queryset
        assert v_mine in qs
        assert v_other not in qs

    def test_delivery_date_must_not_precede_order_date(self, tenant, vendor):
        """Regression for D-18."""
        form = PurchaseOrderForm(
            data={
                'vendor': str(vendor.pk),
                'order_date': str(date.today()),
                'expected_delivery_date': str(date.today() - timedelta(days=1)),
                'payment_terms': 'net_30',
                'shipping_address': '',
                'notes': '',
            },
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'expected_delivery_date' in form.errors


@pytest.mark.django_db
class TestItemFormSet:
    def test_zero_items_blocked(self, draft_po):
        """Regression for D-17 — formset requires min_num=1."""
        data = {
            "items-TOTAL_FORMS": "0",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
        }
        fs = PurchaseOrderItemFormSet(data, instance=draft_po, prefix="items")
        # delete existing item to simulate zero net items
        draft_po.items.all().delete()
        fs = PurchaseOrderItemFormSet(data, instance=draft_po, prefix="items")
        assert not fs.is_valid()
