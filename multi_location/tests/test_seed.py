from io import StringIO

import pytest
from django.core.management import call_command

from multi_location.models import (
    Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
)


@pytest.mark.django_db
class TestSeedMultiLocation:
    def test_seed_without_warehouses_skips_tenant(self, tenant):
        """No warehouses → seed should skip and not crash."""
        out = StringIO()
        call_command("seed_multi_location", stdout=out)
        assert Location.objects.filter(tenant=tenant).count() == 0

    def test_seed_creates_full_hierarchy(self, tenant, warehouse, warehouse2, product, category):
        out = StringIO()
        call_command("seed_multi_location", stdout=out)
        assert Location.objects.filter(tenant=tenant).count() >= 7
        assert LocationTransferRule.objects.filter(tenant=tenant).count() >= 4

    def test_seed_idempotent(self, tenant, warehouse, warehouse2, product, category):
        call_command("seed_multi_location", stdout=StringIO())
        first_count = Location.objects.filter(tenant=tenant).count()
        assert first_count > 0
        call_command("seed_multi_location", stdout=StringIO())
        assert Location.objects.filter(tenant=tenant).count() == first_count

    def test_seed_flush_reseeds(self, tenant, warehouse, warehouse2, product, category):
        call_command("seed_multi_location", stdout=StringIO())
        before = Location.objects.filter(tenant=tenant).count()
        call_command("seed_multi_location", "--flush", stdout=StringIO())
        after = Location.objects.filter(tenant=tenant).count()
        assert before == after
