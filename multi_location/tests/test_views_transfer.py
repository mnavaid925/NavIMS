import pytest
from django.urls import reverse

from multi_location.models import LocationTransferRule


@pytest.mark.django_db
class TestTransferRuleList:
    def test_list_200(self, client_logged_in):
        assert client_logged_in.get(
            reverse("multi_location:transfer_rule_list")
        ).status_code == 200

    @pytest.mark.parametrize("param", ["source", "destination"])
    @pytest.mark.parametrize("value", ["abc", "../../../etc/passwd"])
    def test_non_numeric_filter(self, client_logged_in, param, value):
        """Regression for D-01."""
        r = client_logged_in.get(f"/multi-location/transfer-rules/?{param}={value}")
        assert r.status_code == 200

    def test_filter_by_source(self, client_logged_in, tenant, dc, store):
        rule = LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc, destination_location=store,
        )
        r = client_logged_in.get(f"/multi-location/transfer-rules/?source={dc.pk}")
        assert rule in list(r.context["rules"])

    def test_pagination_retains_filters(self, client_logged_in, tenant, dc, store):
        """Regression for D-10."""
        from multi_location.models import Location
        for i in range(25):
            dst = Location.objects.create(tenant=tenant, name=f"D{i}")
            LocationTransferRule.objects.create(
                tenant=tenant, source_location=dc, destination_location=dst,
            )
        r = client_logged_in.get(
            f"/multi-location/transfer-rules/?source={dc.pk}&allowed=yes"
        )
        assert b"page=2" in r.content
        assert f"source={dc.pk}".encode() in r.content
        assert b"allowed=yes" in r.content


@pytest.mark.django_db
class TestTransferRuleMutations:
    def test_create_success(self, client_logged_in, tenant, dc, store):
        r = client_logged_in.post(
            reverse("multi_location:transfer_rule_create"),
            data={
                'source_location': dc.pk, 'destination_location': store.pk,
                'allowed': 'on', 'max_transfer_qty': 100, 'lead_time_days': 1,
                'requires_approval': '', 'priority': 1,
                'is_active': 'on', 'notes': '',
            },
        )
        assert r.status_code == 302
        assert LocationTransferRule.objects.filter(
            tenant=tenant, source_location=dc, destination_location=store,
        ).count() == 1

    def test_duplicate_source_dest_friendly_error(self, client_logged_in, tenant, dc, store):
        """Regression for D-11: form-layer duplicate guard prevents 500."""
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc, destination_location=store,
        )
        r = client_logged_in.post(
            reverse("multi_location:transfer_rule_create"),
            data={
                'source_location': dc.pk, 'destination_location': store.pk,
                'allowed': 'on', 'max_transfer_qty': 0, 'lead_time_days': 0,
                'requires_approval': '', 'priority': 1,
                'is_active': 'on', 'notes': '',
            },
        )
        assert r.status_code == 200
        assert b'already exists' in r.content
        assert LocationTransferRule.objects.filter(
            tenant=tenant, source_location=dc, destination_location=store,
        ).count() == 1

    def test_non_admin_blocked_from_create(self, staff_client):
        r = staff_client.get(reverse("multi_location:transfer_rule_create"))
        assert r.status_code == 403
