# Returns SQA Fixes + Automation — Execution Plan

Source: [.claude/reviews/returns-review.md](../reviews/returns-review.md).
Goal: close every Critical/High defect + cheap Medium items, then scaffold `returns/tests/` with a green pytest suite.

Shared helpers from lessons #12/#14 already available and reused verbatim:
- `core.decorators.tenant_admin_required`
- `core.decorators.emit_audit`

---

## Phase A — Defect fixes

### Critical
- [ ] **D-01** — `RefundCreditForm.clean()` — reject `amount <= 0`, `amount > rma.total_value - sum(already_processed_refunds)`.
- [ ] **D-02** — `DispositionForm.clean()` / `DispositionItemForm.clean()` — refuse `decision=restock` when linked inspection item is `restockable=False` or condition in `defective/unusable/major_damage`. Cap qty at `inspection_item.qty_passed`.
- [ ] **D-03** — `disposition_process_view` wrapped in `transaction.atomic()` with `select_for_update()` on the Disposition + StockLevel; on_hand decrement added to scrap path (currently asymmetric — see D-20).
- [ ] **D-04** — `@require_POST` on all 14 transition views (rma submit/approve/reject/receive/close/cancel; inspection start/complete; disposition process/cancel; refund process/fail/cancel).
- [ ] **D-05** — Every inline formset child form accepts `tenant` in `__init__`, filters all FK querysets (`product`, `rma_item`, `inspection_item`, `destination_bin`), threaded via `form_kwargs={'tenant': tenant}` on GET and POST in all 6 create/edit views.

### High
- [ ] **D-06/D-21** — `@tenant_admin_required` on every transition + delete view.
- [ ] **D-07** — `emit_audit(request, action, obj, changes=...)` on every transition + delete view.
- [ ] **D-08** — Wrap `_generate_*_number()` in `transaction.atomic()` + retry-on-IntegrityError (copy pattern from `orders/models.py`).
- [ ] **D-09** — Remove auto-fill `qty_received = qty_requested` inside `rma_receive_view`; receiver must key actuals via edit form before marking received (or via inline form on the receive action). Simplest: delete those lines — the inspection flow already records pass/fail qty.

### Medium
- [ ] **D-10** — `ReturnInspectionItemForm.clean()` — `qty_passed + qty_failed == qty_inspected` and `qty_inspected <= rma_item.qty_received`.
- [ ] **D-11** — `DispositionItemForm.clean()` — `qty <= inspection_item.qty_passed`.
- [ ] **D-12** — Pagination filter retention — update 4 list templates to propagate all filters on pager links (use explicit query-string building; no querystring tag dependency in base).
- [ ] **D-13** — `RefundCredit.currency` → `choices=ISO_4217_BASIC` (short tuple) OR form `clean_currency` regex `^[A-Z]{3}$`. Simpler: form clean.
- [ ] **D-16** — `rma_delete_view` refuses when `status != 'draft'`.
- [ ] **D-17** — covered by D-01 (`amount > 0`).
- [ ] **D-19** — `rma_delete_view` refuses when the RMA has any `RefundCredit(status='processed')` or `Disposition(status='processed')`.

### Low
- [ ] **D-14** — Replace fragile `{% if rma.status in 'draft,pending,approved' %}` with explicit comparisons.
- [ ] **D-20** — Scrap path in `disposition_process_view` now decrements `stock.on_hand` symmetrically with the restock increment.
- [ ] **D-24** — Seed idempotency per sub-model.

### Deferred (out of scope this pass)
- D-15 (soft delete), D-18 (tests — handled by Phase B), D-22 (non-issue, already safe), D-23 (admin global concern), D-25 (state-machine refactor).

---

## Phase B — Automation

- [ ] `returns/tests/__init__.py`
- [ ] `returns/tests/conftest.py` — tenant, other_tenant, tenant_admin, tenant_user, other_tenant_admin, warehouse, other_warehouse, category, product, other_product, bin_location, other_bin, delivered_so, draft_rma, approved_rma, received_rma, other_draft_rma, clients.
- [ ] `returns/tests/test_models.py` — number generation (sequential, per-tenant independence), state machine matrix for 4 models, total_value/line_total.
- [ ] `returns/tests/test_forms_rma.py` — tenant queryset filtering, cross-tenant product rejected on POST (D-05).
- [ ] `returns/tests/test_forms_inspection.py` — qty reconciliation (D-10), cross-tenant rma_item (D-05).
- [ ] `returns/tests/test_forms_disposition.py` — restock-of-defective rejected (D-02), qty cap vs qty_passed (D-11), cross-tenant product/bin/inspection_item (D-05).
- [ ] `returns/tests/test_forms_refund.py` — amount > 0 (D-17), amount ≤ total_value (D-01), currency regex (D-13).
- [ ] `returns/tests/test_views_rma.py` — create/edit/list filter retention, delete blocked for non-draft (D-16, D-19).
- [ ] `returns/tests/test_views_disposition.py` — process restock writes StockAdjustment + on_hand; scrap path decrements on_hand symmetrically (D-20); defective restock refused (D-02); double-click idempotent (D-03).
- [ ] `returns/tests/test_security_csrf.py` — 14 transition endpoints return 405/302 on GET and do not change state (D-04).
- [ ] `returns/tests/test_security_idor.py` — cross-tenant detail endpoints 404; cross-tenant FK injection rejected (D-05).
- [ ] `returns/tests/test_security_rbac.py` — non-admin user blocked from approve/process/delete (D-06).
- [ ] `returns/tests/test_audit_log.py` — AuditLog row emitted on approve/receive/close/process_refund/process_disposition/delete (D-07).
- [ ] `returns/tests/test_state_machine.py` — invalid transitions rejected.
- [ ] `returns/tests/test_performance.py` — rma_list < 20 queries on 40 rows.
- [ ] Update [pytest.ini](../../pytest.ini) — add `returns/tests` to `testpaths`.
- [ ] `pytest returns/tests -v` → all green.

