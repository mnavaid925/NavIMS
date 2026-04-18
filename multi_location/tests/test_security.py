import pytest
from django.urls import reverse

from multi_location.models import (
    Location, LocationPricingRule, LocationSafetyStockRule, LocationTransferRule,
)


@pytest.mark.django_db
class TestAuthGates:
    def test_anonymous_redirected_to_login(self, client, tenant):
        r = client.get(reverse("multi_location:location_list"))
        assert r.status_code in (302, 301)

    def test_superuser_no_tenant_list_200(self, client, db):
        """Superuser with tenant=None must not 500 on any list page."""
        from django.contrib.auth import get_user_model
        U = get_user_model()
        su = U.objects.create_user("su", password="x", tenant=None, is_superuser=True)
        client.force_login(su)
        for url in [
            "/multi-location/",
            "/multi-location/pricing-rules/",
            "/multi-location/transfer-rules/",
            "/multi-location/safety-stock-rules/",
            "/multi-location/stock-visibility/",
        ]:
            r = client.get(url)
            assert r.status_code == 200, f"{url} returned {r.status_code}"


@pytest.mark.django_db
class TestXSSAutoescape:
    def test_location_name_script_tag_escaped(self, client_logged_in, tenant):
        Location.objects.create(tenant=tenant, name='<script>alert(1)</script>')
        r = client_logged_in.get(reverse("multi_location:location_list"))
        assert b'<script>alert(1)</script>' not in r.content
        assert b'&lt;script&gt;' in r.content


@pytest.mark.django_db
class TestIDOR:
    def test_cross_tenant_location_detail_404(self, client_logged_in, other_location):
        r = client_logged_in.get(
            reverse("multi_location:location_detail", args=[other_location.pk])
        )
        assert r.status_code == 404

    def test_cross_tenant_pricing_rule_404(self, client_logged_in, other_tenant, other_location):
        rule = LocationPricingRule.objects.create(
            tenant=other_tenant, location=other_location,
            rule_type="markup_pct", value=5,
        )
        assert client_logged_in.get(
            reverse("multi_location:pricing_rule_detail", args=[rule.pk])
        ).status_code == 404
        assert client_logged_in.post(
            reverse("multi_location:pricing_rule_delete", args=[rule.pk])
        ).status_code == 404

    def test_cross_tenant_transfer_rule_404(self, client_logged_in, other_tenant, other_location):
        other2 = Location.objects.create(tenant=other_tenant, name="F2")
        rule = LocationTransferRule.objects.create(
            tenant=other_tenant, source_location=other_location, destination_location=other2,
        )
        assert client_logged_in.get(
            reverse("multi_location:transfer_rule_detail", args=[rule.pk])
        ).status_code == 404

    def test_cross_tenant_safety_stock_404(self, client_logged_in, other_tenant, other_location, other_product):
        rule = LocationSafetyStockRule.objects.create(
            tenant=other_tenant, location=other_location, product=other_product,
            safety_stock_qty=1, reorder_point=2,
        )
        assert client_logged_in.get(
            reverse("multi_location:safety_stock_rule_detail", args=[rule.pk])
        ).status_code == 404


@pytest.mark.django_db
class TestInputValidation:
    """D-01 master sweep: every list FK filter rejects non-numeric input."""

    @pytest.mark.parametrize("url", [
        "/multi-location/?parent=abc",
        "/multi-location/pricing-rules/?location=abc",
        "/multi-location/transfer-rules/?source=abc",
        "/multi-location/transfer-rules/?destination=abc",
        "/multi-location/safety-stock-rules/?location=abc",
        "/multi-location/safety-stock-rules/?product=abc",
        "/multi-location/stock-visibility/?location=abc",
    ])
    def test_non_numeric_does_not_500(self, client_logged_in, url):
        r = client_logged_in.get(url)
        assert r.status_code == 200


@pytest.mark.django_db
class TestCSRF:
    def test_delete_without_csrf_rejected(self, admin_user, tenant, client):
        client.force_login(admin_user)
        loc = Location.objects.create(tenant=tenant, name="X")
        client.handler.enforce_csrf_checks = True
        r = client.post(reverse("multi_location:location_delete", args=[loc.pk]))
        assert r.status_code == 403
        assert Location.objects.filter(pk=loc.pk).exists()


@pytest.mark.django_db
class TestRBAC:
    """D-13: destructive views gated on is_tenant_admin."""

    @pytest.mark.parametrize("route,kwargs_factory", [
        ("multi_location:location_create", lambda f: {}),
        ("multi_location:pricing_rule_create", lambda f: {}),
        ("multi_location:transfer_rule_create", lambda f: {}),
        ("multi_location:safety_stock_rule_create", lambda f: {}),
    ])
    def test_create_endpoints_require_tenant_admin(self, staff_client, route, kwargs_factory):
        r = staff_client.get(reverse(route, **kwargs_factory(None)))
        assert r.status_code == 403
