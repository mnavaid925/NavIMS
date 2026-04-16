"""Security tests — OWASP A01 (IDOR, RBAC), A03 (XSS, SQLi), A09 (audit log)."""
import pytest
from django.urls import reverse

from core.models import AuditLog
from warehousing.models import Warehouse, Zone


@pytest.mark.django_db
class TestAuthnAuthz:
    @pytest.mark.parametrize("url_name,args", [
        ("warehousing:warehouse_list", []),
        ("warehousing:warehouse_create", []),
        ("warehousing:zone_list", []),
        ("warehousing:zone_create", []),
        ("warehousing:aisle_list", []),
        ("warehousing:rack_list", []),
        ("warehousing:bin_list", []),
        ("warehousing:crossdock_list", []),
        ("warehousing:crossdock_create", []),
    ])
    def test_login_required(self, client, url_name, args):
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302
        assert "login" in r.url.lower() or "next=" in r.url

    def test_non_admin_blocked_from_create(self, client_non_admin):
        """D-07 — tenant_admin_required gate."""
        r = client_non_admin.post(reverse("warehousing:warehouse_create"), {
            "name": "Sneaky", "warehouse_type": "distribution_center",
            "address": "", "city": "", "state": "", "country": "",
            "postal_code": "", "contact_person": "", "contact_email": "",
            "contact_phone": "", "is_active": "on", "description": "",
        })
        assert r.status_code == 403
        assert not Warehouse.objects.filter(name="Sneaky").exists()

    def test_non_admin_blocked_from_delete(self, client_non_admin, warehouse):
        r = client_non_admin.post(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk])
        )
        assert r.status_code == 403
        assert Warehouse.objects.filter(pk=warehouse.pk).exists()

    def test_non_admin_can_still_read_list(self, client_non_admin):
        r = client_non_admin.get(reverse("warehousing:warehouse_list"))
        assert r.status_code == 200


@pytest.mark.django_db
class TestInjectionAndXSS:
    def test_xss_in_warehouse_name_escaped(self, client_logged_in, tenant):
        Warehouse.objects.create(
            tenant=tenant, name="<script>alert(1)</script>"
        )
        r = client_logged_in.get(reverse("warehousing:warehouse_list"))
        assert b"<script>alert" not in r.content
        assert b"&lt;script&gt;" in r.content

    def test_sql_injection_on_search_safe(self, client_logged_in, tenant):
        Warehouse.objects.create(tenant=tenant, name="Legit")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list") + "?q=' OR 1=1 --"
        )
        assert r.status_code == 200


@pytest.mark.django_db
class TestTenantIsolation:
    def test_cross_tenant_list_isolation(self, client_logged_in, other_tenant):
        Warehouse.objects.create(tenant=other_tenant, name="Secret")
        r = client_logged_in.get(reverse("warehousing:warehouse_list"))
        assert b"Secret" not in r.content

    def test_cross_tenant_detail_404(self, client_logged_in, other_tenant):
        b_wh = Warehouse.objects.create(tenant=other_tenant, name="Hidden")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_detail", args=[b_wh.pk])
        )
        assert r.status_code == 404

    def test_cross_tenant_delete_404(self, client_logged_in, other_tenant):
        b_wh = Warehouse.objects.create(tenant=other_tenant, name="Hidden")
        r = client_logged_in.post(
            reverse("warehousing:warehouse_delete", args=[b_wh.pk])
        )
        assert r.status_code == 404
        assert Warehouse.objects.filter(pk=b_wh.pk).exists()


@pytest.mark.django_db
class TestAuditLog:
    """D-06 regression."""
    def test_audit_on_warehouse_create(self, client_logged_in, tenant):
        client_logged_in.post(reverse("warehousing:warehouse_create"), {
            "name": "Audited", "warehouse_type": "distribution_center",
            "address": "", "city": "", "state": "", "country": "",
            "postal_code": "", "contact_person": "", "contact_email": "",
            "contact_phone": "", "is_active": "on", "description": "",
        })
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="Warehouse", action="create",
        ).exists()

    def test_audit_on_warehouse_delete(self, client_logged_in, warehouse, tenant):
        client_logged_in.post(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk])
        )
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="Warehouse", action="delete",
        ).exists()

    def test_audit_on_crossdock_transition(self, client_logged_in, crossdock, tenant):
        client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "in_transit"},
        )
        assert AuditLog.objects.filter(
            tenant=tenant, model_name="CrossDockOrder", action="transition",
        ).exists()