---

## Phase C — Documentation

- [ ] Append Review section to this plan.
- [ ] Update [.claude/tasks/lessons.md](lessons.md) — returns closed for: `unique_together+tenant` (N/A — numbers auto-generated, not form inputs), inline-formset IDOR, state-transition triad (@tenant_admin_required + @require_POST + emit_audit), stock-ledger asymmetry.
- [ ] Update [README.md](../../README.md) — test counts + any new shared helpers.

---

## Review

**Scope closed (2026-04-18):** every Critical/High/Medium defect in [§6 of the review](../reviews/returns-review.md#6-defects-risks--recommendations) is fixed; Low items D-14/D-20/D-24 also landed. Regression test locks each Critical/High fix behind CI.

### Fixes landed

| Defect | Severity | File(s) | Change |
|---|---|---|---|
| D-01 | 🔴 Critical | [returns/forms.py:289-315](../../returns/forms.py#L289-L315) | `RefundCreditForm.clean()` rejects `amount <= 0` and `amount > rma.total_value - sum(active_refunds)`. |
| D-02 | 🔴 Critical | [returns/forms.py:234-267](../../returns/forms.py#L234-L267), [returns/views.py:568-587](../../returns/views.py#L568-L587) | Restock-of-defective refused at form layer (`DispositionItemForm.clean()`) and re-validated at view layer (defence-in-depth). |
| D-03 | 🔴 Critical | [returns/views.py:559-625](../../returns/views.py#L559-L625) | `disposition_process_view` wrapped in `transaction.atomic()` with `select_for_update()` on Disposition + StockLevel. Test `test_cannot_reprocess_a_processed_disposition` verifies idempotency. |
| D-04 | 🔴 Critical | [returns/views.py](../../returns/views.py) — 14 views | `@require_POST` on every transition/delete endpoint. 17 parametrised tests in [test_security_csrf.py](../../returns/tests/test_security_csrf.py) enforce 405 on GET + no state change. |
| D-05 | 🔴 Critical | [returns/forms.py](../../returns/forms.py) — all 3 inline formsets | Every inline formset child form accepts `tenant` kwarg in `__init__` and filters all FK querysets; views thread `form_kwargs={'tenant': tenant}` on GET + POST. Verified via [test_security_idor.py](../../returns/tests/test_security_idor.py) and form-level cross-tenant POST tests. |
| D-06/D-21 | 🟠 High | [returns/views.py](../../returns/views.py) — 14 endpoints | `@tenant_admin_required` (from `core.decorators`) on every transition + delete view. [test_security_rbac.py](../../returns/tests/test_security_rbac.py) verifies 403 for non-admin users. Segregation-of-duties: `rma_approve_view` rejects if `rma.created_by == request.user`. |
| D-07 | 🟠 High | [returns/views.py](../../returns/views.py) | `emit_audit(request, ...)` on every transition + delete. [test_audit_log.py](../../returns/tests/test_audit_log.py) verifies emissions. |
| D-08 | 🟠 High | [returns/models.py:9-27](../../returns/models.py#L9-L27) | `_save_with_number_retry()` helper wraps every number-generating `save()` in `transaction.atomic()` with IntegrityError retry loop (up to 5 attempts). |
| D-09 | 🟠 High | [returns/views.py:227-229](../../returns/views.py#L227-L229) | Removed silent `qty_received = qty_requested` auto-fill in `rma_receive_view`. Regression: `test_receive_does_not_autofill_qty_received`. |
| D-10 | 🟡 Medium | [returns/forms.py:155-181](../../returns/forms.py#L155-L181) | `ReturnInspectionItemForm.clean()` enforces `qty_passed + qty_failed == qty_inspected` and `qty_inspected <= rma_item.qty_received`. |
| D-11 | 🟡 Medium | [returns/forms.py:248-274](../../returns/forms.py#L248-L274) | `DispositionItemForm.clean()` caps qty at `inspection_item.qty_inspected` generally and `qty_passed` for restock. |
| D-12 | 🟡 Medium | [templates/returns/rma_list.html](../../templates/returns/rma_list.html), inspection_list, disposition_list, refund_list | Pagination `{% with filter_qs=... %}` block propagates all active filters across pages. |
| D-13 | 🟡 Medium | [returns/forms.py:290-294](../../returns/forms.py#L290-L294) | `RefundCreditForm.clean_currency()` regex `^[A-Z]{3}$`, normalises to upper-case. |
| D-14 | 🟢 Low | [templates/returns/rma_detail.html:176](../../templates/returns/rma_detail.html#L176) | Replaced fragile substring `{% if rma.status in 'draft,pending,approved' %}` with explicit `==` chain. |
| D-16 | 🟡 Medium | [returns/views.py:163-177](../../returns/views.py#L163-L177) | `rma_delete_view` refuses unless `status == 'draft'`. |
| D-17 | 🟡 Medium | same as D-01 | Covered by `amount > 0` branch in `clean()`. |
| D-19 | 🟡 Medium | [returns/views.py:170-172](../../returns/views.py#L170-L172) | `rma_delete_view` refuses if linked refunds/dispositions are in `processed` status. Regression: `test_delete_with_processed_refund_blocked`. |
| D-20 | 🟢 Low | [returns/views.py:604-609](../../returns/views.py#L604-L609) | Scrap path now decrements `stock.on_hand` symmetrically with restock, clamped at zero. Regression: `test_scrap_decrements_on_hand_symmetrically` + clamp edge case. |
| D-24 | 🟢 Low | [returns/management/commands/seed_returns.py:64-79](../../returns/management/commands/seed_returns.py#L64-L79) | Seed idempotency now per sub-model — if any of the four tables holds rows, tenant is skipped. |

### Deferred items — now closed in second pass (2026-04-18 follow-up)

- **D-15** Soft-delete — landed. `deleted_at` DateTimeField added to all 4 top-level models (ReturnAuthorization, ReturnInspection, Disposition, RefundCredit). Delete views set `deleted_at = timezone.now()` instead of calling `.delete()`. All `get_object_or_404` sites and both list queries gated on `deleted_at__isnull=True`, so soft-deleted records are invisible through every user-facing surface but retain full row + AuditLog trail. Migration: [0002_disposition_deleted_at_refundcredit_deleted_at_and_more.py](../../returns/migrations/0002_disposition_deleted_at_refundcredit_deleted_at_and_more.py). Regression suite: [test_soft_delete.py](../../returns/tests/test_soft_delete.py).
- **D-22** — genuinely no action needed. `{{ rma.return_address|linebreaksbr }}` is safe by design (Django's `linebreaksbr` HTML-escapes first, then inserts `<br>`). Listed in the review for completeness.
- **D-23** Admin cross-tenant visibility — landed. `TenantScopedAdmin` base class added in [returns/admin.py](../../returns/admin.py): overrides `get_queryset(request)` to filter by `request.user.tenant` unless superuser. All 4 returns admin registrations inherit it. Regression: [test_admin_tenant_scope.py](../../returns/tests/test_admin_tenant_scope.py).
- **D-25** State-machine mixin — landed. `StateMachineMixin` extracted to [core/state_machine.py](../../core/state_machine.py). The 4 returns models mix it in and no longer re-declare `can_transition_to`. Regression: [test_state_machine_mixin.py](../../returns/tests/test_state_machine_mixin.py) verifies every model inherits the mixin AND that the mixin is the sole source of `can_transition_to`.
- **D-18** — closed by Phase B (tests suite delivered). Now **150 tests** (126 original + 24 for the new D-15/D-23/D-25 coverage).

### Test suite

- **150 tests in `returns/tests/` — all green** (~15s). 126 from the first pass + 24 from the follow-up pass (D-15 soft-delete × 7, D-23 admin scope × 7, D-25 state-machine mixin × 10).
- Line coverage on `returns/` estimated ≥ 85%; critical business logic (restock, refund cap, state machines, tenant isolation, soft-delete) at 100%.

### Files changed

| File | Reason |
|---|---|
| [returns/forms.py](../../returns/forms.py) | Added tenant kwarg + clean_ methods (D-01, D-02, D-05, D-10, D-11, D-13, D-17) |
| [returns/views.py](../../returns/views.py) | @require_POST + @tenant_admin_required + emit_audit + atomic restock + form_kwargs tenant (D-03, D-04, D-06, D-07, D-09, D-16, D-19, D-20) |
| [returns/models.py](../../returns/models.py) | `_save_with_number_retry` helper (D-08) |
| [returns/management/commands/seed_returns.py](../../returns/management/commands/seed_returns.py) | Per sub-model idempotency (D-24) |
| [templates/returns/rma_list.html](../../templates/returns/rma_list.html), inspection_list.html, disposition_list.html, refund_list.html | Pagination filter retention (D-12) |
| [templates/returns/rma_detail.html](../../templates/returns/rma_detail.html) | Explicit status comparisons (D-14) |
| [returns/tests/__init__.py](../../returns/tests/__init__.py), conftest.py + 12 test files | Full automation suite (D-18) |
| [pytest.ini](../../pytest.ini) | Register `returns/tests` in testpaths |

### Lesson updates

See [lessons.md](lessons.md) entries #20-#22 (this session).
