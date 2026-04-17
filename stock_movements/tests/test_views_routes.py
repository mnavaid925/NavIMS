import pytest
from django.urls import reverse

from stock_movements.models import TransferRoute


@pytest.mark.django_db
class TestRouteCRUD:
    def test_create_happy(self, client_logged_in, tenant, w1, w2):
        r = client_logged_in.post(
            reverse("stock_movements:route_create"),
            data={
                "name": "R1", "source_warehouse": str(w1.pk),
                "destination_warehouse": str(w2.pk),
                "transit_method": "truck", "estimated_duration_hours": "4",
                "distance_km": "50.5", "instructions": "go", "is_active": True,
            },
        )
        assert r.status_code == 302
        assert TransferRoute.objects.filter(tenant=tenant, name="R1").exists()

    def test_create_src_eq_dest_blocked(self, client_logged_in, tenant, w1):
        r = client_logged_in.post(
            reverse("stock_movements:route_create"),
            data={
                "name": "Bad", "source_warehouse": str(w1.pk),
                "destination_warehouse": str(w1.pk),
                "transit_method": "truck", "estimated_duration_hours": "1",
                "distance_km": "1", "instructions": "", "is_active": True,
            },
        )
        assert r.status_code == 200
        assert not TransferRoute.objects.filter(tenant=tenant, name="Bad").exists()

    def test_cross_tenant_route_detail_404(
        self, client_logged_in, other_tenant, other_warehouse,
    ):
        r2 = TransferRoute.objects.create(
            tenant=other_tenant, name="ForeignRoute",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            transit_method="truck", estimated_duration_hours=1,
        )
        r = client_logged_in.get(reverse("stock_movements:route_detail", args=[r2.pk]))
        assert r.status_code == 404

    def test_route_detail_lists_related_transfers(
        self, client_logged_in, tenant, w1, w2, user,
    ):
        from stock_movements.models import StockTransfer
        route = TransferRoute.objects.create(
            tenant=tenant, name="R", source_warehouse=w1, destination_warehouse=w2,
            transit_method="truck", estimated_duration_hours=1,
        )
        for _ in range(3):
            StockTransfer.objects.create(
                tenant=tenant, transfer_type="inter_warehouse",
                source_warehouse=w1, destination_warehouse=w2, requested_by=user,
            )
        r = client_logged_in.get(reverse("stock_movements:route_detail", args=[route.pk]))
        assert r.status_code == 200
        assert r.context["related_transfers"].count() == 3

    def test_route_delete(self, client_logged_in, tenant, w1, w2):
        route = TransferRoute.objects.create(
            tenant=tenant, name="ToDel", source_warehouse=w1, destination_warehouse=w2,
            transit_method="truck", estimated_duration_hours=1,
        )
        r = client_logged_in.post(
            reverse("stock_movements:route_delete", args=[route.pk]),
        )
        assert r.status_code == 302
        assert not TransferRoute.objects.filter(pk=route.pk).exists()
