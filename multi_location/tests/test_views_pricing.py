import pytest
from django.urls import reverse

from multi_location.models import LocationPricingRule


@pytest.mark.django_db
class TestPricingRuleList:
    def test_list_200(self, client_logged_in):
        assert client_logged_in.get(
            reverse("multi_location:pricing_rule_list")
        ).status_code == 200

    def test_filter_by_location(self, client_logged_in, tenant, store, dc, product):
        LocationPricingRule.objects.create(
            tenant=tenant, location=store, product=product,
            rule_type="markup_pct", value=10,
        )
        LocationPricingRule.objects.create(
            tenant=tenant, location=dc, product=product,
            rule_type="markdown_pct", value=5,
        )
        r = client_logged_in.get(f"/multi-location/pricing-rules/?location={store.pk}")
        rules = list(r.context["rules"])
        assert len(rules) == 1 and rules[0].location == store

    @pytest.mark.parametrize("value", ["abc", "-1", "999999999999999999999"])
    def test_non_numeric_location_filter(self, client_logged_in, value):
        """Regression for D-01."""
        r = client_logged_in.get(f"/multi-location/pricing-rules/?location={value}")
        assert r.status_code == 200

    def test_pagination_retains_filters(self, client_logged_in, tenant, store, product):
        """Regression for D-10."""
        for _ in range(25):
            LocationPricingRule.objects.create(
                tenant=tenant, location=store, rule_type="markup_pct", value=1,
            )
        r = client_logged_in.get(
            f"/multi-location/pricing-rules/?location={store.pk}&rule_type=markup_pct"
        )
        assert b"page=2" in r.content
        assert f"location={store.pk}".encode() in r.content
        assert b"rule_type=markup_pct" in r.content


@pytest.mark.django_db
class TestPricingRuleMutations:
    def test_admin_can_create(self, client_logged_in, tenant, store):
        r = client_logged_in.post(
            reverse("multi_location:pricing_rule_create"),
            data={
                'location': store.pk, 'product': '', 'category': '',
                'rule_type': 'markup_pct', 'value': '12',
                'priority': 1, 'is_active': 'on',
                'effective_from': '', 'effective_to': '', 'notes': '',
            },
        )
        assert r.status_code == 302
        assert LocationPricingRule.objects.filter(tenant=tenant, location=store).count() == 1

    def test_non_admin_blocked_from_create(self, staff_client):
        r = staff_client.get(reverse("multi_location:pricing_rule_create"))
        assert r.status_code == 403

    def test_non_admin_blocked_from_delete(self, staff_client, tenant, store):
        rule = LocationPricingRule.objects.create(
            tenant=tenant, location=store, rule_type="markup_pct", value=5,
        )
        r = staff_client.post(
            reverse("multi_location:pricing_rule_delete", args=[rule.pk])
        )
        assert r.status_code == 403
        assert LocationPricingRule.objects.filter(pk=rule.pk).exists()

    def test_cross_tenant_detail_404(self, client_logged_in, other_tenant, other_location):
        rule = LocationPricingRule.objects.create(
            tenant=other_tenant, location=other_location,
            rule_type="markup_pct", value=10,
        )
        r = client_logged_in.get(
            reverse("multi_location:pricing_rule_detail", args=[rule.pk])
        )
        assert r.status_code == 404

    def test_delete_get_does_not_delete(self, client_logged_in, tenant, store):
        rule = LocationPricingRule.objects.create(
            tenant=tenant, location=store, rule_type="markup_pct", value=5,
        )
        r = client_logged_in.get(
            reverse("multi_location:pricing_rule_delete", args=[rule.pk])
        )
        assert r.status_code == 302
        assert LocationPricingRule.objects.filter(pk=rule.pk).exists()
