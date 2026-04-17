"""Schedule CRUD + POST-only run (D-01) + run-idempotency (D-11)."""
from datetime import date

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from stocktaking.models import CycleCountSchedule, StockCount


@pytest.mark.django_db
class TestScheduleCRUD:
    def test_list(self, client_admin, schedule):
        r = client_admin.get(reverse('stocktaking:schedule_list'))
        assert r.status_code == 200
        assert schedule.name.encode() in r.content

    def test_create(self, client_admin, tenant, warehouse):
        r = client_admin.post(reverse('stocktaking:schedule_create'), {
            'name': 'Monthly B', 'frequency': 'monthly', 'abc_class': 'b',
            'warehouse': warehouse.pk, 'next_run_date': '',
            'is_active': 'on', 'notes': '',
        })
        assert r.status_code == 302
        sched = CycleCountSchedule.objects.get(tenant=tenant, name='Monthly B')
        assert sched.frequency == 'monthly'

    def test_detail(self, client_admin, schedule):
        r = client_admin.get(
            reverse('stocktaking:schedule_detail', args=[schedule.pk]),
        )
        assert r.status_code == 200

    def test_delete(self, client_admin, schedule):
        r = client_admin.post(
            reverse('stocktaking:schedule_delete', args=[schedule.pk]),
        )
        assert r.status_code == 302
        assert not CycleCountSchedule.objects.filter(pk=schedule.pk).exists()


@pytest.mark.django_db
class TestScheduleRun:
    def test_run_requires_post(self, client_admin, schedule):
        """D-01 regression — run must reject GET."""
        r = client_admin.get(reverse('stocktaking:schedule_run', args=[schedule.pk]))
        assert r.status_code == 405
        assert not StockCount.objects.filter(schedule=schedule).exists()

    def test_run_creates_draft_count(
        self, client_admin, tenant, schedule, stock_levels,
    ):
        r = client_admin.post(
            reverse('stocktaking:schedule_run', args=[schedule.pk]),
        )
        assert r.status_code == 302
        counts = StockCount.objects.filter(tenant=tenant, schedule=schedule)
        assert counts.count() == 1
        c = counts.first()
        assert c.status == 'draft'
        assert c.items.count() == len(stock_levels)

    def test_D11_run_is_idempotent_per_day(
        self, client_admin, tenant, schedule, stock_levels,
    ):
        """D-11 regression — two runs on the same day must NOT create
        two draft counts."""
        client_admin.post(reverse('stocktaking:schedule_run', args=[schedule.pk]))
        r2 = client_admin.post(reverse('stocktaking:schedule_run', args=[schedule.pk]))
        # View uses `timezone.now().date()` — match that, not Python's date.today(),
        # which may differ across timezone boundaries.
        counts = StockCount.objects.filter(
            tenant=tenant, schedule=schedule,
        )
        assert counts.count() == 1, (
            'D-11 regression: a second schedule_run created a duplicate draft count.'
        )
        msgs = [str(m) for m in get_messages(r2.wsgi_request)]
        assert any('already exists' in m for m in msgs)


@pytest.mark.django_db
class TestScheduleIdor:
    def test_cross_tenant_detail_404(self, client_other, schedule):
        r = client_other.get(
            reverse('stocktaking:schedule_detail', args=[schedule.pk]),
        )
        assert r.status_code == 404

    def test_cross_tenant_run_404(self, client_other, schedule):
        r = client_other.post(
            reverse('stocktaking:schedule_run', args=[schedule.pk]),
        )
        assert r.status_code == 404
