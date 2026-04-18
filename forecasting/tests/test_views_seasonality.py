import pytest
from django.urls import reverse

from forecasting.models import SeasonalityPeriod, SeasonalityProfile


@pytest.mark.django_db
class TestSeasonalityProfileCRUD:
    def test_list(self, client_logged_in):
        r = client_logged_in.get(reverse("forecasting:profile_list"))
        assert r.status_code == 200

    def test_create_monthly_autopopulates_12_periods(self, client_logged_in, tenant):
        r = client_logged_in.post(reverse("forecasting:profile_create"), {
            "name": "New monthly", "description": "",
            "category": "", "product": "",
            "period_type": "month", "is_active": "on", "notes": "",
        })
        assert r.status_code == 302
        profile = SeasonalityProfile.objects.get(tenant=tenant, name="New monthly")
        assert profile.periods.count() == 12

    def test_create_quarterly_autopopulates_4_periods(self, client_logged_in, tenant):
        r = client_logged_in.post(reverse("forecasting:profile_create"), {
            "name": "New quarterly", "description": "",
            "category": "", "product": "",
            "period_type": "quarter", "is_active": "on", "notes": "",
        })
        assert r.status_code == 302
        profile = SeasonalityProfile.objects.get(tenant=tenant, name="New quarterly")
        assert profile.periods.count() == 4

    def test_detail_shows_periods(self, client_logged_in, monthly_profile):
        r = client_logged_in.get(
            reverse("forecasting:profile_detail", args=[monthly_profile.pk])
        )
        assert r.status_code == 200
        assert len(r.context["periods"]) == 12

    def test_delete(self, client_logged_in, monthly_profile):
        r = client_logged_in.post(
            reverse("forecasting:profile_delete", args=[monthly_profile.pk])
        )
        assert r.status_code == 302
        assert not SeasonalityProfile.objects.filter(pk=monthly_profile.pk).exists()
