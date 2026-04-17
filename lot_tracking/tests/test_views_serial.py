"""Integration — serial CRUD, transitions, D-02 edit preservation, D-12 recalled-lot guard."""
import pytest
from django.urls import reverse

from lot_tracking.models import SerialNumber, TraceabilityLog


@pytest.mark.django_db
class TestSerialViews:
    def test_list_renders(self, client_logged_in, serial):
        r = client_logged_in.get(reverse("lot_tracking:serial_list"))
        assert r.status_code == 200
        assert serial.serial_number.encode() in r.content

    def test_create_emits_traceability(
        self, client_logged_in, tenant, product, warehouse, lot,
    ):
        r = client_logged_in.post(reverse("lot_tracking:serial_create"), {
            "serial_number": "SN-NEW", "product": product.pk,
            "lot": lot.pk, "warehouse": warehouse.pk,
            "purchase_date": "", "warranty_expiry": "", "notes": "",
        })
        assert r.status_code == 302
        s = SerialNumber.objects.get(serial_number="SN-NEW")
        assert TraceabilityLog.objects.filter(
            serial_number=s, event_type="received",
        ).exists()

    def test_transition_emits_traceability(self, client_logged_in, serial):
        r = client_logged_in.post(
            reverse("lot_tracking:serial_transition", args=[serial.pk, "sold"]),
        )
        assert r.status_code == 302
        serial.refresh_from_db()
        assert serial.status == "sold"
        assert TraceabilityLog.objects.filter(
            serial_number=serial, event_type="sold",
        ).exists()

    def test_edit_preserves_lot_fk_when_lot_quarantine(
        self, client_logged_in, serial,
    ):
        """D-02 — editing a serial whose lot is non-active must not clear the lot FK."""
        serial.lot.status = "quarantine"
        serial.lot.save()

        r = client_logged_in.post(
            reverse("lot_tracking:serial_edit", args=[serial.pk]),
            {
                "serial_number": serial.serial_number,
                "product": serial.product.pk,
                "lot": serial.lot.pk,
                "warehouse": serial.warehouse.pk,
                "purchase_date": "", "warranty_expiry": "", "notes": "updated",
            },
        )
        assert r.status_code == 302, r.content[:200]
        serial.refresh_from_db()
        assert serial.lot_id is not None  # NOT cleared

    def test_delete_blocks_serial_under_recalled_lot(
        self, client_logged_in, serial,
    ):
        """D-12 — cannot delete a serial whose parent lot is recalled."""
        serial.lot.status = "recalled"
        serial.lot.save()
        r = client_logged_in.post(
            reverse("lot_tracking:serial_delete", args=[serial.pk]), follow=True,
        )
        assert SerialNumber.objects.filter(pk=serial.pk).exists()
        assert b"Cannot delete" in r.content

    def test_delete_available_serial_no_lot(
        self, client_logged_in, tenant, product, warehouse,
    ):
        s = SerialNumber.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            serial_number="SN-FLOAT",
        )
        r = client_logged_in.post(
            reverse("lot_tracking:serial_delete", args=[s.pk])
        )
        assert r.status_code == 302
        assert not SerialNumber.objects.filter(pk=s.pk).exists()

    def test_delete_non_available_blocked(self, client_logged_in, serial):
        serial.status = "allocated"
        serial.save()
        r = client_logged_in.post(
            reverse("lot_tracking:serial_delete", args=[serial.pk]), follow=True,
        )
        assert SerialNumber.objects.filter(pk=serial.pk).exists()
