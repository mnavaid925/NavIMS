"""Regression tests keyed to the defects in .claude/reviews/quality_control-review.md.

Each test is named `test_D<NN>_*` so the intent is searchable and traceable
back to the SQA review.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import AuditLog
from quality_control.models import ScrapWriteOff, QCChecklist
from inventory.models import StockAdjustment, StockLevel


# ── D-01 High: concurrent scrap-post double-decrement ───────────

@pytest.mark.django_db
def test_D01_scrap_post_inner_recheck_catches_stale_approval_status(
    client_admin, tenant, tenant_admin, product, warehouse, stock_level, monkeypatch,
):
    """Simulated race: request A enters `scrap_post_view` with an in-memory
    `obj.approval_status='approved'` snapshot. Before it reaches the atomic
    block, another transaction (simulated by monkey-patching the queryset's
    `select_for_update` entry) has already flipped `approval_status` to
    'posted'. The D-01 fix — re-fetching under `select_for_update()` inside
    the atomic block and re-checking `can_transition_to('posted')` — must
    abort the second post with no StockLevel mutation and no duplicate
    StockAdjustment.

    The threaded version of this test requires a DB with real row-level locks
    (MySQL/Postgres); SQLite serialises writes at the table level and cannot
    reproduce the race. This deterministic test works on any DB backend.
    """
    scrap = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=2, unit_cost=Decimal('1.00'), reason='race-regression',
        approval_status='approved', requested_by=tenant_admin,
        approved_by=tenant_admin,
    )

    import quality_control.views as qc_views
    original_mgr = qc_views.ScrapWriteOff.objects

    class _PoisonQS:
        """When `.get()` is finally called after `select_for_update()`, bump
        the underlying row's approval_status via a raw UPDATE to simulate a
        concurrent commit. Then defer to the real queryset so the view sees
        the poisoned state."""

        def __init__(self, inner):
            self.inner = inner

        def get(self, **kwargs):
            # Simulate a concurrent view that completed the full save() path —
            # both approval_status and the status-mirror must be bumped to
            # 'posted' or the StateMachineMixin check (which reads `status`)
            # would miss the race.
            ScrapWriteOff.objects.filter(pk=scrap.pk).update(
                approval_status='posted', status='posted',
            )
            return self.inner.get(**kwargs)

    class _PoisonManager:
        def __getattr__(self, name):
            return getattr(original_mgr, name)

        def select_for_update(self):
            return _PoisonQS(original_mgr.select_for_update())

    monkeypatch.setattr(qc_views.ScrapWriteOff, 'objects', _PoisonManager())

    r = client_admin.post(reverse('quality_control:scrap_post', args=[scrap.pk]))
    assert r.status_code == 302

    stock_level.refresh_from_db()
    assert stock_level.on_hand == 100, f'on_hand must not change; got {stock_level.on_hand}'
    assert StockAdjustment.objects.filter(stock_level=stock_level).count() == 0


@pytest.mark.django_db
def test_D01_scrap_post_sequential_second_call_refuses(
    client_admin, tenant, tenant_admin, product, warehouse, stock_level,
):
    """Non-racing guard: once a scrap is posted, a second POST is a no-op.

    Catches the pre-flight `can_transition_to` check even when the inner
    re-fetch isn't stressed.
    """
    scrap = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=3, unit_cost=Decimal('1.00'), reason='seq',
        approval_status='approved', requested_by=tenant_admin,
    )
    r1 = client_admin.post(reverse('quality_control:scrap_post', args=[scrap.pk]))
    assert r1.status_code == 302
    stock_level.refresh_from_db()
    assert stock_level.on_hand == 97

    r2 = client_admin.post(reverse('quality_control:scrap_post', args=[scrap.pk]))
    assert r2.status_code == 302
    stock_level.refresh_from_db()
    assert stock_level.on_hand == 97          # unchanged
    assert StockAdjustment.objects.filter(stock_level=stock_level).count() == 1


# ── D-09 Low: audit payload contains adjustment + on_hand info ──

@pytest.mark.django_db
def test_D09_scrap_post_audit_payload_enriched(
    client_admin, tenant, tenant_admin, product, warehouse, stock_level,
):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=3, unit_cost=Decimal('1.00'), reason='x',
        approval_status='approved', requested_by=tenant_admin,
    )
    client_admin.post(reverse('quality_control:scrap_post', args=[s.pk]))
    entry = AuditLog.objects.filter(model_name='ScrapWriteOff', action='post').latest('id')
    assert 'approved->posted' in entry.changes
    assert 'adj=' in entry.changes
    assert 'on_hand 100->97' in entry.changes


# ── D-04 Medium: queryset union preserves historical edit ───────

@pytest.mark.django_db
def test_D04_product_deactivation_does_not_brick_edit(tenant, tenant_admin, product):
    from quality_control.forms import QCChecklistForm
    c = QCChecklist.objects.create(
        tenant=tenant, name='hist', applies_to='product', product=product,
        created_by=tenant_admin,
    )
    product.is_active = False; product.save()
    data = {
        'code': c.code, 'name': c.name, 'applies_to': 'product',
        'product': product.pk, 'is_mandatory': 'on', 'is_active': 'on',
    }
    form = QCChecklistForm(data=data, instance=c, tenant=tenant)
    assert form.is_valid(), form.errors
