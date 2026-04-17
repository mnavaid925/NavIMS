# Stock Movement & Transfers — SQA Fixes + Automation Plan

Source report: [.claude/reviews/stock_movements-review.md](../reviews/stock_movements-review.md)

Working tree: `main` after the receiving-fixes commits land. Each file edit → one PowerShell-safe git commit at the end.

---

## Part A — Defect fixes (in dependency order)

### A.1 [D-01] Cross-tenant product IDOR (Critical, OWASP A01)
**Files:**
- [stock_movements/views.py](../../stock_movements/views.py): in both `transfer_create_view` (lines 91-99) and `transfer_edit_view` (lines 154-167) — verify each `product_id` belongs to `tenant`. Skip / surface error otherwise.

**Approach:** Build a single helper `_persist_transfer_items(transfer, tenant, request)` that:
1. Parses the parallel POST lists (`item_product`, `item_quantity`, `item_notes`).
2. Resolves each product_id via `Product.objects.filter(tenant=tenant, pk=...).first()`.
3. Returns a list of validation errors when any product is foreign / missing / quantity invalid.
4. Persists items only when no errors.

Call it from both views; render errors via `messages.error` and re-render the form on failure.

### A.2 [D-04] Racy auto-numbering (High)
**Files:**
- [stock_movements/models.py](../../stock_movements/models.py): import the proven helper from receiving and apply to `StockTransfer.save()`.

**Approach:** Either (a) duplicate the inline `_save_with_generated_number` helper, or (b) extract it to `core/db.py` and import from both. Pick (a) for speed in this fix; mark (b) as a future cleanup. Same `IntegrityError` retry pattern.

### A.3 [D-03] Completion silently overwrites partial receipts (High)
**Files:**
- [stock_movements/views.py](../../stock_movements/views.py): `transfer_transition_view` — for `new_status='completed'`, REJECT the transition when any item is short-received instead of overwriting; surface a warning.

### A.4 [D-05] Self-approval bypass (High, OWASP A01)
**Files:**
- [stock_movements/views.py](../../stock_movements/views.py): `transfer_approve_view` — reject when `transfer.requested_by_id == request.user.id`. Same guard on `transfer_transition_view` for `→ approved` transition.

### A.5 [D-06] Receive view UX defects (Medium)
**Files:**
- [stock_movements/views.py](../../stock_movements/views.py): `transfer_receive_view` — surface field-level errors when the input is non-int or out of `[0, item.quantity]`. Re-render form on errors instead of redirecting on success.

### A.6 [D-07] N+1 in `route_detail_view` (Medium)
**Files:**
- [stock_movements/views.py](../../stock_movements/views.py): add `.select_related('source_warehouse', 'destination_warehouse', 'requested_by')` to `related_transfers` queryset.

### A.7 [D-09] Approval rule consultation (Medium)
**Files:**
- [stock_movements/views.py](../../stock_movements/views.py): on transfer create — look up the smallest matching `TransferApprovalRule` (active, by item count). If `requires_approval=False`, leave status `draft`. If `requires_approval=True`, set `status='pending_approval'` automatically.

### A.8 [D-10] Approval rule range (Low)
**Files:**
- [stock_movements/forms.py](../../stock_movements/forms.py): `TransferApprovalRuleForm.clean` — reject `min_items > max_items` when `max_items` is set.

