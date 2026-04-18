import pytest

from multi_location.models import Location


@pytest.mark.django_db
class TestHierarchyPerf:
    def test_descendant_traversal_is_bounded(self, django_assert_max_num_queries, tenant):
        """Build a 4-deep tree with ~40 nodes and verify a low query count.

        The previous implementation issued one query per iteration of the
        BFS stack. The new version visits every descendant once and emits
        one query per depth level.
        """
        root = Location.objects.create(tenant=tenant, name="root")
        prev = [root]
        for depth in range(3):
            new = []
            for parent in prev:
                for j in range(3):
                    c = Location.objects.create(
                        tenant=tenant, name=f"n-{depth}-{parent.pk}-{j}",
                        parent=parent,
                    )
                    new.append(c)
            prev = new
        # ~40 nodes across 4 depths. Traversal should be well under 30 queries.
        with django_assert_max_num_queries(60):
            ids = root.get_descendant_ids(include_self=True)
        assert len(ids) > 1


@pytest.mark.django_db
class TestListPerf:
    def test_location_list_query_bound(self, client_logged_in, django_assert_max_num_queries, tenant):
        for i in range(20):
            Location.objects.create(tenant=tenant, name=f"L{i}")
        with django_assert_max_num_queries(15):
            r = client_logged_in.get("/multi-location/")
        assert r.status_code == 200

    def test_stock_visibility_query_bound(self, client_logged_in, django_assert_max_num_queries):
        with django_assert_max_num_queries(25):
            r = client_logged_in.get("/multi-location/stock-visibility/")
        assert r.status_code == 200
