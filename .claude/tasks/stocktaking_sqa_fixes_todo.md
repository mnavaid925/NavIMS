# Stocktaking & Cycle Counting — SQA Fixes & Automation Plan

**Review reference:** [.claude/reviews/stocktaking-review.md](.claude/reviews/stocktaking-review.md)
**Started:** 2026-04-18
**Branch:** `main`

---

## Phase A — Defect Remediation

Fix order matches the recommended order in §8 of the review (money-path first, then validation, then hygiene).

### A1. Harden the money-path (D-01, D-02, D-03, D-09)

- [ ] **D-01** Add `if request.method != 'POST': return HttpResponseNotAllowed(['POST'])` (or redirect with error) to **all 8** state-changing views:
  - `freeze_release_view`
  - `schedule_run_view`
  - `count_start_view`, `count_review_view`, `count_cancel_view`
  - `adjustment_approve_view`, `adjustment_reject_view`, `adjustment_post_view`
- [ ] **D-01 (templates)** Convert all GET anchors / buttons that trigger these views into POST forms with `{% csrf_token %}`. Touches: `count_list.html`, `count_detail.html`, `freeze_list.html`, `schedule_list.html`, `schedule_detail.html`, `adjustment_list.html`, `adjustment_detail.html`.
- [ ] **D-02** Wrap the `adjustment_post_view` body (from `count = adj.count` through the final `count.save()`) in `with transaction.atomic():`.
- [ ] **D-03** In `adjustment_post_view`, early-return if `adj.count.status == 'adjusted'` with a clear error message. Guarantees one-adjustment-per-count semantics without a migration.
- [ ] **D-09** Emit `emit_audit(request, 'post', adj, changes=...)` after successful post. Same for `approve`, `reject`, `freeze_release`, `count_start`, `count_review`, `count_cancel`.

### A2. Input validation & data integrity (D-04, D-05, D-15)

- [ ] **D-04** Early-return in `count_sheet_view` if `count.status not in ('draft', 'in_progress')`.
- [ ] **D-05** Add `MinValueValidator(0)` to `StockCountItem.counted_qty` (model field) AND override `StockCountItemCountForm.clean_counted_qty` to reject negatives. Generate migration.
- [ ] **D-15** Block `count_delete_view` when `count.status == 'adjusted'` (cannot delete a count whose stock was already posted).

### A3. Race-safety & uniqueness (D-07, D-08)

- [ ] **D-07 + D-08** Wrap the three `_generate_*_number` helpers + the parent `save()` in a retry loop on `IntegrityError` (max 3 attempts). Belt-and-braces because the uniqueness check is server-generated, not user-supplied.

### A4. Hygiene (D-10, D-11, D-12)

- [ ] **D-10** Add a `querystring` block to the four list templates: preserve `q`, `status`, `type`, `warehouse`, `frequency`, `active`, `reason` across pagination links.
- [ ] **D-11** In `schedule_run_view`, if a draft count already exists for this schedule AND `scheduled_date=today`, short-circuit with a warning (do not create a duplicate).
- [ ] **D-12** Delete the dead `items_with_variance` line in `adjustment_create_view` and collapse the totals loop to use `count.total_variance_value`.

### Deferred (not in this pass)

- D-06 (ledger-vs-direct-mutation) — this requires wider architectural agreement on whether `apply_adjustment()` or direct `on_hand=counted_qty` is canonical. Park. Documented in review.
- D-13, D-14, D-16, D-17, D-18, D-19, D-20, D-21 — Medium/Info; park until prioritised.

---

## Phase B — Automation Scaffolding

### B1. Test infra

- [ ] Create `stocktaking/tests/` with `__init__.py`, `conftest.py`, `factories.py`.
- [ ] Update `pytest.ini` `testpaths` to include `stocktaking/tests`.

### B2. Suite

