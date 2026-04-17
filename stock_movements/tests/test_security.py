"""OWASP-aligned tests for the stock_movements module."""
import pytest
from django.urls import reverse

from stock_movements.models import (
    StockTransfer, TransferRoute, TransferApprovalRule,
)


@pytest.mark.django_db
class TestA01BrokenAccessControl:
    def test_anonymous_transfer_list_redirects(self, client):
        r = client.get(reverse("stock_movements:transfer_list"))
        assert r.status_code in (302, 403)

    def test_anonymous_route_list_redirects(self, client):
        r = client.get(reverse("stock_movements:route_list"))
        assert r.status_code in (302, 403)

    def test_cross_tenant_transfer_detail_404(
        self, client_logged_in, other_tenant, other_warehouse, other_user,
    ):
        t = StockTransfer.objects.create(
            tenant=other_tenant, transfer_type="intra_warehouse",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            requested_by=other_user,
        )
        r = client_logged_in.get(
            reverse("stock_movements:transfer_detail", args=[t.pk]),
        )
        assert r.status_code == 404

    def test_cross_tenant_route_edit_404(
        self, client_logged_in, other_tenant, other_warehouse,
    ):
        r2 = TransferRoute.objects.create(
            tenant=other_tenant, name="Foreign",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            transit_method="truck", estimated_duration_hours=1,
        )
        r = client_logged_in.get(
            reverse("stock_movements:route_edit", args=[r2.pk]),
        )
        assert r.status_code == 404

    def test_cross_tenant_approval_rule_edit_404(
        self, client_logged_in, other_tenant,
    ):
        rule = TransferApprovalRule.objects.create(
            tenant=other_tenant, name="X", min_items=0, max_items=5,
            requires_approval=True, is_active=True,
        )
        r = client_logged_in.get(
            reverse("stock_movements:approval_rule_edit", args=[rule.pk]),
        )
        assert r.status_code == 404


@pytest.mark.django_db
class TestA01SegregationOfDuties:
    def test_requester_cannot_self_approve(
        self, client_logged_in, tenant, w1, w2, user,
    ):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="pending_approval", requested_by=user,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_approve", args=[t.pk]),
            data={"decision": "approved", "comments": ""},
        )
        t.refresh_from_db()
        assert t.status == "pending_approval"


@pytest.mark.django_db
class TestA01CrossTenantPayloadInjection:
    def test_foreign_product_on_create_rejected(
        self, client_logged_in, tenant, w1, w2, other_product,
    ):
        r = client_logged_in.post(
            reverse("stock_movements:transfer_create"),
            data={
                "transfer_type": "inter_warehouse",
                "source_warehouse": str(w1.pk),
                "destination_warehouse": str(w2.pk),
                "priority": "normal", "notes": "",
                "item_product": [str(other_product.pk)],
                "item_quantity": ["5"],
                "item_notes": [""],
            },
        )
        assert r.status_code == 200
        assert StockTransfer.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
class TestA03XssEscape:
    def test_notes_escaped_on_transfer_detail(
        self, client_logged_in, tenant, w1, w2, user,
    ):
        payload = "<script>alert('x')</script>"
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            notes=payload, requested_by=user,
        )
        r = client_logged_in.get(
            reverse("stock_movements:transfer_detail", args=[t.pk]),
        )
        assert r.status_code == 200
        assert payload.encode() not in r.content
        assert b"&lt;script&gt;" in r.content

    def test_instructions_escaped_on_route_detail(
        self, client_logged_in, tenant, w1, w2,
    ):
        payload = "<script>alert(42)</script>"
        route = TransferRoute.objects.create(
            tenant=tenant, name="R", source_warehouse=w1, destination_warehouse=w2,
            transit_method="truck", estimated_duration_hours=1,
            instructions=payload,
        )
        r = client_logged_in.get(
            reverse("stock_movements:route_detail", args=[route.pk]),
        )
        assert r.status_code == 200
        assert payload.encode() not in r.content
        assert b"&lt;script&gt;" in r.content
