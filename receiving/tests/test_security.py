"""OWASP Top-10-aligned tests for the receiving module."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from receiving.models import (
    GoodsReceiptNote, VendorInvoice, WarehouseLocation,
)


@pytest.mark.django_db
class TestA01BrokenAccessControl:
    def test_grn_detail_cross_tenant_404(self, client, user, other_tenant, other_po, other_user):
        g = GoodsReceiptNote.objects.create(
            tenant=other_tenant, purchase_order=other_po,
            received_date=date(2026, 1, 1), created_by=other_user,
        )
        client.force_login(user)
        assert client.get(reverse("receiving:grn_detail", args=[g.pk])).status_code == 404

    def test_location_edit_cross_tenant_404(self, client, user, other_tenant):
        loc = WarehouseLocation.objects.create(
            tenant=other_tenant, name="X", code="X", location_type="bin",
        )
        client.force_login(user)
        assert client.get(reverse("receiving:location_edit", args=[loc.pk])).status_code == 404

    def test_invoice_delete_cross_tenant_404(self, client, user, other_tenant, other_vendor, other_po):
        inv = VendorInvoice.objects.create(
            tenant=other_tenant, invoice_number="A1", vendor=other_vendor,
            purchase_order=other_po, invoice_date=date(2026, 1, 1),
            subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
        )
        client.force_login(user)
        r = client.post(reverse("receiving:invoice_delete", args=[inv.pk]))
        assert r.status_code == 404

    def test_transition_non_post_redirects(self, client_logged_in, grn):
        r = client_logged_in.get(reverse("receiving:grn_transition", args=[grn.pk, "completed"]))
        assert r.status_code == 302


@pytest.mark.django_db
class TestA03XssEscape:
    def test_invoice_notes_escaped_on_detail(self, client_logged_in, tenant, vendor, po):
        payload = "<script>alert('x')</script>"
        inv = VendorInvoice.objects.create(
            tenant=tenant, invoice_number="XSS1", vendor=vendor, purchase_order=po,
            invoice_date=date(2026, 1, 1),
            subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
            notes=payload,
        )
        r = client_logged_in.get(reverse("receiving:invoice_detail", args=[inv.pk]))
        assert r.status_code == 200
        assert payload.encode() not in r.content
        assert b"&lt;script&gt;" in r.content


@pytest.mark.django_db
class TestA08FileUpload:
    def _payload(self, vendor, po, number):
        return {
            "invoice_number": number, "vendor": str(vendor.pk), "purchase_order": str(po.pk),
            "invoice_date": "2026-01-01", "due_date": "",
            "subtotal": "0", "tax_amount": "0", "total_amount": "0", "notes": "",
        }

    @pytest.mark.parametrize("name,content_type", [
        ("evil.exe", "application/x-msdownload"),
        ("evil.php", "application/x-php"),
        ("evil.sh", "application/x-sh"),
        ("evil.bat", "application/octet-stream"),
        ("evil.ps1", "application/octet-stream"),
    ])
    def test_dangerous_extensions_blocked(
        self, client_logged_in, tenant, vendor, po, name, content_type,
    ):
        payload = SimpleUploadedFile(name, b"content", content_type=content_type)
        r = client_logged_in.post(
            reverse("receiving:invoice_create"),
            data={**self._payload(vendor, po, f"X-{name}"), "document": payload},
        )
        assert r.status_code == 200
        assert not VendorInvoice.objects.filter(invoice_number=f"X-{name}").exists()

    def test_svg_blocked(self, client_logged_in, tenant, vendor, po):
        svg = SimpleUploadedFile(
            "x.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type="image/svg+xml",
        )
        r = client_logged_in.post(
            reverse("receiving:invoice_create"),
            data={**self._payload(vendor, po, "SVG-1"), "document": svg},
        )
        assert r.status_code == 200
        assert not VendorInvoice.objects.filter(invoice_number="SVG-1").exists()


@pytest.mark.django_db
class TestA04InsecureDesign:
    def test_invoice_total_mismatch_rejected(self, client_logged_in, vendor, po):
        data = {
            "invoice_number": "DESIGN-1", "vendor": str(vendor.pk),
            "purchase_order": str(po.pk), "invoice_date": "2026-01-01", "due_date": "",
            "subtotal": "100.00", "tax_amount": "10.00", "total_amount": "500.00",
            "notes": "",
        }
        r = client_logged_in.post(reverse("receiving:invoice_create"), data=data)
        assert r.status_code == 200
        assert not VendorInvoice.objects.filter(invoice_number="DESIGN-1").exists()