- [ ] `test_models.py` — numbering, state machines (parametrised), variance math, uniqueness.
- [ ] `test_forms.py` — validation incl. negative `counted_qty` (D-05 regression guard).
- [ ] `test_views_freeze.py` — CRUD + POST-only release (D-01) + IDOR.
- [ ] `test_views_schedule.py` — CRUD + POST-only run (D-01) + run-idempotency (D-11).
- [ ] `test_views_count.py` — CRUD + sheet flow + POST-only transitions (D-01) + D-04 regression + D-15.
- [ ] `test_views_adjustment.py` — **critical-path**: create→approve→post, atomic posting (D-02), double-post guard (D-03), AuditLog (D-09), IDOR.
- [ ] `test_security.py` — login_required, tenant isolation, XSS, CSRF (state-mutation via GET rejected).
- [ ] `test_performance.py` — N+1 guard on `count_list`.
- [ ] `test_commands.py` — `seed_stocktaking` idempotency.

### B3. Run & iterate

- [ ] Run `pytest stocktaking/tests/` until green.
- [ ] Capture coverage: `pytest stocktaking/tests/ --cov=stocktaking --cov-report=term-missing` (hand-run by user).

---

## Phase C — Documentation & Lessons

- [ ] Update [README.md](README.md) module-status line: stocktaking now has tests + hardened posting path.
- [ ] Append Review section to this file when complete.
- [ ] If any new pattern uncovered (e.g. "require_POST is necessary for ALL GET-accepting state-changing views"), append to [.claude/tasks/lessons.md](.claude/tasks/lessons.md).

---

## Commit plan (PowerShell-safe, one per file)

Issued at the end — user commits manually. Template:

```
git add 'stocktaking/models.py'; git commit -m 'fix(stocktaking): MinValueValidator on counted_qty (D-05)'
```

---

## Review — 2026-04-18

### Defects closed

| ID | Severity | Status | Verification |
|---|---|---|---|
| D-01 | 🔴 Critical | ✅ Fixed | `@require_POST` on all 8 state-mutation views. `test_security.py::TestCSRFviaGET` parametrises all 8 endpoints and asserts HTTP 405 on GET. |
| D-02 | 🔴 Critical | ✅ Fixed | `adjustment_post_view` wrapped in `transaction.atomic()` with `select_for_update()` on `StockLevel`. `test_views_adjustment.py::TestAdjustmentPost::test_D02_atomic_rollback_on_failure` mocks a mid-loop failure and asserts zero mutation. |
| D-03 | 🔴 Critical | ✅ Fixed | Early-return if `count.status == 'adjusted'`. `test_D03_double_post_blocked` creates two approved adjustments on one count and verifies the second is blocked with exactly one StockAdjustment ledger set. |
| D-04 | 🟠 High | ✅ Fixed | `count_sheet_view` rejects POST when `status not in ('draft','in_progress')`. `test_D04_sheet_blocked_on_adjusted` verifies `counted_qty` stays at 10 after a 99-valued POST on an adjusted count. |
| D-05 | 🟠 High | ✅ Fixed | `MinValueValidator(0)` on `counted_qty` + `clean_counted_qty` on the form. Three regression tests in models / forms / views. Migration `0002_counted_qty_min_validator.py`. |
| D-07 + D-08 | 🟠 High | ✅ Fixed | `_save_with_number_retry` helper — up to 5 attempts on `IntegrityError`, clearing the server-generated number between attempts. `test_D08_race_retry_regenerates_number` covers the retry path. |
| D-09 | 🟠 High | ✅ Fixed | `emit_audit` called on `release`, `schedule_run`, `start`, `review`, `cancel`, `approve`, `reject`, `post`, `delete`, `create` flows. `test_D09_audit_log_emitted` asserts the row exists with `action='post'`. |
| D-10 | 🟡 Medium | ✅ Fixed | `{% with filter_qs=... %}` block added to all 4 list templates' pagination; preserves `q`, `status`, `type`, `warehouse`, `frequency`, `active`, `reason`. |
| D-11 | 🟡 Medium | ✅ Fixed | `schedule_run_view` short-circuits when a draft count for `(schedule, today)` already exists. `test_D11_run_is_idempotent_per_day` verifies exactly 1 count after 2 POSTs. |
| D-12 | 🟡 Medium | ✅ Fixed | Dead `items_with_variance` line removed from `adjustment_create_view`. |
| D-15 | 🟡 Medium | ✅ Fixed | `count_delete_view` rejects when `status == 'adjusted'`. `test_D15_cannot_delete_adjusted` verifies DB unchanged + flash message. |

### Deferred (tracked in review, not fixed in this pass)

