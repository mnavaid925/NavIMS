"""Stock count CRUD + sheet flow + POST-only transitions (D-01) +
D-04 sheet-mutation guard + D-15 delete guard."""
from datetime import date

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from stocktaking.models import StockCount, StockCountItem


@pytest.mark.django_db
class TestCountCreate:
    def test_create_populates_items(
        self, client_admin, tenant, warehouse, stock_levels,
    ):
        r = client_admin.post(reverse('stocktaking:count_create'), {
            'type': 'cycle', 'warehouse': warehouse.pk,
            'scheduled_date': '2026-04-18', 'blind_count': '',
        })
        assert r.status_code == 302
        c = StockCount.objects.get(tenant=tenant)
        assert c.items.count() == len(stock_levels)
        # snapshot of system_qty
        assert c.items.first().system_qty == 100


@pytest.mark.django_db
class TestCountEdit:
    def test_edit_blocked_post_draft(
        self, client_admin, tenant, warehouse,
    ):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='counted',
        )
        r = client_admin.get(reverse('stocktaking:count_edit', args=[c.pk]))
        assert r.status_code == 302
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        assert any('Cannot edit a count after it has started' in m for m in msgs)


@pytest.mark.django_db
class TestCountSheet:
    def _formset_payload(self, item, counted_qty):
        return {
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-id': str(item.pk),
            'items-0-counted_qty': str(counted_qty),
            'items-0-reason_code': '',
            'items-0-notes': '',
        }

    def test_sheet_saves_counted_qty(
        self, client_admin, tenant, warehouse, products,
    ):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        item = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=10,
        )
        r = client_admin.post(
            reverse('stocktaking:count_sheet', args=[c.pk]),
            self._formset_payload(item, 12),
        )
        assert r.status_code == 302
        item.refresh_from_db()
        assert item.counted_qty == 12
        c.refresh_from_db()
        assert c.status == 'in_progress'

    def test_D04_sheet_blocked_on_adjusted(
        self, client_admin, tenant, warehouse, products,
    ):
        """D-04 regression — sheet POST must not mutate a finalised count."""
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='adjusted',
        )
        item = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=10,
        )
        r = client_admin.post(
            reverse('stocktaking:count_sheet', args=[c.pk]),
            self._formset_payload(item, 99),
        )
        item.refresh_from_db()
        assert item.counted_qty == 10, (
            'D-04 regression: sheet POST mutated counted_qty on an adjusted count.'
        )
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        assert any('read-only after submission' in m for m in msgs)

    def test_D05_negative_counted_qty_rejected(
        self, client_admin, tenant, warehouse, products,
    ):
        """D-05 regression — server-side validation must reject negatives."""
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        item = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=10,
        )
        r = client_admin.post(
            reverse('stocktaking:count_sheet', args=[c.pk]),
            self._formset_payload(item, -5),
        )
        item.refresh_from_db()
        assert item.counted_qty != -5, (
            'D-05 regression: negative counted_qty was accepted server-side.'
        )

    def test_submit_flips_to_counted(
        self, client_admin, tenant, warehouse, products,
    ):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='in_progress',
        )
        item = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=10,
        )
        payload = self._formset_payload(item, 10)
        payload['submit_count'] = '1'
        r = client_admin.post(reverse('stocktaking:count_sheet', args=[c.pk]), payload)
        assert r.status_code == 302
        c.refresh_from_db()
        assert c.status == 'counted'

    def test_blind_count_hides_system_qty(
        self, client_admin, tenant, warehouse, products,
    ):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), blind_count=True,
        )
        StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=42,
        )
        r = client_admin.get(reverse('stocktaking:count_sheet', args=[c.pk]))
        assert r.status_code == 200
        assert b'>42<' not in r.content
        assert b'Blind Count Mode' in r.content


@pytest.mark.django_db
class TestCountTransitions:
    def test_start_requires_post(self, client_admin, draft_count):
        url = reverse('stocktaking:count_start', args=[draft_count.pk])
        r = client_admin.get(url)
        assert r.status_code == 405

    def test_review_requires_post(
        self, client_admin, tenant, warehouse,
    ):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='counted',
        )
        url = reverse('stocktaking:count_review', args=[c.pk])
        r = client_admin.get(url)
        assert r.status_code == 405

    def test_cancel_requires_post(self, client_admin, draft_count):
        url = reverse('stocktaking:count_cancel', args=[draft_count.pk])
        r = client_admin.get(url)
        assert r.status_code == 405

    def test_review_via_post(self, client_admin, tenant, warehouse):
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='counted',
        )
        client_admin.post(reverse('stocktaking:count_review', args=[c.pk]))
        c.refresh_from_db()
        assert c.status == 'reviewed'


@pytest.mark.django_db
class TestCountDelete:
    def test_delete_draft(self, client_admin, draft_count):
        r = client_admin.post(
            reverse('stocktaking:count_delete', args=[draft_count.pk]),
        )
        assert r.status_code == 302
        assert not StockCount.objects.filter(pk=draft_count.pk).exists()

    def test_D15_cannot_delete_adjusted(
        self, client_admin, tenant, warehouse,
    ):
        """D-15 regression — cannot delete a count whose stock was already posted."""
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse,
            scheduled_date=date.today(), status='adjusted',
        )
        r = client_admin.post(reverse('stocktaking:count_delete', args=[c.pk]))
        assert StockCount.objects.filter(pk=c.pk).exists()
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        assert any('Cannot delete a count that has been adjusted' in m for m in msgs)


@pytest.mark.django_db
class TestCountIdor:
    def test_cross_tenant_sheet_404(self, client_other, draft_count):
        r = client_other.get(
            reverse('stocktaking:count_sheet', args=[draft_count.pk]),
        )
        assert r.status_code == 404
