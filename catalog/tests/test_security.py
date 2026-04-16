"""Security tests — OWASP-aligned.

Covers:
- TC-SEC-001 Auth required on every catalog URL
- TC-SEC-002 Cross-tenant IDOR → 404
- TC-SEC-004 Stored XSS escaped on render
- TC-SEC-005 Query-tampering / SQLi safe (via ORM)
- TC-SEC-011 CSRF enforced on destructive POSTs
"""
import pytest
from django.test import Client
from django.urls import reverse

from catalog.models import Category, Product


CATALOG_URLS = [
    ("catalog:category_list", []),
    ("catalog:category_create", []),
    ("catalog:product_list", []),
    ("catalog:product_create", []),
]


@pytest.mark.django_db
class TestAuthRequired:
    @pytest.mark.parametrize("name,args", CATALOG_URLS)
    def test_unauthenticated_redirects_to_login(self, client, name, args):
        r = client.get(reverse(name, args=args))
        assert r.status_code == 302
        # Django default login redirect
        assert "login" in r.url.lower()


@pytest.mark.django_db
class TestCrossTenantIDOR:
    def test_cannot_view_other_tenant_product(
        self, client_logged_in, other_tenant,
    ):
        foreign = Product.objects.create(
            tenant=other_tenant, sku="X-1", name="Foreign", status="active",
        )
        r = client_logged_in.get(
            reverse("catalog:product_detail", args=[foreign.pk])
        )
        assert r.status_code == 404

    def test_cannot_delete_other_tenant_product(
        self, client_logged_in, other_tenant,
    ):
        foreign = Product.objects.create(
            tenant=other_tenant, sku="X-2", name="Foreign", status="active",
        )
        r = client_logged_in.post(
            reverse("catalog:product_delete", args=[foreign.pk])
        )
        assert r.status_code == 404
        assert Product.objects.filter(pk=foreign.pk).exists()

    def test_cannot_view_other_tenant_category(
        self, client_logged_in, other_tenant,
    ):
        foreign = Category.objects.create(
            tenant=other_tenant, name="Foreign Category",
        )
        r = client_logged_in.get(
            reverse("catalog:category_detail", args=[foreign.pk])
        )
        assert r.status_code == 404


@pytest.mark.django_db
class TestXSSAndInjection:
    def test_xss_in_product_name_is_escaped(
        self, client_logged_in, tenant, category,
    ):
        Product.objects.create(
            tenant=tenant,
            sku="XSS-1",
            name="<script>alert(1)</script>",
            category=category,
            status="active",
        )
        r = client_logged_in.get(reverse("catalog:product_list"))
        assert r.status_code == 200
        assert b"<script>alert(1)</script>" not in r.content
        assert b"&lt;script&gt;" in r.content

    def test_sqli_in_search_query_safe(
        self, client_logged_in, tenant, category,
    ):
        Product.objects.create(
            tenant=tenant, sku="SAFE-1", name="Safe Product",
            category=category, status="active",
        )
        # A classic SQLi attempt — Django ORM parameterises the query.
        r = client_logged_in.get(
            reverse("catalog:product_list") + "?q=' OR 1=1 --"
        )
        assert r.status_code == 200


@pytest.mark.django_db
class TestCSRFEnforcement:
    def test_delete_without_csrf_returns_403(self, user, product):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        r = csrf_client.post(
            reverse("catalog:product_delete", args=[product.pk])
        )
        assert r.status_code == 403
        assert Product.objects.filter(pk=product.pk).exists()
