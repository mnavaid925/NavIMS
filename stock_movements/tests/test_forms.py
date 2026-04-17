import pytest

from stock_movements.forms import (
    StockTransferForm, StockTransferItemForm,
    TransferRouteForm, TransferApprovalRuleForm,
)


@pytest.mark.django_db
class TestStockTransferForm:
    def test_inter_requires_distinct_warehouses(self, tenant, w1):
        f = StockTransferForm(
            data={"transfer_type": "inter_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(w1.pk),
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors

    def test_inter_requires_destination(self, tenant, w1):
        f = StockTransferForm(
            data={"transfer_type": "inter_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": "",
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors

    def test_intra_coerces_dest_to_src(self, tenant, w1):
        f = StockTransferForm(
            data={"transfer_type": "intra_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": "",
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors
        assert f.cleaned_data["destination_warehouse"] == w1

    def test_inter_rejects_foreign_dest_warehouse(self, tenant, w1, other_warehouse):
        f = StockTransferForm(
            data={"transfer_type": "inter_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(other_warehouse.pk),
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors


@pytest.mark.django_db
class TestStockTransferItemForm:
    def test_D12_product_filter_uses_status_active(self, tenant, category):
        from catalog.models import Product
        Product.objects.create(
            tenant=tenant, category=category, sku="D-1",
            name="DraftWidget", status="draft", is_active=True,
        )
        active = Product.objects.create(
            tenant=tenant, category=category, sku="A-1",
            name="ActiveWidget", status="active", is_active=True,
        )
        f = StockTransferItemForm(tenant=tenant)
        qs = list(f.fields["product"].queryset)
        assert active in qs
        assert all(p.status == "active" for p in qs)


@pytest.mark.django_db
class TestRouteForm:
    def test_src_eq_dest_rejected(self, tenant, w1):
        f = TransferRouteForm(
            data={"name": "X", "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(w1.pk),
                  "transit_method": "truck", "estimated_duration_hours": "4",
                  "distance_km": "1.0", "instructions": "", "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors

    def test_happy(self, tenant, w1, w2):
        f = TransferRouteForm(
            data={"name": "Happy", "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(w2.pk),
                  "transit_method": "van", "estimated_duration_hours": "2",
                  "distance_km": "10.5", "instructions": "go", "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors


@pytest.mark.django_db
class TestApprovalRuleForm:
    def test_D10_min_greater_than_max_rejected(self, tenant):
        f = TransferApprovalRuleForm(
            data={"name": "Bad", "min_items": "10", "max_items": "5",
                  "requires_approval": True, "approver_role": "Manager",
                  "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "max_items" in f.errors

    def test_D10_unlimited_max_allowed(self, tenant):
        f = TransferApprovalRuleForm(
            data={"name": "Big", "min_items": "100", "max_items": "",
                  "requires_approval": True, "approver_role": "Admin",
                  "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors

    def test_D10_min_equal_max_allowed(self, tenant):
        f = TransferApprovalRuleForm(
            data={"name": "Exact", "min_items": "5", "max_items": "5",
                  "requires_approval": True, "approver_role": "Manager",
                  "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors
