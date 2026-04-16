"""Performance tests — N+1 guards on list + map views."""
import pytest
from decimal import Decimal
from django.urls import reverse

from warehousing.models import Warehouse, Zone, Bin


@pytest.mark.django_db
class TestPerformance:
    def test_bin_list_no_n_plus_one(
        self, client_logged_in, tenant, django_assert_max_num_queries,
    ):
        wh = Warehouse.objects.create(tenant=tenant, name="A")
        z = Zone.objects.create(
            tenant=tenant, warehouse=wh, name="Z", code="Z-PERF",
            zone_type="storage",
        )
        for i in range(50):
            Bin.objects.create(
                tenant=tenant, zone=z, name=f"B{i}", code=f"BIN-PERF-{i:04d}",
                bin_type="standard",
                max_weight=Decimal("100"),
                max_volume=Decimal("1"),
                max_quantity=10,
            )
        with django_assert_max_num_queries(15):
            r = client_logged_in.get(reverse("warehousing:bin_list"))
        assert r.status_code == 200

    def test_warehouse_map_query_budget(
        self, client_logged_in, warehouse, bin_obj, django_assert_max_num_queries,
    ):
        with django_assert_max_num_queries(20):
            r = client_logged_in.get(
                reverse("warehousing:warehouse_map", args=[warehouse.pk])
            )
        assert r.status_code == 200
