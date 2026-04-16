from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from receiving.forms import (
    GoodsReceiptNoteItemForm, GoodsReceiptNoteItemFormSet,
    QualityInspectionItemForm, QualityInspectionItemFormSet,
    VendorInvoiceForm, WarehouseLocationForm,
)
from receiving.models import (
    GoodsReceiptNote, GoodsReceiptNoteItem, VendorInvoice, WarehouseLocation,
)


# ────────────────────────────
# WarehouseLocationForm — D-01 + self-parent guard
# ────────────────────────────

@pytest.mark.django_db
class TestWarehouseLocationForm:
    def test_D01_duplicate_code_rejected_at_form(self, tenant):
        WarehouseLocation.objects.create(
            tenant=tenant, name="Existing", code="DUP", location_type="bin",
        )
        f = WarehouseLocationForm(
            data={"name": "New", "code": "DUP", "location_type": "bin",
                  "parent": "", "capacity": "10", "is_active": True, "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "code" in f.errors

    def test_D01_duplicate_code_case_insensitive(self, tenant):
        WarehouseLocation.objects.create(
            tenant=tenant, name="Existing", code="dup", location_type="bin",
        )
        f = WarehouseLocationForm(
            data={"name": "New", "code": "DUP", "location_type": "bin",
                  "parent": "", "capacity": "10", "is_active": True, "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "code" in f.errors

    def test_same_code_allowed_across_tenants(self, tenant, other_tenant):
        WarehouseLocation.objects.create(
            tenant=other_tenant, name="Existing", code="DUP", location_type="bin",
        )
        f = WarehouseLocationForm(
            data={"name": "New", "code": "DUP", "location_type": "bin",
                  "parent": "", "capacity": "10", "is_active": True, "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors

    def test_edit_keeps_own_code(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="Existing", code="KEEP", location_type="bin",
        )
        f = WarehouseLocationForm(
            data={"name": "Updated", "code": "KEEP", "location_type": "bin",
                  "parent": "", "capacity": "10", "is_active": True, "notes": ""},
            instance=loc, tenant=tenant,
        )
        assert f.is_valid() is True, f.errors

    def test_self_parent_rejected(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="X", code="SELF", location_type="bin",
        )
        f = WarehouseLocationForm(
            data={"name": "X", "code": "SELF", "location_type": "bin",
                  "parent": str(loc.pk), "capacity": "10",
                  "is_active": True, "notes": ""},
            instance=loc, tenant=tenant,
        )
        assert f.is_valid() is False
        assert "parent" in f.errors


# ────────────────────────────
# VendorInvoiceForm — D-01, D-02, D-07
# ────────────────────────────

@pytest.mark.django_db
class TestVendorInvoiceForm:
    def _valid_data(self, vendor, po):
        return {
            "invoice_number": "INV-1",
            "vendor": str(vendor.pk),
            "purchase_order": str(po.pk),
            "invoice_date": "2026-01-05",
            "due_date": "",
            "subtotal": "100.00",
            "tax_amount": "10.00",
            "total_amount": "110.00",
            "notes": "",
        }

    def test_D01_duplicate_invoice_number_rejected_at_form(self, tenant, vendor, po):
        VendorInvoice.objects.create(
            tenant=tenant, invoice_number="INV-1", vendor=vendor, purchase_order=po,
            invoice_date=date(2026, 1, 1),
            subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
        )
        f = VendorInvoiceForm(data=self._valid_data(vendor, po), tenant=tenant)
        assert f.is_valid() is False
        assert "invoice_number" in f.errors

    def test_same_invoice_number_across_tenants(self, tenant, other_tenant, vendor, other_vendor, po, other_po):
        VendorInvoice.objects.create(
            tenant=other_tenant, invoice_number="INV-1", vendor=other_vendor,
            purchase_order=other_po, invoice_date=date(2026, 1, 1),
            subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
        )
        f = VendorInvoiceForm(data=self._valid_data(vendor, po), tenant=tenant)
        assert f.is_valid() is True, f.errors

    def test_D07_totals_reconciled(self, tenant, vendor, po):
        bad = self._valid_data(vendor, po)
        bad["total_amount"] = "99999.00"  # != subtotal + tax
        f = VendorInvoiceForm(data=bad, tenant=tenant)
        assert f.is_valid() is False
        assert "total_amount" in f.errors

    def test_D02_exe_upload_rejected(self, tenant, vendor, po):
        exe = SimpleUploadedFile("payload.exe", b"MZ" + b"\x00" * 1024,
                                 content_type="application/octet-stream")
        f = VendorInvoiceForm(
            data=self._valid_data(vendor, po), files={"document": exe}, tenant=tenant,
        )
        assert f.is_valid() is False
        assert "document" in f.errors

    def test_D02_svg_upload_rejected(self, tenant, vendor, po):
        svg = SimpleUploadedFile(
            "evil.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type="image/svg+xml",
        )
        f = VendorInvoiceForm(
            data=self._valid_data(vendor, po), files={"document": svg}, tenant=tenant,
        )
        assert f.is_valid() is False
        assert "document" in f.errors

    def test_D02_oversize_pdf_rejected(self, tenant, vendor, po):
        # 11 MB
        big = SimpleUploadedFile(
            "big.pdf", b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024),
            content_type="application/pdf",
        )
        f = VendorInvoiceForm(
            data=self._valid_data(vendor, po), files={"document": big}, tenant=tenant,
        )
        assert f.is_valid() is False
        assert "document" in f.errors

    def test_D02_pdf_upload_accepted(self, tenant, vendor, po):
        pdf = SimpleUploadedFile(
            "ok.pdf", b"%PDF-1.4\nhello", content_type="application/pdf",
        )
        f = VendorInvoiceForm(
            data=self._valid_data(vendor, po), files={"document": pdf}, tenant=tenant,
        )
        assert f.is_valid() is True, f.errors


# ────────────────────────────
# GoodsReceiptNoteItemForm — D-04 + D-06
# ────────────────────────────

@pytest.mark.django_db
class TestGrnItemForm:
    def test_D04_foreign_po_item_rejected(self, tenant, other_po_item, product):
        """Tenant-A user cannot bind a tenant-B PO item into their GRN."""
        f = GoodsReceiptNoteItemForm(
            data={"po_item": str(other_po_item.pk), "product": str(product.pk),
                  "quantity_received": "1", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "po_item" in f.errors

    def test_D04_foreign_product_rejected(self, tenant, po_item, other_product):
        f = GoodsReceiptNoteItemForm(
            data={"po_item": str(po_item.pk), "product": str(other_product.pk),
                  "quantity_received": "1", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "product" in f.errors

    def test_D06_over_receipt_rejected(self, tenant, po_item, product):
        f = GoodsReceiptNoteItemForm(
            data={"po_item": str(po_item.pk), "product": str(product.pk),
                  "quantity_received": str(po_item.quantity + 5), "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "quantity_received" in f.errors

    def test_D06_receipt_equal_to_outstanding_allowed(self, tenant, po_item, product):
        f = GoodsReceiptNoteItemForm(
            data={"po_item": str(po_item.pk), "product": str(product.pk),
                  "quantity_received": str(po_item.quantity), "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors

    def test_D06_subsequent_receipt_limited_to_remaining(self, tenant, po, po_item, product, user):
        # Receive 4 of 10 in a completed GRN.
        g1 = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g1, po_item=po_item, product=product, quantity_received=4,
        )
        # 7 is now over-receipt (only 6 outstanding).
        f = GoodsReceiptNoteItemForm(
            data={"po_item": str(po_item.pk), "product": str(product.pk),
                  "quantity_received": "7", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "quantity_received" in f.errors


# ────────────────────────────
# QualityInspectionItemForm — D-04 + D-11
# ────────────────────────────

@pytest.mark.django_db
class TestQualityInspectionItemForm:
    def test_D11_invariant_violation_rejected(self, tenant, po, po_item, product, user):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        gi = GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product, quantity_received=10,
        )
        f = QualityInspectionItemForm(
            data={
                "grn_item": str(gi.pk), "product": str(product.pk),
                "quantity_inspected": "10",
                "quantity_accepted": "3",
                "quantity_rejected": "2",
                "quantity_quarantined": "2",  # sum 7 ≠ 10
                "decision": "accepted", "reject_reason": "", "notes": "",
            },
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert f.errors  # non-field or field error at form level

    def test_D11_invariant_satisfied(self, tenant, po, po_item, product, user):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        gi = GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product, quantity_received=10,
        )
        f = QualityInspectionItemForm(
            data={
                "grn_item": str(gi.pk), "product": str(product.pk),
                "quantity_inspected": "10",
                "quantity_accepted": "7",
                "quantity_rejected": "2",
                "quantity_quarantined": "1",
                "decision": "accepted", "reject_reason": "", "notes": "",
            },
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors
