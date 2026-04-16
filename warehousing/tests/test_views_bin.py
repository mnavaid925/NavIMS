"""Integration tests — bin CRUD, occupancy-delete guard, filter retention."""
import pytest
from decimal import Decimal
from django.urls import reverse

from warehousing.models import Bin


@pytest.mark.django_db
class TestBinViews:
    def test_list_renders(self, client_logged_in, bin_obj):
        r = client_logged_in.get(reverse("warehousing:bin_list"))
        assert r.status_code == 200
        assert bin_obj.code.encode() in r.content

    def test_list_filter_by_zone(self, client_logged_in, tenant, zone, bin_obj):
        r = client_logged_in.get(
            reverse("warehousing:bin_list") + f"?zone={zone.pk}"
        )
        assert bin_obj.code.encode() in r.content

    def test_list_filter_by_capacity(self, client_logged_in, bin_obj):
        bin_obj.is_occupied = True
        bin_obj.save()
        r = client_logged_in.get(
            reverse("warehousing:bin_list") + "?capacity=occupied"
        )
        assert bin_obj.code.encode() in r.content

    def test_create_bin(self, client_logged_in, tenant, zone, rack):
        r = client_logged_in.post(reverse("warehousing:bin_create"), {
            "zone": zone.pk, "rack": rack.pk,
            "name": "New Bin", "code": "BIN-NEW",
            "bin_type": "standard",
            "max_weight": "10", "max_volume": "1", "max_quantity": 1,
            "is_active": "on",
        })
        assert r.status_code == 302
        assert Bin.objects.filter(tenant=tenant, code="BIN-NEW").exists()

    def test_delete_occupied_bin_blocked(self, client_logged_in, bin_obj):
        bin_obj.is_occupied = True
        bin_obj.save()
        r = client_logged_in.post(
            reverse("warehousing:bin_delete", args=[bin_obj.pk]), follow=True,
        )
        assert Bin.objects.filter(pk=bin_obj.pk).exists()
        assert b"Cannot delete" in r.content

    def test_delete_bin_with_inventory_blocked(self, client_logged_in, bin_obj):
        """D-11 — delete refuses when current_quantity > 0 even without is_occupied."""
        bin_obj.is_occupied = False
        bin_obj.current_quantity = 5
        bin_obj.save()
        r = client_logged_in.post(
            reverse("warehousing:bin_delete", args=[bin_obj.pk]), follow=True,
        )
        assert Bin.objects.filter(pk=bin_obj.pk).exists()
        assert b"Cannot delete" in r.content

    def test_delete_empty_bin_succeeds(self, client_logged_in, bin_obj):
        bin_obj.is_occupied = False
        bin_obj.current_quantity = 0
        bin_obj.current_weight = Decimal("0")
        bin_obj.current_volume = Decimal("0")
        bin_obj.save()
        r = client_logged_in.post(
            reverse("warehousing:bin_delete", args=[bin_obj.pk])
        )
        assert r.status_code == 302
        assert not Bin.objects.filter(pk=bin_obj.pk).exists()

    def test_bin_list_has_all_choice_badges(self, client_logged_in, tenant, zone):
        """D-05 regression — every BIN_TYPE_CHOICES value renders without the generic fallback."""
        choices = ['standard', 'bulk', 'pick', 'pallet', 'cold', 'hazmat']
        for i, bt in enumerate(choices):
            Bin.objects.create(
                tenant=tenant, zone=zone,
                name=f"B{i}", code=f"BIN-BADGE-{i}",
                bin_type=bt,
            )
        r = client_logged_in.get(reverse("warehousing:bin_list"))
        assert r.status_code == 200
        # The template now has matching branches, so labelled badges appear:
        for label in ["Standard", "Bulk", "Pick", "Pallet", "Cold", "Hazmat"]:
            assert label.encode() in r.content, f"missing {label} badge"
