import time

import pytest

from multi_location.models import Location


@pytest.mark.django_db
class TestLocationCodeGenerator:
    def test_auto_code_first_insert(self, tenant):
        loc = Location.objects.create(tenant=tenant, name="HQ")
        assert loc.code == "LOC-00001"

    def test_auto_code_sequential(self, tenant):
        Location.objects.create(tenant=tenant, name="HQ")
        loc2 = Location.objects.create(tenant=tenant, name="DC")
        assert loc2.code == "LOC-00002"

    def test_auto_code_not_reset_by_non_loc_prefix(self, tenant):
        """Regression for D-02: non-LOC prefix must not reset the numbering."""
        Location.objects.create(tenant=tenant, name="A")
        Location.objects.create(tenant=tenant, name="X", code="STORE-01")
        loc = Location.objects.create(tenant=tenant, name="B")
        assert loc.code == "LOC-00002"
        assert Location.objects.filter(tenant=tenant, code=loc.code).count() == 1

    def test_auto_code_takes_max_not_latest(self, tenant):
        """Holes in the sequence do not cause collisions."""
        Location.objects.create(tenant=tenant, name="A")         # LOC-00001
        Location.objects.create(tenant=tenant, name="B")         # LOC-00002
        Location.objects.get(tenant=tenant, code="LOC-00001").delete()
        loc = Location.objects.create(tenant=tenant, name="C")
        assert loc.code == "LOC-00003"

    def test_auto_code_isolated_per_tenant(self, tenant, other_tenant):
        Location.objects.create(tenant=tenant, name="A")
        loc = Location.objects.create(tenant=other_tenant, name="A")
        assert loc.code == "LOC-00001"


@pytest.mark.django_db
class TestLocationHierarchy:
    def test_full_path_three_levels(self, company, region, dc):
        assert dc.full_path == "HQ > North > Seattle DC"

    def test_full_path_cycle_marks_and_terminates(self, tenant):
        """Regression for D-09: must not render infinite chain."""
        a = Location.objects.create(tenant=tenant, name="A")
        b = Location.objects.create(tenant=tenant, name="B", parent=a)
        a.parent = b
        a.save()
        path = a.full_path
        assert "…" in path
        assert path.count(">") <= 3

    def test_get_descendant_ids_terminates_on_cycle(self, tenant):
        """Regression for D-08: must return in < 1s and yield a finite set."""
        a = Location.objects.create(tenant=tenant, name="A")
        b = Location.objects.create(tenant=tenant, name="B", parent=a)
        a.parent = b
        a.save()
        t0 = time.time()
        ids = a.get_descendant_ids()
        assert time.time() - t0 < 1.0
        assert set(ids) == {b.pk}

    def test_get_descendant_ids_include_self(self, company, region, dc, store):
        ids = set(company.get_descendant_ids(include_self=True))
        assert ids == {company.pk, region.pk, dc.pk, store.pk}

    def test_children_count_property(self, company, region):
        assert company.children_count == 1

    def test_walks_into_cycle_false_for_normal_tree(self, dc):
        assert dc._walks_into_cycle() is False


@pytest.mark.django_db
class TestLocationStr:
    def test_str_combines_code_and_name(self, tenant):
        loc = Location.objects.create(tenant=tenant, name="HQ")
        assert str(loc) == f"{loc.code} - HQ"
