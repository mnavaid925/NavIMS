"""Query-budget tests to enforce the D-02 N+1 fix stays in place."""
import pytest
from django.urls import reverse

from quality_control.models import QCChecklist, QCChecklistItem, InspectionRoute, InspectionRouteRule


@pytest.mark.django_db
def test_D02_checklist_list_no_n_plus_one(
    client_admin, django_assert_max_num_queries, tenant, tenant_admin,
):
    for i in range(25):
        c = QCChecklist.objects.create(
            tenant=tenant, name=f'C{i}', applies_to='all', created_by=tenant_admin,
        )
        for j in range(4):
            QCChecklistItem.objects.create(
                tenant=tenant, checklist=c, sequence=j,
                check_name=f'check {j}', check_type='visual',
            )
    # Budget: auth + middleware + count + list + annotate + pagination ≤ 12.
    # Without the annotate fix this scales with row count (≈ 30+).
    with django_assert_max_num_queries(12):
        r = client_admin.get(reverse('quality_control:checklist_list'))
        assert r.status_code == 200


@pytest.mark.django_db
def test_D02_route_list_no_n_plus_one(
    client_admin, django_assert_max_num_queries, tenant, warehouse, qc_zone, checklist,
):
    for i in range(15):
        route = InspectionRoute.objects.create(
            tenant=tenant, name=f'R{i}', source_warehouse=warehouse, qc_zone=qc_zone,
        )
        for j in range(3):
            InspectionRouteRule.objects.create(
                tenant=tenant, route=route, applies_to='all', checklist=checklist,
            )
    with django_assert_max_num_queries(12):
        r = client_admin.get(reverse('quality_control:route_list'))
        assert r.status_code == 200
