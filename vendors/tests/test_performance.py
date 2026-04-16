"""Performance regressions — query counts."""
import pytest
from datetime import date
from django.urls import reverse

from vendors.models import Vendor, VendorPerformance


@pytest.mark.django_db
def test_vendor_list_query_count_bounded(client_logged_in, tenant, django_assert_max_num_queries):
    # 50 vendors — list view must not issue per-row queries.
    for i in range(50):
        Vendor.objects.create(tenant=tenant, company_name=f'V{i:03d}', status='active')
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse('vendors:vendor_list'))
        assert r.status_code == 200


@pytest.mark.django_db
def test_performance_list_query_count_bounded(client_logged_in, tenant, vendor, django_assert_max_num_queries):
    for _ in range(25):
        VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=5, quality_rating=5, compliance_rating=5,
        )
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse('vendors:performance_list'))
        assert r.status_code == 200
