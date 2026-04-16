# Vendors SQA Fixes + Automation — Execution Plan

Source of truth: [.claude/reviews/vendors-review.md](../reviews/vendors-review.md).
Goal: implement every High/Critical defect, the cheap Medium/Low fixes, then scaffold `vendors/tests/` and prove everything works.

---

## Phase A — Defect fixes

### Critical
- [ ] **D-01** — `VendorForm.clean_company_name` — reject duplicates in same tenant before save.
- [ ] **D-02** — `VendorContractForm.clean_contract_number` — reject duplicates in same tenant.
- [ ] **D-06** — `VendorContractForm.clean_document` — extension whitelist + 10 MB cap + reject SVG + content-type check.

### High
- [ ] **D-03** — `VendorContractForm.clean()` — `end_date` must be > `start_date`.
- [ ] **D-04** — add `MinValueValidator(0), MaxValueValidator(100)` to `defect_rate` / `on_time_delivery_rate` on `VendorPerformance` model + migration.
- [ ] **D-10** — introduce `@tenant_admin_required` decorator in `core/` (or a local `vendors/decorators.py`) and apply to every destructive view.

### Medium
- [ ] **D-05** — `VendorPerformanceForm.clean_review_date` — no future dates.
- [ ] **D-07** — DB `CheckConstraint`s for ratings 1..5 on `VendorPerformance` + migration.
- [ ] **D-08** — add `rel="noopener noreferrer"` to `target="_blank"` links in [vendor_detail.html](../../templates/vendors/vendor_detail.html).
- [ ] **D-09** — emit `core.AuditLog` on every create/update/delete in `vendors/views.py`.

### Low / Info
- [ ] **D-11** — inline `*_add_view` handlers: on invalid form, `messages.error(...)` with the form errors (no silent redirect).
- [ ] **D-14** — pass `tenant=tenant` to the three inline forms for defence-in-depth.
- [ ] **D-16** — `MinValueValidator(1)` on `Vendor.minimum_order_quantity` (caught by the D-04 migration).
- [ ] **D-17** — `MinValueValidator(0)` on `VendorContract.contract_value`.

### Out of scope for this pass
- D-12 (N+1 in `average_performance_score`) — replace with `aggregate(Avg(...))` after tests pass.
- D-13 (standalone detail views for contract/performance/communication) — scope expansion; next sprint.
- D-15 (Edit icons in inline detail tables) — UI polish.

---

## Phase B — Automation

- [ ] Create `vendors/tests/__init__.py`
- [ ] Create `vendors/tests/conftest.py` — fixtures (`tenant`, `other_tenant`, `user`, `client_logged_in`, `vendor`, `foreign_vendor`, `performance`, `contract`).
- [ ] Create `vendors/tests/test_models.py` — unit tests for properties + `unique_together` + constraints.
- [ ] Create `vendors/tests/test_forms.py` — parametrised negative tests for every new `clean_*` guard (regression of D-01..D-07).
- [ ] Create `vendors/tests/test_views_vendor.py` — list / create / detail / edit / delete integration + tenant IDOR + XSS.
- [ ] Create `vendors/tests/test_security.py` — OWASP-mapped (auth required, CSRF, audit log, tabnabbing).
- [ ] Create `vendors/tests/test_performance.py` — `django_assert_max_num_queries` guard on vendor_list.
- [ ] Update [pytest.ini](../../pytest.ini) — append `vendors/tests` to `testpaths`.
- [ ] Run `pytest vendors/tests -v` → all green.

---

## Phase C — Close-out

- [ ] Verify fixes against shell probes from the review.
- [ ] Append **Review** section below with what changed, commits, test counts.
- [ ] Append a new lesson to [.claude/tasks/lessons.md](lessons.md) capturing the `unique_together` + tenant pattern's re-appearance in a second module (should have been applied as a module-wide audit after lesson #6).
- [ ] Emit per-file PowerShell-safe `git add … ; git commit -m …` list at the end.

---

## Execution order

