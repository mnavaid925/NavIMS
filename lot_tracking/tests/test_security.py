"""Security — OWASP A01 (anon, IDOR, RBAC), A03 (XSS, SQLi), A09 (AuditLog)."""
import pytest
from django.urls import reverse

from core.models import AuditLog
from lot_tracking.models import LotBatch


@pytest.mark.django_db
class TestAuthn:
    @pytest.mark.parametrize("name,args", [
        ("lot_tracking:lot_list", []),
        ("lot_tracking:lot_create", []),
        ("lot_tracking:serial_list", []),
        ("lot_tracking:serial_create", []),
        ("lot_tracking:expiry_dashboard", []),
        ("lot_tracking:expiry_alert_list", []),
        ("lot_tracking:traceability_list", []),
        ("lot_tracking:traceability_create", []),
    ])
    def test_login_required(self, client, name, args):
        r = client.get(reverse(name, args=args))
        assert r.status_code == 302


@pytest.mark.django_db
class TestRBAC:
    """D-05 — non-admin tenant user must be blocked from destructive endpoints."""
    def test_non_admin_blocked_from_lot_delete(self, client_non_admin, lot):
        lot.status = "quarantine"
        lot.save()
        r = client_non_admin.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert r.status_code == 403
        assert LotBatch.objects.filter(pk=lot.pk).exists()

    def test_non_admin_blocked_from_transition(self, client_non_admin, lot):
        r = client_non_admin.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "recalled"])
        )
        assert r.status_code == 403
        lot.refresh_from_db()
        assert lot.status == "active"

    def test_non_admin_blocked_from_lot_create(
        self, client_non_admin, product, warehouse,
    ):
        r = client_non_admin.post(reverse("lot_tracking:lot_create"), {
            "product": product.pk, "warehouse": warehouse.pk, "grn": "",
            "quantity": 10,
            "manufacturing_date": "", "expiry_date": "",
            "supplier_batch_number": "", "notes": "",
        })
        assert r.status_code == 403

    def test_non_admin_can_still_read_list(self, client_non_admin):
        r = client_non_admin.get(reverse("lot_tracking:lot_list"))
        assert r.status_code == 200


@pytest.mark.django_db
class TestXSSAndSQLi:
    def test_xss_in_lot_notes_escaped(
        self, client_logged_in, tenant, product, warehouse,
    ):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, notes="<script>alert(1)</script>",
        )
        r = client_logged_in.get(
            reverse("lot_tracking:lot_detail", args=[lot.pk])
        )
        assert b"<script>alert" not in r.content
        assert b"&lt;script&gt;" in r.content

    def test_sql_injection_on_search(self, client_logged_in):
        r = client_logged_in.get(
            reverse("lot_tracking:lot_list") + "?q=' OR 1=1 --"
        )
        assert r.status_code == 200


@pytest.mark.django_db
class TestTenantIsolation:
    def test_cross_tenant_list_isolation(
        self, client_logged_in, other_tenant,
    ):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        LotBatch.objects.create(
            tenant=other_tenant, product=p2, warehouse=w2,
            quantity=1, lot_number="LOT-SECRET",
        )
        r = client_logged_in.get(reverse("lot_tracking:lot_list"))
        assert b"LOT-SECRET" not in r.content


@pytest.mark.django_db
class TestAuditLog:
    """D-06 regression."""
    def test_audit_on_lot_create(
        self, client_logged_in, tenant, product, warehouse,
    ):
        client_logged_in.post(reverse("lot_tracking:lot_create"), {
            "product": product.pk, "warehouse": warehouse.pk, "grn": "",
            "quantity": 10,
            "manufacturing_date": "", "expiry_date": "",
            "supplier_batch_number": "", "notes": "",
        })
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="LotBatch", action="create",
        ).exists()

    def test_audit_on_lot_delete(self, client_logged_in, lot, tenant):
        lot.status = "quarantine"
        lot.save()
        client_logged_in.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="LotBatch", action="delete",
        ).exists()

    def test_audit_on_lot_transition(self, client_logged_in, lot, tenant):
        client_logged_in.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "recalled"])
        )
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="LotBatch", action="transition",
        ).exists()

    def test_audit_on_serial_transition(self, client_logged_in, serial, tenant):
        client_logged_in.post(
            reverse("lot_tracking:serial_transition", args=[serial.pk, "sold"])
        )
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="SerialNumber", action="transition",
        ).exists()