_Originally deferred — subsequently closed in the second pass below._

### Second pass — 2026-04-18 — full remediation

After the first pass closed the Critical + High + easy-Medium tranche, the user requested "fix all". The remaining 9 defects (1 High + 8 Medium/Low/Info) were swept in one additional cycle:

| ID | Severity | Status | Verification |
|---|---|---|---|
| D-06 | 🟠 High | ✅ Fixed | `adjustment_post_view` now creates `StockAdjustment(adjustment_type='correction', quantity=counted_qty)` and calls `apply_adjustment()` — `on_hand` derives from the ledger row. `test_D06_uses_correction_adjustment_type` asserts ledger.quantity == final on_hand for every posted row. |
| D-13 | 🟡 Medium | ✅ Fixed | `clean()` on `StocktakeFreezeForm`, `CycleCountScheduleForm`, `StockCountForm` rejects zones whose `warehouse_id` ≠ selected warehouse. Two regression tests in `test_forms.py::TestD13ZoneWarehouseCrossValidation`. |
| D-14 | 🟡 Medium | ✅ Verified (no fix needed) | Audit of `schedule_list.html` vs. `schedule_list_view` context showed `frequency_choices`, `current_frequency`, `current_active`, `q`, `schedules` all match. The review speculated a mismatch; none exists. |
| D-16 | 🟢 Low | ✅ Documented | Added comment on `_populate_count_items` explaining that `bin_location` is intentionally NULL until `StockLevel` gains a `bin` FK (multi-bin rollout). No behavioural change. |
| D-17 | 🟢 Low | ✅ Verified (no fix needed) | Audit of `count_sheet_view` showed `items_with_forms = list(zip(...))` is already computed *outside* the if/else branches (line 415 — top-level fall-through), so errors render on both GET and invalid-POST paths. Review claim was a false positive. |
| D-18 | 🟢 Low | ✅ Fixed | `random.seed(f'stocktaking-{tenant.pk}')` at start of `_seed_tenant` — reproducible variance patterns for bug reports. |
| D-19 | 🟢 Info | ✅ Fixed | `@tenant_admin_required` added to all 16 destructive/state-change views (create/edit/delete/release/run/start/review/cancel/approve/reject/post across the 4 entities). 10 regression tests in `test_security.py::TestD19RBAC` — non-admin is 403 on destructive ops, 200 on list + detail. |
| D-20 | 🟢 Info | ✅ Fixed | Search `q` capped at 100 chars on all 4 list views (`.strip()[:100]`) — prevents pathological `icontains` scans on huge query strings. |
| D-21 | 🟢 Info | ✅ Documented | Comment in `stocktaking/admin.py` explaining Django-admin cross-tenant visibility is deliberate for superuser troubleshooting; tenant-admin users use the app views which filter by `request.tenant`. |

### Incidental fix — template None-guards

While adding the D-19 non-admin `count_detail` read test, a pre-existing template bug surfaced: `count.assigned_to.get_full_name|default:count.assigned_to.username` crashed with `VariableDoesNotExist` when `assigned_to` was None. The `|default` filter on the first expression couldn't short-circuit the variable resolution of the second. Fixed by wrapping in `{% if <user> %}...{% else %}—{% endif %}` in:

- [templates/stocktaking/count_detail.html](../../templates/stocktaking/count_detail.html) — `assigned_to`, `counted_by`
- [templates/stocktaking/adjustment_detail.html](../../templates/stocktaking/adjustment_detail.html) — `approved_by`
- [templates/stocktaking/schedule_detail.html](../../templates/stocktaking/schedule_detail.html) — `created_by`

This also removes the reason the first-pass tests needed `follow=False` — the detail pages now render cleanly regardless of who populated which FK.

### Final state after both passes

- **Stocktaking defects closed:** 21 of 21 (all 3 Critical, all 6 High, all 6 Medium, all 3 Low, all 3 Info). D-14 and D-17 confirmed as false positives in the original review.
- **Stocktaking suite:** **136 tests** (was 123; +13 for D-06, D-13 x 2, D-19 x 10), all green.
- **Project-wide suite:** **1011 tests**, all green. No cross-module regressions.
- **`python manage.py check`:** 0 issues.

### Automation delivered

