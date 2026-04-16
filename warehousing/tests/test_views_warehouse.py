"""Integration tests — warehouse CRUD, filters, IDOR."""
import pytest
from django.urls import reverse

from warehousing.models import Warehouse


@pytest.mark.django_db
class TestWarehouseViews:
    def test_list_requires_login(self, client):
        r = client.get(reverse("warehousing:warehouse_list"))
        assert r.status_code == 302

    def test_list_returns_only_tenant_warehouses(
        self, client_logged_in, tenant, other_tenant
    ):
        Warehouse.objects.create(tenant=tenant, name="Mine")
        Warehouse.objects.create(tenant=other_tenant, name="Secret")
        r = client_logged_in.get(reverse("warehousing:warehouse_list"))
        assert b"Mine" in r.content
        assert b"Secret" not in r.content

    def test_list_search_by_name(self, client_logged_in, tenant):
        Warehouse.objects.create(tenant=tenant, name="Alpha DC")
        Warehouse.objects.create(tenant=tenant, name="Beta Cold")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list") + "?q=Alpha"
        )
        assert b"Alpha DC" in r.content
        assert b"Beta Cold" not in r.content

    def test_list_filter_type(self, client_logged_in, tenant):
        Warehouse.objects.create(tenant=tenant, name="DC", warehouse_type="distribution_center")
        Warehouse.objects.create(tenant=tenant, name="Cold", warehouse_type="cold_storage")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list") + "?type=cold_storage"
        )
        assert b"Cold" in r.content
        assert b"DC" not in r.content

    def test_list_filter_active(self, client_logged_in, tenant):
        Warehouse.objects.create(tenant=tenant, name="Live", is_active=True)
        Warehouse.objects.create(tenant=tenant, name="Dead", is_active=False)
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list") + "?active=inactive"
        )
        assert b"Dead" in r.content
        assert b"Live" not in r.content

    def test_filter_retention_through_pagination(self, client_logged_in, tenant):
        for i in range(25):
            Warehouse.objects.create(
                tenant=tenant, name=f"W{i}",
                warehouse_type="distribution_center",
            )
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list")
            + "?type=distribution_center&active=active&page=2"
        )
        assert r.status_code == 200
        assert b"type=distribution_center" in r.content
        assert b"active=active" in r.content

    def test_create_view_get(self, client_logged_in):
        r = client_logged_in.get(reverse("warehousing:warehouse_create"))
        assert r.status_code == 200

    def test_create_warehouse_post(self, client_logged_in, tenant):
        r = client_logged_in.post(reverse("warehousing:warehouse_create"), {
            "name": "New DC", "warehouse_type": "distribution_center",
            "address": "", "city": "", "state": "", "country": "",
            "postal_code": "", "contact_person": "", "contact_email": "",
            "contact_phone": "", "is_active": "on", "description": "",
        })
        assert r.status_code == 302
        assert Warehouse.objects.filter(tenant=tenant, name="New DC").exists()

    def test_detail_renders(self, client_logged_in, warehouse):
        r = client_logged_in.get(
            reverse("warehousing:warehouse_detail", args=[warehouse.pk])
        )
        assert r.status_code == 200
        assert warehouse.name.encode() in r.content

    def test_idor_cross_tenant_detail(self, client_logged_in, other_tenant):
        b_wh = Warehouse.objects.create(tenant=other_tenant, name="Hidden")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_detail", args=[b_wh.pk])
        )
        assert r.status_code == 404

    def test_delete_non_empty_blocked(self, client_logged_in, warehouse, zone):
        r = client_logged_in.post(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk]),
            follow=True,
        )
        assert Warehouse.objects.filter(pk=warehouse.pk).exists()
        assert b"Cannot delete" in r.content

    def test_delete_empty_succeeds(self, client_logged_in, warehouse):
        r = client_logged_in.post(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk])
        )
        assert r.status_code == 302
        assert not Warehouse.objects.filter(pk=warehouse.pk).exists()

    def test_delete_get_is_no_op(self, client_logged_in, warehouse):
        r = client_logged_in.get(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk])
        )
        assert r.status_code == 302
        assert Warehouse.objects.filter(pk=warehouse.pk).exists()

    def test_warehouse_map_renders(self, client_logged_in, warehouse, bin_obj):
        r = client_logged_in.get(
            reverse("warehousing:warehouse_map", args=[warehouse.pk])
        )
        assert r.status_code == 200
