"""Integration tests — vendor list / create / detail / edit / delete."""
import pytest
from django.urls import reverse

from vendors.models import Vendor


@pytest.mark.django_db
class TestVendorList:
    def test_only_own_tenant_vendors_shown(self, client_logged_in, vendor, foreign_vendor):
        r = client_logged_in.get(reverse('vendors:vendor_list'))
        assert r.status_code == 200
        assert b'Acme Corp' in r.content
        assert b'Foreign Co' not in r.content

    @pytest.mark.parametrize('q,expected', [
        ('Acme', True),
        ('NotHere', False),
    ])
    def test_search_by_name(self, client_logged_in, vendor, q, expected):
        r = client_logged_in.get(reverse('vendors:vendor_list'), {'q': q})
        assert r.status_code == 200
        assert (b'Acme Corp' in r.content) == expected

    def test_filter_by_status(self, client_logged_in, tenant, vendor):
        Vendor.objects.create(tenant=tenant, company_name='Pending Co', status='pending')
        r = client_logged_in.get(reverse('vendors:vendor_list'), {'status': 'pending'})
        assert r.status_code == 200
        assert b'Pending Co' in r.content
        assert b'Acme Corp' not in r.content

    def test_filter_by_vendor_type(self, client_logged_in, tenant, vendor):
        Vendor.objects.create(tenant=tenant, company_name='Whole Co', vendor_type='wholesaler', status='active')
        r = client_logged_in.get(reverse('vendors:vendor_list'), {'vendor_type': 'wholesaler'})
        assert b'Whole Co' in r.content
        assert b'Acme Corp' not in r.content


@pytest.mark.django_db
class TestVendorCreate:
    def test_create_happy_path(self, client_logged_in, tenant):
        r = client_logged_in.post(reverse('vendors:vendor_create'), {
            'company_name': 'Brand New Co',
            'vendor_type': 'distributor',
            'status': 'active',
            'payment_terms': 'net_30',
            'lead_time_days': 7,
            'minimum_order_quantity': 10,
            'is_active': 'on',
        })
        assert r.status_code == 302
        assert Vendor.objects.filter(tenant=tenant, company_name='Brand New Co').exists()

    def test_create_rejects_duplicate_company_name(self, client_logged_in, vendor):
        """D-01 end-to-end — form error, not 500."""
        r = client_logged_in.post(reverse('vendors:vendor_create'), {
            'company_name': 'Acme Corp',
            'vendor_type': 'distributor',
            'status': 'active',
            'payment_terms': 'net_30',
            'lead_time_days': 0,
            'minimum_order_quantity': 1,
            'is_active': 'on',
        })
        assert r.status_code == 200  # re-render with error
        assert Vendor.objects.filter(company_name='Acme Corp').count() == 1


@pytest.mark.django_db
class TestVendorIDOR:
    def test_detail_cross_tenant_404(self, client_logged_in, foreign_vendor):
        r = client_logged_in.get(reverse('vendors:vendor_detail', args=[foreign_vendor.pk]))
        assert r.status_code == 404

    def test_edit_get_cross_tenant_404(self, client_logged_in, foreign_vendor):
        r = client_logged_in.get(reverse('vendors:vendor_edit', args=[foreign_vendor.pk]))
        assert r.status_code == 404

    def test_edit_post_cross_tenant_404(self, client_logged_in, foreign_vendor):
        r = client_logged_in.post(reverse('vendors:vendor_edit', args=[foreign_vendor.pk]), {
            'company_name': 'Stolen',
            'vendor_type': 'distributor',
            'status': 'active',
            'payment_terms': 'net_30',
            'lead_time_days': 0,
            'minimum_order_quantity': 1,
        })
        assert r.status_code == 404
        foreign_vendor.refresh_from_db()
        assert foreign_vendor.company_name == 'Foreign Co'

    def test_delete_cross_tenant_404_not_deleted(self, client_logged_in, foreign_vendor):
        r = client_logged_in.post(reverse('vendors:vendor_delete', args=[foreign_vendor.pk]))
        assert r.status_code == 404
        assert Vendor.objects.filter(pk=foreign_vendor.pk).exists()


@pytest.mark.django_db
class TestVendorDelete:
    def test_delete_get_is_noop(self, client_logged_in, vendor):
        r = client_logged_in.get(reverse('vendors:vendor_delete', args=[vendor.pk]))
        assert r.status_code == 302
        assert Vendor.objects.filter(pk=vendor.pk).exists()

    def test_delete_post_happy_path(self, client_logged_in, vendor):
        r = client_logged_in.post(reverse('vendors:vendor_delete', args=[vendor.pk]))
        assert r.status_code == 302
        assert not Vendor.objects.filter(pk=vendor.pk).exists()


@pytest.mark.django_db
class TestVendorXSS:
    def test_script_in_name_escaped_on_list(self, client_logged_in, tenant):
        Vendor.objects.create(
            tenant=tenant, company_name='<script>alert(1)</script>', status='active',
        )
        r = client_logged_in.get(reverse('vendors:vendor_list'))
        assert r.status_code == 200
        assert b'<script>alert(1)</script>' not in r.content
        assert b'&lt;script&gt;' in r.content


@pytest.mark.django_db
class TestVendorDetailSubforms:
    """Inline add handlers — happy path and invalid-form UX (D-11)."""
    def test_detail_renders(self, client_logged_in, vendor):
        r = client_logged_in.get(reverse('vendors:vendor_detail', args=[vendor.pk]))
        assert r.status_code == 200
        assert b'Acme Corp' in r.content

    def test_inline_performance_add_happy_path(self, client_logged_in, vendor):
        from datetime import date
        r = client_logged_in.post(reverse('vendors:vendor_performance_add', args=[vendor.pk]), {
            'vendor': vendor.pk,
            'review_date': date.today().isoformat(),
            'delivery_rating': 4, 'quality_rating': 4, 'compliance_rating': 4,
            'defect_rate': '1', 'on_time_delivery_rate': '95',
        })
        assert r.status_code == 302
        assert vendor.performances.count() == 1

    def test_inline_performance_add_invalid_shows_error_message(self, client_logged_in, vendor):
        """D-11 regression — invalid inline post must not silently succeed."""
        r = client_logged_in.post(
            reverse('vendors:vendor_performance_add', args=[vendor.pk]),
            {'vendor': vendor.pk},  # missing required fields
            follow=True,
        )
        assert r.status_code == 200
        # Message framework stores errors in messages stack — use response context
        msgs = [str(m) for m in r.context['messages']]
        assert any('required' in m.lower() or 'invalid' in m.lower() or 'form' in m.lower() for m in msgs)
        assert vendor.performances.count() == 0