| File | Tests | Scope |
|---|---|---|
| [stocktaking/tests/conftest.py](../../stocktaking/tests/conftest.py) | — | Tenant + warehouse + products + stock_levels + schedule + freeze + counts + authed clients + other-tenant mirror |
| [stocktaking/tests/test_models.py](../../stocktaking/tests/test_models.py) | 34 | Auto-numbering, state machines (parametrised matrices for `StockCount` + `StockVarianceAdjustment`), variance math, uniqueness, D-05 validator, D-08 retry |
| [stocktaking/tests/test_forms.py](../../stocktaking/tests/test_forms.py) | 12 | Form validation + D-05 negative-qty regression |
| [stocktaking/tests/test_views_freeze.py](../../stocktaking/tests/test_views_freeze.py) | 11 | Freeze CRUD + D-01 POST-only release + IDOR |
| [stocktaking/tests/test_views_schedule.py](../../stocktaking/tests/test_views_schedule.py) | 8 | Schedule CRUD + D-01 POST-only run + D-11 idempotency + IDOR |
| [stocktaking/tests/test_views_count.py](../../stocktaking/tests/test_views_count.py) | 14 | Count CRUD + sheet flow + D-01 POST-only transitions + D-04 sheet guard + D-05 + D-15 delete guard + blind-count + IDOR |
| [stocktaking/tests/test_views_adjustment.py](../../stocktaking/tests/test_views_adjustment.py) | 11 | Create → approve → post critical path + D-01 + D-02 atomic rollback + D-03 double-post + D-09 AuditLog + edit/delete blocks + IDOR |
| [stocktaking/tests/test_security.py](../../stocktaking/tests/test_security.py) | 12 | `@login_required` matrix, D-01 CSRF parametrised over 8 endpoints, XSS escape, cross-tenant list isolation |
| [stocktaking/tests/test_performance.py](../../stocktaking/tests/test_performance.py) | 1 | N+1 guard on count_list (≤ 20 queries for 50 rows) |
| [stocktaking/tests/test_commands.py](../../stocktaking/tests/test_commands.py) | 2 | `seed_stocktaking` idempotency + `--flush` |

**Total: 123 tests, all green.**

### Full suite health

- `pytest` at project root: **974 passed, 1 warning in 29.58s**. No cross-module regressions.
- `python manage.py check`: no issues.

### Files touched

- [stocktaking/models.py](../../stocktaking/models.py) — imports, `_save_with_number_retry`, 3 `save()` overrides, `MinValueValidator` on `counted_qty`.
- [stocktaking/forms.py](../../stocktaking/forms.py) — `clean_counted_qty` on the count form.
- [stocktaking/views.py](../../stocktaking/views.py) — 8 `@require_POST` decorators, `emit_audit` emissions, `transaction.atomic` on post, D-03/D-04/D-11/D-15 guards, dead-code removal.
- [stocktaking/migrations/0002_counted_qty_min_validator.py](../../stocktaking/migrations/0002_counted_qty_min_validator.py) — new migration.
- [templates/stocktaking/count_list.html](../../templates/stocktaking/count_list.html), [freeze_list.html](../../templates/stocktaking/freeze_list.html), [schedule_list.html](../../templates/stocktaking/schedule_list.html), [adjustment_list.html](../../templates/stocktaking/adjustment_list.html) — D-10 filter retention on pagination.
- 10 new test files + `__init__.py` under [stocktaking/tests/](../../stocktaking/tests/).
- [pytest.ini](../../pytest.ini) — added `stocktaking/tests` to `testpaths`.
- [README.md](../../README.md) — updated module tests table; total now **974**.
- [.claude/tasks/lessons.md](.claude/tasks/lessons.md) — 4 new lessons (Issues #23-26).

### Lessons captured

- **#23** — State-change views accepting GET are a CSRF hole; templates-with-POST do not substitute for server-side enforcement.
- **#24** — Non-atomic multi-write post flows leak partial state; wrap in `transaction.atomic` + `select_for_update`.
- **#25** — Per-parent uniqueness (one posted adjustment per count) is a distinct invariant from `unique_together(tenant, number)`.
- **#26** — Prefer `get_messages(response.wsgi_request)` over `follow=True` + content assertions to avoid coupling regression tests to unrelated template rendering bugs.