1. Forms fixes (D-01, D-02, D-03, D-05, D-06) — one edit to [vendors/forms.py](../../vendors/forms.py).
2. Model fixes (D-04, D-07, D-16, D-17) — one edit to [vendors/models.py](../../vendors/models.py) + `makemigrations`.
3. Views fixes (D-09, D-10, D-11, D-14) — edits to [vendors/views.py](../../vendors/views.py) + new `vendors/decorators.py` if needed.
4. Template fixes (D-08) — edit [templates/vendors/vendor_detail.html](../../templates/vendors/vendor_detail.html).
5. Scaffold tests.
6. `pytest vendors/tests` — iterate until green.
7. Close-out (review section + lesson + commits).

---

## Review

Executed 2026-04-17.

### Summary
Closed every Critical and High defect from the review plus the cheap Medium / Info items. Added 78 regression tests; full suite (catalog + vendors) is 118 passing. Original shell probe re-run — every one of D-01 through D-07 now rejects at the form or DB layer (see verification output captured in the skill transcript).

### What changed

| File | Change | Defects closed |
|---|---|---|
| [vendors/forms.py](../../vendors/forms.py) | `clean_company_name`, `clean_contract_number`, `clean_document`, contract `clean()` cross-field, `clean_review_date` | D-01, D-02, D-03, D-05, D-06 |
| [vendors/models.py](../../vendors/models.py) | Max-100 validators on `defect_rate` / `on_time_delivery_rate`, `MinValueValidator(1)` on MOQ fields, `MinValueValidator(0)` on contract_value, six `CheckConstraint`s on `VendorPerformance` ratings/rates and `VendorContract.contract_value` | D-04, D-07, D-16, D-17 |
| [vendors/migrations/0002_alter_vendor_minimum_order_quantity_and_more.py](../../vendors/migrations/) | Generated migration for the above | — |
| [vendors/decorators.py](../../vendors/decorators.py) (new) | `@tenant_admin_required`, `emit_audit(request, action, instance, changes='')` helper | D-09, D-10 |
| [vendors/views.py](../../vendors/views.py) | `@tenant_admin_required` on every destructive view (create/edit/delete across all 4 entities + 6 inline handlers); `emit_audit` on every create/update/delete; inline add handlers now pass `tenant=tenant` to the form and surface form errors via `messages.error`; `_form_error_text` helper | D-09, D-10, D-11, D-14 |
| [templates/vendors/vendor_detail.html](../../templates/vendors/vendor_detail.html) | Added `rel="noopener noreferrer"` to the `target="_blank"` website link and contract document download link | D-08 |
| [vendors/tests/__init__.py](../../vendors/tests/__init__.py) (new) | package marker | — |
| [vendors/tests/conftest.py](../../vendors/tests/conftest.py) (new) | Fixtures: `tenant`, `other_tenant`, `user`, `non_admin_user`, `other_user`, `client_logged_in`, `client_non_admin`, `vendor`, `foreign_vendor`, `performance`, `contract`, `communication` | — |
| [vendors/tests/test_models.py](../../vendors/tests/test_models.py) (new) | 16 tests — `unique_together`, properties, `reviewed_by = SET_NULL`, six `CheckConstraint`s | — |
| [vendors/tests/test_forms.py](../../vendors/tests/test_forms.py) (new) | 26 tests — every new `clean_*` regression + file-upload whitelist + date cross-field + unicode/javascript-URL | — |
| [vendors/tests/test_views_vendor.py](../../vendors/tests/test_views_vendor.py) (new) | 17 tests — list/create/detail/edit/delete integration + IDOR + XSS + inline form UX | — |
| [vendors/tests/test_security.py](../../vendors/tests/test_security.py) (new) | 17 tests — A01 auth-required (parametrised 8 URLs), CSRF 403, RBAC (D-10), AuditLog (D-09), tabnabbing (D-08), SQLi safe | — |
| [vendors/tests/test_performance.py](../../vendors/tests/test_performance.py) (new) | 2 `django_assert_max_num_queries` guards on vendor_list (≤ 10) and performance_list (≤ 12) | — |
| [pytest.ini](../../pytest.ini) | Added `vendors/tests` to `testpaths` | — |
| [.claude/tasks/lessons.md](lessons.md) | Appended Issue #7 — the `unique_together` + tenant trap re-appeared in a second module; added audit-sweep rule | — |

