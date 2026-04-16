from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from receiving.models import (
    GoodsReceiptNote, GoodsReceiptNoteItem, VendorInvoice, WarehouseLocation,
    QualityInspection, PutawayTask, ThreeWayMatch,
)


# ────────────────────────────
# GRN views
# ────────────────────────────

@pytest.mark.django_db
class TestGrnViews:
    def test_list_200_for_tenant_admin(self, client_logged_in, grn):
        r = client_logged_in.get(reverse("receiving:grn_list"))
        assert r.status_code == 200
        assert grn.grn_number.encode() in r.content

    def test_detail_cross_tenant_returns_404(self, client, user, other_tenant, other_po, other_user):
        g = GoodsReceiptNote.objects.create(
            tenant=other_tenant, purchase_order=other_po,
            received_date=date(2026, 1, 1), created_by=other_user,
        )
        client.force_login(user)
        r = client.get(reverse("receiving:grn_detail", args=[g.pk]))
        assert r.status_code == 404

    def test_edit_non_draft_redirects(self, client_logged_in, grn):
        grn.status = "completed"
        grn.save()
        r = client_logged_in.get(reverse("receiving:grn_edit", args=[grn.pk]))
        assert r.status_code == 302

    def test_delete_non_draft_rejected(self, client_logged_in, grn):
        grn.status = "completed"
        grn.save()
        r = client_logged_in.post(reverse("receiving:grn_delete", args=[grn.pk]))
        assert r.status_code == 302
        assert GoodsReceiptNote.objects.filter(pk=grn.pk).exists()

    def test_delete_draft_succeeds(self, client_logged_in, grn):
        r = client_logged_in.post(reverse("receiving:grn_delete", args=[grn.pk]))
        assert r.status_code == 302
        assert not GoodsReceiptNote.objects.filter(pk=grn.pk).exists()

    def test_D04_cross_tenant_po_item_on_post_rejected(
        self, client_logged_in, tenant, po, other_po_item,
    ):
        """Regression for D-04 — tenant A user submits tenant B's po_item id."""
        payload = {
            "purchase_order": str(po.pk),
            "received_date": "2026-02-01",
            "delivery_note_number": "",
            "notes": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-po_item": str(other_po_item.pk),  # foreign tenant
            "items-0-product": "",
            "items-0-quantity_received": "1",
            "items-0-notes": "",
        }
        r = client_logged_in.post(reverse("receiving:grn_create"), data=payload)
        assert r.status_code == 200  # re-rendered with errors, not a redirect
        assert GoodsReceiptNote.objects.filter(tenant=tenant).count() == 0

    def test_transition_completed_updates_po_status(
        self, client_logged_in, tenant, po, po_item, product, user,
    ):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 2, 1),
            status="inspecting", created_by=user,
        )
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product,
            quantity_received=po_item.quantity,
        )
        r = client_logged_in.post(
            reverse("receiving:grn_transition", args=[g.pk, "completed"]),
        )
        assert r.status_code == 302
        po.refresh_from_db()
        assert po.status == "received"


# ────────────────────────────
# Vendor Invoice views — D-02, D-07
# ────────────────────────────

@pytest.mark.django_db
class TestInvoiceViews:
    def _payload(self, vendor, po, number="INV-V1"):
        return {
            "invoice_number": number,
            "vendor": str(vendor.pk),
            "purchase_order": str(po.pk),
            "invoice_date": "2026-01-05",
            "due_date": "",
            "subtotal": "10.00",
            "tax_amount": "0.00",
            "total_amount": "10.00",
            "notes": "",
        }

    def test_D02_exe_upload_rejected_at_view(self, client_logged_in, vendor, po):
        exe = SimpleUploadedFile("x.exe", b"MZ\x00" * 100, content_type="application/octet-stream")
        r = client_logged_in.post(
            reverse("receiving:invoice_create"),
            data={**self._payload(vendor, po, "EXE-1"), "document": exe},
        )
        assert r.status_code == 200
        assert not VendorInvoice.objects.filter(invoice_number="EXE-1").exists()

    def test_D07_invoice_total_mismatch_rejected(self, client_logged_in, vendor, po):
        data = self._payload(vendor, po, "TOT-1")
        data["total_amount"] = "9999.00"
        r = client_logged_in.post(reverse("receiving:invoice_create"), data=data)
        assert r.status_code == 200
        assert not VendorInvoice.objects.filter(invoice_number="TOT-1").exists()

    def test_happy_invoice_create(self, client_logged_in, vendor, po):
        r = client_logged_in.post(
            reverse("receiving:invoice_create"), data=self._payload(vendor, po, "INV-HAPPY"),
        )
        assert r.status_code == 302
        assert VendorInvoice.objects.filter(invoice_number="INV-HAPPY").exists()

    def test_cross_tenant_invoice_detail_404(self, client, user, other_tenant, other_vendor, other_po):
        inv = VendorInvoice.objects.create(
            tenant=other_tenant, invoice_number="X", vendor=other_vendor,
            purchase_order=other_po, invoice_date=date(2026, 1, 1),
            subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
        )
        client.force_login(user)
        r = client.get(reverse("receiving:invoice_detail", args=[inv.pk]))
        assert r.status_code == 404


# ────────────────────────────
# Location views — D-01
# ────────────────────────────

