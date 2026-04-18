import pytest
from django.urls import reverse

from multi_location.models import (
    Location, LocationPricingRule, LocationSafetyStockRule, LocationTransferRule,
)


@pytest.mark.django_db
class TestLocationList:
    def test_list_200_for_admin(self, client_logged_in):
        r = client_logged_in.get(reverse("multi_location:location_list"))
        assert r.status_code == 200

    def test_list_filters_by_type(self, client_logged_in, tenant, company, store):
        r = client_logged_in.get("/multi-location/?type=retail_store")
        assert r.status_code == 200
        locations = list(r.context["locations"])
        assert store in locations
        assert company not in locations

    def test_list_filters_active_inactive(self, client_logged_in, tenant):
        Location.objects.create(tenant=tenant, name="Open", is_active=True)
        Location.objects.create(tenant=tenant, name="Shut", is_active=False)
        r = client_logged_in.get("/multi-location/?active=inactive")
        names = {loc.name for loc in r.context["locations"]}
        assert names == {"Shut"}

    def test_list_search_by_city(self, client_logged_in, tenant):
        Location.objects.create(tenant=tenant, name="A", city="Tokyo")
        Location.objects.create(tenant=tenant, name="B", city="Berlin")
        r = client_logged_in.get("/multi-location/?q=Tokyo")
        names = {loc.name for loc in r.context["locations"]}
        assert names == {"A"}

    @pytest.mark.parametrize("param", ["parent"])
    @pytest.mark.parametrize("value", ["abc", "1' OR '1'='1", "../etc/passwd", "9" * 25])
    def test_non_numeric_filter_does_not_500(self, client_logged_in, param, value):
        """Regression for D-01."""
        r = client_logged_in.get(f"/multi-location/?{param}={value}")
        assert r.status_code == 200

    def test_pagination_retains_query_filters(self, client_logged_in, tenant):
        """Regression for D-10."""
        for i in range(25):
            Location.objects.create(tenant=tenant, name=f"City{i}", city="Seattle")
        r = client_logged_in.get("/multi-location/?q=Seattle&active=active")
        assert b"page=2" in r.content
        assert b"q=Seattle" in r.content
        assert b"active=active" in r.content

    def test_cross_tenant_detail_404(self, client_logged_in, other_location):
        r = client_logged_in.get(
            reverse("multi_location:location_detail", args=[other_location.pk])
        )
        assert r.status_code == 404


@pytest.mark.django_db
class TestLocationMutations:
    def test_create_success(self, client_logged_in, tenant):
        r = client_logged_in.post(
            reverse("multi_location:location_create"),
            data={
                'name': 'NewLoc', 'location_type': 'retail_store',
                'parent': '', 'warehouse': '',
                'address': '', 'city': '', 'state': '', 'country': '',
                'postal_code': '', 'manager_name': '',
                'contact_email': '', 'contact_phone': '',
                'is_active': 'on', 'notes': '',
            },
        )
        assert r.status_code == 302
        assert Location.objects.filter(tenant=tenant, name='NewLoc').exists()

    def test_non_admin_blocked_from_create(self, staff_client):
        """Regression for D-13."""
        r = staff_client.get(reverse("multi_location:location_create"))
        assert r.status_code == 403

    def test_non_admin_blocked_from_edit(self, staff_client, dc):
        r = staff_client.get(reverse("multi_location:location_edit", args=[dc.pk]))
        assert r.status_code == 403

    def test_non_admin_blocked_from_delete(self, staff_client, dc):
        r = staff_client.post(reverse("multi_location:location_delete", args=[dc.pk]))
        assert r.status_code == 403
        assert Location.objects.filter(pk=dc.pk).exists()

    def test_non_admin_can_still_list_and_view(self, staff_client, dc):
        assert staff_client.get(reverse("multi_location:location_list")).status_code == 200
        assert staff_client.get(
            reverse("multi_location:location_detail", args=[dc.pk])
        ).status_code == 200

    def test_delete_requires_post(self, client_logged_in, tenant):
        loc = Location.objects.create(tenant=tenant, name="ToDelete")
        r = client_logged_in.get(reverse("multi_location:location_delete", args=[loc.pk]))
        assert r.status_code == 302
        assert Location.objects.filter(pk=loc.pk).exists()

    def test_delete_cascades_rules(self, client_logged_in, tenant, dc, product):
        LocationPricingRule.objects.create(
            tenant=tenant, location=dc, product=product, rule_type="markup_pct", value=10,
        )
        LocationSafetyStockRule.objects.create(
            tenant=tenant, location=dc, product=product,
            safety_stock_qty=1, reorder_point=2,
        )
        r = client_logged_in.post(reverse("multi_location:location_delete", args=[dc.pk]))
        assert r.status_code == 302
        assert not Location.objects.filter(pk=dc.pk).exists()
        assert not LocationPricingRule.objects.filter(location_id=dc.pk).exists()
        assert not LocationSafetyStockRule.objects.filter(location_id=dc.pk).exists()

    def test_cross_tenant_edit_404(self, client_logged_in, other_location):
        r = client_logged_in.post(
            reverse("multi_location:location_edit", args=[other_location.pk]),
            data={'name': 'Hack', 'location_type': 'retail_store', 'is_active': 'on'},
        )
        assert r.status_code == 404

    def test_cross_tenant_delete_404(self, client_logged_in, other_location):
        r = client_logged_in.post(
            reverse("multi_location:location_delete", args=[other_location.pk])
        )
        assert r.status_code == 404
        assert Location.objects.filter(pk=other_location.pk).exists()


@pytest.mark.django_db
class TestLocationAuditLog:
    """D-12 — every mutating location endpoint emits core.AuditLog."""

    def test_create_emits_audit(self, client_logged_in, tenant):
        from core.models import AuditLog
        client_logged_in.post(
            reverse("multi_location:location_create"),
            data={
                'name': 'AuditLoc', 'location_type': 'retail_store',
                'parent': '', 'warehouse': '',
                'address': '', 'city': '', 'state': '', 'country': '',
                'postal_code': '', 'manager_name': '',
                'contact_email': '', 'contact_phone': '',
                'is_active': 'on', 'notes': '',
            },
        )
        log = AuditLog.objects.filter(
            tenant=tenant, model_name='Location', action='create',
        ).first()
        assert log is not None
        assert 'code=' in log.changes

    def test_update_emits_audit(self, client_logged_in, tenant, dc):
        from core.models import AuditLog
        client_logged_in.post(
            reverse("multi_location:location_edit", args=[dc.pk]),
            data={
                'name': 'Renamed DC', 'location_type': 'distribution_center',
                'parent': '', 'warehouse': '',
                'address': '', 'city': '', 'state': '', 'country': '',
                'postal_code': '', 'manager_name': '',
                'contact_email': '', 'contact_phone': '',
                'is_active': 'on', 'notes': '',
            },
        )
        assert AuditLog.objects.filter(
            tenant=tenant, model_name='Location', action='update',
            object_id=str(dc.pk),
        ).exists()

    def test_delete_emits_audit(self, client_logged_in, tenant):
        from core.models import AuditLog
        loc = Location.objects.create(tenant=tenant, name='ToAudit')
        client_logged_in.post(reverse("multi_location:location_delete", args=[loc.pk]))
        log = AuditLog.objects.filter(
            tenant=tenant, model_name='Location', action='delete',
        ).first()
        assert log is not None
        assert 'code=' in log.changes and 'name=' in log.changes
