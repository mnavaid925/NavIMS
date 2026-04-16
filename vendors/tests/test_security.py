"""Security tests — OWASP-aligned."""
import pytest
from django.test import Client
from django.urls import reverse

from core.models import AuditLog
from vendors.models import Vendor


VENDOR_URLS = [
    ('vendors:vendor_list', []),
    ('vendors:vendor_create', []),
    ('vendors:performance_list', []),
    ('vendors:performance_create', []),
    ('vendors:contract_list', []),
    ('vendors:contract_create', []),
    ('vendors:communication_list', []),
    ('vendors:communication_create', []),
]


@pytest.mark.django_db
class TestAuthRequired:
    """A01 — every route requires authentication."""
    @pytest.mark.parametrize('name,args', VENDOR_URLS)
    def test_anon_redirects_to_login(self, client, name, args):
        r = client.get(reverse(name, args=args))
        assert r.status_code == 302
        assert 'login' in r.url.lower()


@pytest.mark.django_db
class TestCSRFEnforcement:
    def test_delete_without_csrf_returns_403(self, user, vendor):
        c = Client(enforce_csrf_checks=True)
        c.force_login(user)
        r = c.post(reverse('vendors:vendor_delete', args=[vendor.pk]))
        assert r.status_code == 403
        assert Vendor.objects.filter(pk=vendor.pk).exists()


@pytest.mark.django_db
class TestRBAC:
    """D-10 — non-admin tenant users cannot perform destructive ops."""
    def test_non_admin_cannot_create_vendor(self, client_non_admin):
        r = client_non_admin.post(reverse('vendors:vendor_create'), {
            'company_name': 'Illicit',
            'vendor_type': 'distributor',
            'status': 'active',
            'payment_terms': 'net_30',
            'lead_time_days': 0,
            'minimum_order_quantity': 1,
        })
        assert r.status_code == 403
        assert not Vendor.objects.filter(company_name='Illicit').exists()

    def test_non_admin_cannot_delete_vendor(self, client_non_admin, vendor):
        r = client_non_admin.post(reverse('vendors:vendor_delete', args=[vendor.pk]))
        assert r.status_code == 403
        assert Vendor.objects.filter(pk=vendor.pk).exists()

    def test_non_admin_can_still_read(self, client_non_admin, vendor):
        r = client_non_admin.get(reverse('vendors:vendor_list'))
        assert r.status_code == 200
        r = client_non_admin.get(reverse('vendors:vendor_detail', args=[vendor.pk]))
        assert r.status_code == 200


@pytest.mark.django_db
class TestAuditLog:
    """D-09 — every destructive op emits AuditLog."""
    def test_delete_vendor_emits_audit(self, client_logged_in, user, vendor):
        pk = vendor.pk
        client_logged_in.post(reverse('vendors:vendor_delete', args=[pk]))
        assert AuditLog.objects.filter(
            tenant=user.tenant,
            model_name='Vendor',
            object_id=str(pk),
            action__icontains='delete',
        ).exists()

    def test_create_vendor_emits_audit(self, client_logged_in, user):
        client_logged_in.post(reverse('vendors:vendor_create'), {
            'company_name': 'Fresh Co',
            'vendor_type': 'distributor',
            'status': 'active',
            'payment_terms': 'net_30',
            'lead_time_days': 0,
            'minimum_order_quantity': 1,
            'is_active': 'on',
        })
        assert AuditLog.objects.filter(
            tenant=user.tenant,
            model_name='Vendor',
            action__icontains='create',
        ).exists()

    def test_delete_contract_emits_audit(self, client_logged_in, user, contract):
        client_logged_in.post(reverse('vendors:contract_delete', args=[contract.pk]))
        assert AuditLog.objects.filter(
            tenant=user.tenant,
            model_name='VendorContract',
            action__icontains='delete',
        ).exists()


@pytest.mark.django_db
class TestWebsiteTabnabbing:
    """D-08 regression — target=_blank without rel=noopener is tabnabbing."""
    def test_website_link_has_rel_noopener(self, client_logged_in, vendor):
        vendor.website = 'https://evil.example'
        vendor.save()
        r = client_logged_in.get(reverse('vendors:vendor_detail', args=[vendor.pk]))
        assert b'rel="noopener noreferrer"' in r.content


@pytest.mark.django_db
class TestSQLiSafe:
    def test_search_with_classic_sqli_payload_returns_200(self, client_logged_in, vendor):
        r = client_logged_in.get(reverse('vendors:vendor_list') + "?q=' OR 1=1 --")
        assert r.status_code == 200
        # ORM parameterises — the payload is treated as a literal substring.