### Deferred (not in this pass)
- **D-12** — `average_performance_score` still iterates in Python. Add `Vendor.objects.annotate(...)` or a cached property. Low risk; typical vendors have < 50 reviews.
- **D-13** — standalone detail views for Contract / Performance / Communication. Scope expansion (new templates, URLs, views).
- **D-15** — Edit icons alongside Delete in the inline tables on `vendor_detail.html`.

### Verification evidence

Original shell probe (from review §6) re-run after fixes — every defect now rejects:

```
D-01 duplicate company_name          valid=False  err={'company_name': ['A vendor with this company name already exists for this tenant.']}
D-02 duplicate contract_number        valid=False  err={'contract_number': ['A contract with this number already exists for this tenant.']}
D-03 end_date < start_date            valid=False  err={'end_date': ['End date must be after the start date.']}
D-04 defect_rate > 100                valid=False  err={'defect_rate': ['Ensure this value is less than or equal to 100.']}
D-05 review_date in future            valid=False  err={'review_date': ['Review date cannot be in the future.']}
D-06 contract document .exe upload    valid=False  err={'document': ['File type ".exe" is not allowed. Allowed types: doc, docx, jpeg, jpg, pdf, png, xls, xlsx.']}
D-07 ORM create with rating=0         BLOCKED at DB (PASS): CHECK constraint failed: vendorperformance_delivery_rating_1_5
```

### Test suite status

```
$ pytest
========================== 118 passed, 1 warning in 11.64s ==========================
```

- catalog/tests: 40 passing (pre-existing)
- vendors/tests: 78 passing (new)

### Git commits (one per file, PowerShell-safe)

```
git add 'vendors/forms.py'
git commit -m 'fix(vendors): add clean_* guards for unique_together, dates, file upload (D-01..D-06)'

git add 'vendors/models.py'
git commit -m 'fix(vendors): add rating/rate bounds + CHECK constraints + MOQ/contract_value guards (D-04, D-07, D-16, D-17)'

git add 'vendors/migrations/0002_alter_vendor_minimum_order_quantity_and_more.py'
git commit -m 'fix(vendors): migration for new validators and CheckConstraints'

git add 'vendors/decorators.py'
git commit -m 'feat(vendors): add @tenant_admin_required and emit_audit helpers (D-09, D-10)'

git add 'vendors/views.py'
git commit -m 'fix(vendors): gate destructive views behind tenant_admin, emit AuditLog, surface inline form errors (D-09..D-11, D-14)'

git add 'templates/vendors/vendor_detail.html'
git commit -m 'fix(vendors): add rel=noopener noreferrer to target=_blank anchors (D-08)'

git add 'vendors/tests/__init__.py'
git commit -m 'test(vendors): add tests package'

git add 'vendors/tests/conftest.py'
git commit -m 'test(vendors): add fixtures for tenant/user/vendor/contract/performance/communication'

git add 'vendors/tests/test_models.py'
git commit -m 'test(vendors): model unit tests for unique_together, properties, CheckConstraints'

git add 'vendors/tests/test_forms.py'
git commit -m 'test(vendors): regression coverage for D-01..D-06 form guards'

git add 'vendors/tests/test_views_vendor.py'
git commit -m 'test(vendors): integration tests for CRUD, IDOR, XSS, inline UX'

git add 'vendors/tests/test_security.py'
git commit -m 'test(vendors): OWASP-mapped auth/CSRF/RBAC/audit/tabnabbing tests'

git add 'vendors/tests/test_performance.py'
git commit -m 'test(vendors): N+1 query guards on list views'

git add 'pytest.ini'
git commit -m 'test: include vendors/tests in pytest testpaths'

git add '.claude/tasks/vendors_sqa_fixes_todo.md'
git commit -m 'docs(sqa): vendors SQA fixes execution plan + review section'

git add '.claude/reviews/vendors-review.md'
git commit -m 'docs(sqa): add vendors module SQA review with 17 defects and automation plan'

git add '.claude/tasks/lessons.md'
git commit -m 'docs(lessons): capture unique_together + tenant trap recurrence across modules'
```