@pytest.mark.django_db
class TestLocationViews:
    def test_D01_duplicate_code_rejected(self, client_logged_in, tenant):
        WarehouseLocation.objects.create(
            tenant=tenant, name="X", code="DUP", location_type="bin",
        )
        r = client_logged_in.post(
            reverse("receiving:location_create"),
            data={"name": "X2", "code": "DUP", "location_type": "bin",
                  "parent": "", "capacity": "10", "is_active": "on", "notes": ""},
        )
        assert r.status_code == 200
        assert WarehouseLocation.objects.filter(tenant=tenant, code="DUP").count() == 1

    def test_delete_with_children_rejected(self, client_logged_in, tenant):
        z = WarehouseLocation.objects.create(
            tenant=tenant, name="Z", code="Z1", location_type="zone",
        )
        WarehouseLocation.objects.create(
            tenant=tenant, name="A", code="A1", parent=z, location_type="aisle",
        )
        r = client_logged_in.post(reverse("receiving:location_delete", args=[z.pk]))
        assert r.status_code == 302
        assert WarehouseLocation.objects.filter(pk=z.pk).exists()


# ────────────────────────────
# Putaway views — D-08 + D-09
# ────────────────────────────

@pytest.mark.django_db
class TestPutawayViews:
    def _make_task(self, tenant, grn, po_item, product, bin_loc, user, qty=10, status="in_progress"):
        gi = GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=grn, po_item=po_item, product=product, quantity_received=qty,
        )
        return PutawayTask.objects.create(
            tenant=tenant, grn=grn, grn_item=gi, product=product,
            quantity=qty, suggested_location=bin_loc, assigned_location=bin_loc,
            status=status, assigned_to=user, created_by=user,
        )

    def test_D08_capacity_overflow_rejected(
        self, client_logged_in, tenant, po, po_item, product, user,
    ):
        bin_loc = WarehouseLocation.objects.create(
            tenant=tenant, name="Small", code="SML", location_type="bin",
            capacity=5, current_quantity=0, is_active=True,
        )
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        task = self._make_task(tenant, g, po_item, product, bin_loc, user, qty=10)
        r = client_logged_in.post(
            reverse("receiving:putaway_transition", args=[task.pk, "completed"]),
        )
        assert r.status_code == 302
        task.refresh_from_db()
        bin_loc.refresh_from_db()
        # D-08: completion must NOT have fired when capacity would overflow.
        assert task.status == "in_progress"
        assert bin_loc.current_quantity == 0

    def test_completion_increments_location_qty(
        self, client_logged_in, tenant, po, po_item, product, user,
    ):
        bin_loc = WarehouseLocation.objects.create(
            tenant=tenant, name="Big", code="BIG", location_type="bin",
            capacity=1000, current_quantity=0, is_active=True,
        )
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        task = self._make_task(tenant, g, po_item, product, bin_loc, user, qty=10)
        r = client_logged_in.post(
            reverse("receiving:putaway_transition", args=[task.pk, "completed"]),
        )
        assert r.status_code == 302
        task.refresh_from_db()
        bin_loc.refresh_from_db()
        assert task.status == "completed"
        assert bin_loc.current_quantity == 10

    def test_unlimited_capacity_allows_any_qty(
        self, client_logged_in, tenant, po, po_item, product, user,
    ):
        bin_loc = WarehouseLocation.objects.create(
            tenant=tenant, name="Unltd", code="UNL", location_type="bin",
            capacity=0, current_quantity=0, is_active=True,
        )
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", created_by=user,
        )
        task = self._make_task(tenant, g, po_item, product, bin_loc, user, qty=99999)
        r = client_logged_in.post(
            reverse("receiving:putaway_transition", args=[task.pk, "completed"]),
        )
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == "completed"


# ────────────────────────────
# Inspection views — D-04 formset
# ────────────────────────────

@pytest.mark.django_db
class TestInspectionViews:
    def test_D04_cross_tenant_grn_item_rejected(
        self, client_logged_in, tenant, other_tenant, grn, other_po, other_po_item, other_product, other_user,
    ):
        # GRN in tenant A; tenant A user attempts to bind tenant B's grn_item.
        other_grn = GoodsReceiptNote.objects.create(
            tenant=other_tenant, purchase_order=other_po,
            received_date=date(2026, 1, 1), status="completed", created_by=other_user,
        )
        other_grn_item = GoodsReceiptNoteItem.objects.create(
            tenant=other_tenant, grn=other_grn, po_item=other_po_item,
            product=other_product, quantity_received=1,
        )
        payload = {
            "grn": str(grn.pk),
            "inspector": "",
            "inspection_date": "",
            "notes": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-grn_item": str(other_grn_item.pk),  # foreign tenant
            "items-0-product": "",
            "items-0-quantity_inspected": "1",
            "items-0-quantity_accepted": "1",
            "items-0-quantity_rejected": "0",
            "items-0-quantity_quarantined": "0",
            "items-0-decision": "accepted",
            "items-0-reject_reason": "",
            "items-0-notes": "",
        }
        r = client_logged_in.post(reverse("receiving:inspection_create"), data=payload)
        assert r.status_code == 200
        assert QualityInspection.objects.filter(tenant=tenant).count() == 0


# ────────────────────────────
# Auth — anonymous access blocked
# ────────────────────────────

@pytest.mark.django_db
class TestAuth:
    def test_anonymous_grn_list_redirects(self, client):
        r = client.get(reverse("receiving:grn_list"))
        assert r.status_code in (302, 403)

    def test_anonymous_invoice_list_redirects(self, client):
        r = client.get(reverse("receiving:invoice_list"))
        assert r.status_code in (302, 403)
