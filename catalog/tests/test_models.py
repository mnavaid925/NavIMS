"""Unit tests for catalog model logic.

Covers: TC-CAT-001/002/003 hierarchy rules, slug regeneration,
TC-IMG-006 primary-image invariant, full_path computation.
"""
import pytest

from catalog.models import Category, Product, ProductImage


@pytest.mark.django_db
class TestCategoryHierarchy:
    def test_department_level_auto_set(self, tenant):
        cat = Category.objects.create(tenant=tenant, name="Apparel")
        assert cat.level == "department"
        assert cat.slug == "apparel"

    def test_category_level_under_department(self, tenant, department):
        cat = Category.objects.create(
            tenant=tenant, name="Laptops", parent=department,
        )
        assert cat.level == "category"

    def test_subcategory_level_under_category(self, tenant, category):
        sub = Category.objects.create(
            tenant=tenant, name="Gaming", parent=category,
        )
        assert sub.level == "subcategory"

    def test_full_path_includes_all_ancestors(self, tenant, category):
        sub = Category.objects.create(
            tenant=tenant, name="Gaming", parent=category,
        )
        assert sub.full_path == "Electronics > Laptops > Gaming"

    def test_slug_regenerated_on_rename(self, tenant):
        c = Category.objects.create(tenant=tenant, name="Old Name")
        c.name = "New Name"
        c.save()
        assert c.slug == "new-name"


@pytest.mark.django_db
class TestPrimaryImageInvariant:
    """TC-IMG-006 — only one primary image per product at a time."""

    def test_new_primary_demotes_existing_primary(self, product, tenant):
        img1 = ProductImage.objects.create(
            tenant=tenant, product=product, image="a.jpg", is_primary=True,
        )
        img2 = ProductImage.objects.create(
            tenant=tenant, product=product, image="b.jpg", is_primary=True,
        )
        img1.refresh_from_db()
        assert img1.is_primary is False
        assert img2.is_primary is True

    def test_primary_image_property(self, product, tenant):
        ProductImage.objects.create(
            tenant=tenant, product=product, image="a.jpg", is_primary=False,
        )
        primary = ProductImage.objects.create(
            tenant=tenant, product=product, image="b.jpg", is_primary=True,
        )
        assert product.primary_image.pk == primary.pk


@pytest.mark.django_db
class TestProductDefaults:
    def test_sku_unique_per_tenant_not_global(self, tenant, other_tenant):
        Product.objects.create(tenant=tenant, sku="SHARED", name="A")
        # Same SKU in different tenant must be allowed
        Product.objects.create(tenant=other_tenant, sku="SHARED", name="B")
        assert Product.objects.filter(sku="SHARED").count() == 2
