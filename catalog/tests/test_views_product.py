"""View / integration tests for Product CRUD.

Covers:
- TC-PROD-001 create happy path
- TC-PROD-003 duplicate SKU rejection
- TC-PROD-017 filter retention
- TC-PROD-011 unknown status query param ignored
"""
import pytest
from django.urls import reverse

from catalog.models import Product


def _formset_empties(prefix="attributes"):
    return {
        f"{prefix}-TOTAL_FORMS": "0",
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


@pytest.mark.django_db
class TestProductCreate:
    def test_list_requires_login(self, client):
        r = client.get(reverse("catalog:product_list"))
        assert r.status_code == 302
        assert "/login" in r.url or "login" in r.url

    def test_create_product_happy_path(self, client_logged_in, tenant, category):
        payload = {
            "sku": "NEW-001",
            "name": "Test Widget",
            "status": "active",
            "category": category.pk,
            "purchase_cost": "10.00",
            "retail_price": "15.00",
            "wholesale_price": "12.00",
            "markup_percentage": "",
            "is_active": "on",
            **_formset_empties(),
        }
        r = client_logged_in.post(reverse("catalog:product_create"), data=payload)
        assert r.status_code == 302
        product = Product.objects.get(tenant=tenant, sku="NEW-001")
        assert product.name == "Test Widget"
        # Auto-computed markup (D-04 blank path)
        assert product.markup_percentage == 50

    def test_duplicate_sku_same_tenant_rejected(self, client_logged_in, product):
        payload = {
            "sku": product.sku,
            "name": "Clash",
            "status": "draft",
            "purchase_cost": "1.00",
            "retail_price": "2.00",
            "wholesale_price": "0",
            "markup_percentage": "0",
            "is_active": "on",
            **_formset_empties(),
        }
        r = client_logged_in.post(reverse("catalog:product_create"), data=payload)
        # Form redisplay (200) means the validation blocked the save.
        assert r.status_code == 200
        assert Product.objects.filter(sku=product.sku).count() == 1


@pytest.mark.django_db
class TestProductListFilters:
    def test_invalid_status_filter_ignored(self, client_logged_in, product):
        r = client_logged_in.get(
            reverse("catalog:product_list") + "?status=__EVIL__"
        )
        assert r.status_code == 200
        assert product.name.encode() in r.content

    def test_search_by_sku(self, client_logged_in, tenant, category):
        Product.objects.create(
            tenant=tenant, sku="ALPHA-1", name="Alpha Thing",
            category=category, status="active",
        )
        Product.objects.create(
            tenant=tenant, sku="BETA-1", name="Beta Thing",
            category=category, status="active",
        )
        r = client_logged_in.get(reverse("catalog:product_list") + "?q=ALPHA")
        assert r.status_code == 200
        assert b"Alpha Thing" in r.content
        assert b"Beta Thing" not in r.content


@pytest.mark.django_db
class TestProductDelete:
    def test_delete_requires_post(self, client_logged_in, product):
        r = client_logged_in.get(
            reverse("catalog:product_delete", args=[product.pk])
        )
        assert r.status_code == 302  # redirects, no-op on GET
        assert Product.objects.filter(pk=product.pk).exists()

    def test_delete_cascades_to_attributes(self, client_logged_in, product, tenant):
        from catalog.models import ProductAttribute
        ProductAttribute.objects.create(
            tenant=tenant, product=product, name="Color", value="Black",
        )
        r = client_logged_in.post(
            reverse("catalog:product_delete", args=[product.pk])
        )
        assert r.status_code == 302
        assert not Product.objects.filter(pk=product.pk).exists()
        assert ProductAttribute.objects.filter(product=product).count() == 0
