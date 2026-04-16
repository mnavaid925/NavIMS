from datetime import date
from decimal import Decimal

import pytest

from receiving.models import (
    GoodsReceiptNote, GoodsReceiptNoteItem, VendorInvoice, ThreeWayMatch,
)


@pytest.mark.django_db
class TestThreeWayMatch:
    def _setup_grn(self, tenant, po, po_item, product, user, qty_received):
        g = GoodsReceiptNote.objects.create(
            tenant=tenant, purchase_order=po, received_date=date(2026, 1, 1),
            status="completed", received_by=user, created_by=user,
        )
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=g, po_item=po_item, product=product,
            quantity_received=qty_received,
        )
        return g

    def test_full_match(self, tenant, po, po_item, product, vendor, user):
        g = self._setup_grn(tenant, po, po_item, product, user, po_item.quantity)
        inv = VendorInvoice.objects.create(
            tenant=tenant, invoice_number="I-FULL", vendor=vendor, purchase_order=po,
            invoice_date=date(2026, 1, 3),
            subtotal=po.subtotal, tax_amount=po.tax_total,
            total_amount=po.grand_total,
        )
        twm = ThreeWayMatch.objects.create(
            tenant=tenant, purchase_order=po, grn=g, vendor_invoice=inv,
        )
        twm.perform_match()
        assert twm.quantity_match is True
        assert twm.price_match is True
        assert twm.total_match is True
        assert twm.status == "matched"

    def test_quantity_mismatch_flags_discrepancy(self, tenant, po, po_item, product, vendor, user):
        g = self._setup_grn(tenant, po, po_item, product, user, po_item.quantity - 2)
        inv = VendorInvoice.objects.create(
            tenant=tenant, invoice_number="I-QTY", vendor=vendor, purchase_order=po,
            invoice_date=date(2026, 1, 3),
            subtotal=po.subtotal, tax_amount=po.tax_total, total_amount=po.grand_total,
        )
        twm = ThreeWayMatch.objects.create(tenant=tenant, purchase_order=po, grn=g, vendor_invoice=inv)
        twm.perform_match()
        assert twm.quantity_match is False
        assert twm.status == "discrepancy"

    def test_D05_invoice_manipulation_attack(self, tenant, po, po_item, product, vendor, user):
        """
        Regression for D-05.

        Attacker receives less than ordered but submits an invoice whose total
        equals the PO grand_total. With the old logic `price_match` compared
        only PO↔Invoice (matched), so `total_match` passed despite a short GRN.
        After the fix GRN total must also be in the comparison.
        """
        # PO: qty=10 @ 5.00 → grand_total 50.00; receive only 5 → GRN total 25.00
        g = self._setup_grn(tenant, po, po_item, product, user, 5)
        inv = VendorInvoice.objects.create(
            tenant=tenant, invoice_number="I-ATTACK", vendor=vendor, purchase_order=po,
            invoice_date=date(2026, 1, 3),
            subtotal=po.subtotal, tax_amount=po.tax_total,
            total_amount=po.grand_total,  # manipulated to equal PO total
        )
        twm = ThreeWayMatch.objects.create(tenant=tenant, purchase_order=po, grn=g, vendor_invoice=inv)
        twm.perform_match()
        assert twm.price_match is False, "GRN total must be part of the price comparison"
        assert twm.status == "discrepancy"

    def test_match_number_auto_generated(self, tenant, po, po_item, product, vendor, user):
        g = self._setup_grn(tenant, po, po_item, product, user, po_item.quantity)
        inv = VendorInvoice.objects.create(
            tenant=tenant, invoice_number="I-N", vendor=vendor, purchase_order=po,
            invoice_date=date(2026, 1, 3),
            subtotal=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"),
        )
        twm = ThreeWayMatch.objects.create(tenant=tenant, purchase_order=po, grn=g, vendor_invoice=inv)
        assert twm.match_number.startswith("TWM-")