### A.9 [D-12] Product filter consistency (Low)
**Files:**
- [stock_movements/forms.py:84](../../stock_movements/forms.py#L84): change `is_active=True` → `status='active'` to match catalog/receiving.

### Deferred (out of scope this pass)
- **D-02** — Inventory integration. Architectural; needs a separate scope decision (which app owns `StockOnHand`, what the contract is). Documented in report.
- **D-08** — `AuditLog` on item delete. Project-wide concern; receiving/views also lacks this. Leave to a project-wide A09 sweep.
- **D-11** — Routes never enforced. UX decision (require route on inter-warehouse, or demote to docs).
- **D-13** — Approval-rule detail view. Cosmetic; add when CRUD-completeness sweep runs.
- **D-14** — RBAC beyond `@login_required`. Project-wide; D-05 fix patches the most dangerous case.
- **D-16** — Project-level settings; out of module scope.

---

## Part B — Automation scaffold

```
stock_movements/tests/
  __init__.py
  conftest.py
  test_models.py
  test_forms.py
  test_views_transfers.py     # incl. D-01 + D-03 regression
  test_views_approvals.py     # incl. D-05 + D-09 regression
  test_views_routes.py        # incl. D-07 regression
  test_views_receive.py       # incl. D-06 regression
  test_security.py            # OWASP A01/A03
  test_performance.py         # N+1 guards
  test_regression.py          # explicit guards for each fix
```

Update [pytest.ini](../../pytest.ini) — append `stock_movements/tests`.

---

## Acceptance criteria

- [ ] D-01, D-03, D-04, D-05, D-06, D-07, D-09, D-10, D-12 fixed.
- [ ] Each fix has at least one regression test.
- [ ] `pytest stock_movements/tests` green.
- [ ] `pytest` (whole repo) green.
- [ ] No regression in `seed_stock_movements`.
- [ ] PowerShell-safe per-file commit list.

---

## Review

### Execution summary

| Defect | Severity | Status | Regression test |
|---|---|---|---|
| D-01 Cross-tenant product injection | Critical | Fixed — `_parse_transfer_items` helper tenant-validates every `product_id` in POST | `test_views_transfers.py::TestTransferCreate::test_D01_*`, `TestTransferEdit::test_D01_*`, `test_security.py::TestA01CrossTenantPayloadInjection` |
| D-03 Completion overwrites partial receipts | High | Fixed — `transfer_transition_view` rejects `→ completed` when any item is short-received | `test_views_transfers.py::TestTransferTransitions::test_D03_*` + `test_complete_when_fully_received_succeeds` |
| D-04 Racy auto-numbering | High | Fixed — `_save_with_generated_number` helper ported from receiving; `transaction.atomic()` + `IntegrityError` retry | `test_models.py::TestStockTransferAutoNumber` |
| D-05 Self-approval bypass | High | Fixed — `transfer_approve_view` + `transfer_transition_view` reject when `requested_by_id == request.user.id` | `test_views_transfers.py::TestTransferTransitions::test_D05_*`, `test_views_approvals.py::TestApproveView::test_D05_*`, `test_security.py::TestA01SegregationOfDuties` |
| D-06 Receive view silent failures | Medium | Fixed — validates every input, surfaces field-level errors, re-renders form on failure | `test_views_receive.py::TestReceiveView::test_D06_*` (three cases: over-receive, non-int, negative) |
| D-07 N+1 in `route_detail_view` | Medium | Fixed — `select_related` + `annotate(_items_count=Count('items'))` | `test_performance.py::test_D07_route_detail_no_n_plus_one` |
| D-09 Approval rules dead code | Medium | Fixed — `_resolve_initial_status` helper consults smallest matching active rule at create time | `test_views_approvals.py::TestApprovalRuleConsultation` (5 cases: no rule, requires False, requires True, unbounded, inactive) |
| D-10 Rule range validation | Low | Fixed — `TransferApprovalRuleForm.clean` rejects `min_items > max_items` | `test_forms.py::TestApprovalRuleForm::test_D10_*` |
| D-12 Product filter consistency | Low | Fixed — `StockTransferItemForm` uses `status='active'` | `test_forms.py::TestStockTransferItemForm::test_D12_*` |

**Deferred (documented in report, not applied):**
- D-02 Inventory integration — architectural; needs cross-app contract with `warehousing` / `inventory`.
- D-08 AuditLog on item delete — project-wide A09 sweep.
- D-11 Routes never enforced — UX decision.
- D-13 Approval-rule detail view — cosmetic CRUD sweep.
- D-14 RBAC beyond `@login_required` — project-wide; D-05 patched the most dangerous case.
- D-16 Project-level settings.

### Test results

```
$ pytest stock_movements/tests
69 passed in 15.53s

$ pytest  (full repo)
527 passed in 24.73s

$ python manage.py seed_stock_movements  (second run)
  [Acme Industries] Stock movements data already exists. Use --flush to re-seed.
  ...idempotent, no crash.
```

Breakdown of new tests (69):
- Models: 10 (auto-number 3, status machine 3, aggregates 2, approval rule 2)
- Forms: 9 (StockTransferForm 4, item filter 1, route 2, approval rule range 3)
- Views (transfers): 14 (create 4, edit 3, delete 2, transitions 4, cross-tenant 1)
- Views (approvals): 9 (approve 4, rule consultation 5)
- Views (receive): 8 (status guard, partial, full, D-06 × 3, empty, cross-tenant)
- Views (routes): 5 (happy, src=dest, cross-tenant, related list, delete)
- Security: 10 (A01 × 6, SoD 1, cross-tenant payload 1, A03 × 2)
- Performance: 3 (transfer_list, route_list, route_detail — D-07)
- Bonus: 1 in test_models (isolation across tenants)

### Files changed

**Production code**
- [stock_movements/forms.py](../../stock_movements/forms.py) — added `TransferApprovalRuleForm.clean` (D-10); changed product filter to `status='active'` (D-12).
- [stock_movements/models.py](../../stock_movements/models.py) — added `_save_with_generated_number` helper (D-04); wired `StockTransfer.save()` to use it; extended `total_items` to prefer annotated value.
- [stock_movements/views.py](../../stock_movements/views.py) — added `_parse_transfer_items` and `_resolve_initial_status` helpers; rewrote `transfer_create_view` and `transfer_edit_view` (D-01, D-09); added self-approval guard to `transfer_approve_view` and `transfer_transition_view` (D-05); rewrote `transfer_receive_view` with strict validation (D-06); D-03 guard in `transfer_transition_view`; `select_related` + `annotate(_items_count)` on list and route_detail (D-07).

**New test files**
- [stock_movements/tests/__init__.py](../../stock_movements/tests/__init__.py)
- [stock_movements/tests/conftest.py](../../stock_movements/tests/conftest.py)
- [stock_movements/tests/test_models.py](../../stock_movements/tests/test_models.py)
- [stock_movements/tests/test_forms.py](../../stock_movements/tests/test_forms.py)
- [stock_movements/tests/test_views_transfers.py](../../stock_movements/tests/test_views_transfers.py)
- [stock_movements/tests/test_views_approvals.py](../../stock_movements/tests/test_views_approvals.py)
- [stock_movements/tests/test_views_receive.py](../../stock_movements/tests/test_views_receive.py)
- [stock_movements/tests/test_views_routes.py](../../stock_movements/tests/test_views_routes.py)
- [stock_movements/tests/test_security.py](../../stock_movements/tests/test_security.py)
- [stock_movements/tests/test_performance.py](../../stock_movements/tests/test_performance.py)

**Config / docs**
- [pytest.ini](../../pytest.ini) — added `stock_movements/tests` to `testpaths`.
- [.claude/tasks/lessons.md](./lessons.md) — lesson #11 (raw POST parallel-array IDOR) + mark `stock_movements` clear in lesson #7 scope.

### New lessons captured

- **Lesson #11 — Raw POST parallel-array IDOR.** A third variant of the "formset IDOR" family: when views build child rows from `request.POST.getlist('item_product')` + `getlist('item_quantity')` instead of using a Django formset, the tenant check has to be duplicated at parse time. Covered by a shared helper (`_parse_transfer_items`) that resolves IDs against a tenant-scoped queryset and aggregates errors. Same anti-pattern probably exists in `orders`, `returns`, `stocktaking` — audit next.

### Exit gate status

| Gate | Status |
|---|---|
| D-01, D-03, D-04, D-05 fixed with regression tests | ✅ |
| `stock_movements/tests` wired and green | ✅ (69/69) |
| Full repo `pytest` green | ✅ (527/527) |
| Seed idempotency verified | ✅ |
| N+1 budgets met (list ≤12, route_detail ≤15) | ✅ |
| PowerShell-safe commit list emitted | See chat tail |


