from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from purchase_orders.models import PurchaseOrder
from .conftest import formset_payload


@pytest.mark.django_db
class TestListView:
    def test_anonymous_redirected(self, client):
        resp = client.get(reverse('purchase_orders:po_list'))
        assert resp.status_code == 302
        assert '/accounts/login/' in resp['Location']

    def test_list_tenant_isolation(
        self, client_logged_in, draft_po, other_tenant
    ):
        from vendors.models import Vendor
        other_vendor = Vendor.objects.create(
            tenant=other_tenant, company_name="Other",
            is_active=True, status="active")
        PurchaseOrder.objects.create(
            tenant=other_tenant, vendor=other_vendor, order_date=date.today())

        resp = client_logged_in.get(reverse('purchase_orders:po_list'))
        assert draft_po.po_number.encode() in resp.content

    def test_filter_by_status_hides_non_matches(self, client_logged_in, draft_po):
        resp = client_logged_in.get(
            reverse('purchase_orders:po_list') + '?status=approved')
        assert draft_po.po_number.encode() not in resp.content

    def test_search_by_po_number(self, client_logged_in, draft_po):
        resp = client_logged_in.get(
            reverse('purchase_orders:po_list') + f'?q={draft_po.po_number}')
        assert draft_po.po_number.encode() in resp.content

    def test_invalid_vendor_param_is_ignored(self, client_logged_in, draft_po):
        """Regression for D-11 (numeric coercion)."""
        resp = client_logged_in.get(
            reverse('purchase_orders:po_list') + '?vendor=abc')
        assert resp.status_code == 200
        assert draft_po.po_number.encode() in resp.content


@pytest.mark.django_db
class TestCreateView:
    def test_create_with_items(self, client_logged_in, tenant, vendor, product):
        data = {
            'vendor': str(vendor.pk),
            'order_date': str(date.today()),
            'expected_delivery_date': '',
            'payment_terms': 'net_30',
            'shipping_address': '',
            'notes': 'integration test',
        }
        data.update(formset_payload(rows=[
            {'product': product.pk, 'description': '', 'quantity': 2,
             'unit_price': '10.00', 'tax_rate': '0', 'discount': '0'},
        ]))
        # min_num=1 on formset
        data['items-MIN_NUM_FORMS'] = '1'
        resp = client_logged_in.post(reverse('purchase_orders:po_create'), data)
        assert resp.status_code == 302, resp.content
        po = PurchaseOrder.objects.filter(tenant=tenant).first()
        assert po is not None
        assert po.items.count() == 1
        assert po.grand_total == Decimal('20.00')


@pytest.mark.django_db
class TestDetailView:
    def test_cross_tenant_returns_404(
        self, client, other_tenant_user, draft_po
    ):
        client.force_login(other_tenant_user)
        resp = client.get(reverse('purchase_orders:po_detail', args=[draft_po.pk]))
        assert resp.status_code == 404

    def test_detail_renders_totals(self, client_logged_in, draft_po):
        resp = client_logged_in.get(reverse('purchase_orders:po_detail', args=[draft_po.pk]))
        assert resp.status_code == 200
        assert b'110.00' in resp.content  # grand_total


@pytest.mark.django_db
class TestDeleteView:
    def test_delete_draft_by_creator_succeeds(self, client_logged_in, draft_po):
        pk = draft_po.pk
        resp = client_logged_in.post(
            reverse('purchase_orders:po_delete', args=[pk]))
        assert resp.status_code == 302
        assert not PurchaseOrder.objects.filter(pk=pk).exists()

    def test_delete_non_draft_blocked(self, client_logged_in, pending_po):
        client_logged_in.post(
            reverse('purchase_orders:po_delete', args=[pending_po.pk]))
        assert PurchaseOrder.objects.filter(pk=pending_po.pk).exists()

    def test_delete_GET_redirects_without_deleting(
        self, client_logged_in, draft_po
    ):
        resp = client_logged_in.get(
            reverse('purchase_orders:po_delete', args=[draft_po.pk]))
        assert resp.status_code == 302
        assert PurchaseOrder.objects.filter(pk=draft_po.pk).exists()
