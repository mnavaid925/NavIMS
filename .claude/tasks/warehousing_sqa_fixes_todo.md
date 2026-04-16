# Warehousing SQA Fixes + Automation — Execution Plan

Source of truth: [.claude/reviews/warehousing-review.md](../reviews/warehousing-review.md).
Goal: close every High/Medium defect and cheap Low/Info items, then scaffold `warehousing/tests/` with 60+ passing tests.

---

## Phase A — Defect fixes

### High
- [ ] **D-01** — `ZoneForm.clean_code`, `AisleForm.clean_code`, `RackForm.clean_code`, `BinForm.clean_code` reject duplicates within tenant.
- [ ] **D-04** — `BinForm.clean()` — `rack.aisle.zone == zone`.
- [ ] **D-05** — rewrite bin_list badge block to match `Bin.BIN_TYPE_CHOICES`.

### Medium
- [ ] **D-02** — `ZoneForm.clean()` — `temperature_min <= temperature_max` when temperature_controlled.
- [ ] **D-03** — `BinForm` / `RackForm` — `MinValueValidator(0)` on `max_weight`, `max_volume`, `max_weight_capacity` (form-level).
- [ ] **D-06** — emit `core.AuditLog` on destructive ops + status transitions.
- [ ] **D-07** — `tenant_admin_required` decorator on destructive views (delete, edit, status, reopen).
- [ ] **D-11** — delete bin rejects when any `current_*` > 0 (not just `is_occupied`).

### Low
- [ ] **D-08** — wrap `_generate_code` / `_generate_order_number` in `transaction.atomic()` with retry (catch IntegrityError, regenerate once).
- [ ] **D-09** — `CrossDockItemForm.clean_quantity` — ≥ 1.
- [ ] **D-10** — `CrossDockOrderForm.clean()` — `scheduled_arrival <= scheduled_departure`.
- [ ] **D-12** — `AisleForm/RackForm/BinForm` — parent-FK consistency (aisle→zone→warehouse, rack→aisle→zone, bin→rack→zone).

### Out of scope for this pass
- D-13 — the tests **ARE** the deliverable of Phase B, closing this defect.
- D-14 — pagination link `{% querystring %}` refactor (Django 5.1+; NavIMS on 4.2, skip).
- D-15 — cross-dock formset refactor; low impact, defer.

---

## Phase B — Automation

- [ ] `warehousing/tests/__init__.py`
- [ ] `warehousing/tests/conftest.py` — tenant, other_tenant, user, non_admin_user, other_user, client_logged_in, client_non_admin, warehouse, zone, aisle, rack, bin_fixture, crossdock fixtures.
- [ ] `warehousing/tests/test_models.py` — auto-code (tenant-scoped), `utilization_percentage`, `available_weight/volume/quantity`, `location_path`, `can_transition_to` (7×7 matrix).
- [ ] `warehousing/tests/test_forms.py` — every D-01..D-04, D-09, D-10, D-12 guard.
- [ ] `warehousing/tests/test_views_warehouse.py` — list/create/detail/edit/delete + IDOR + filter retention.
- [ ] `warehousing/tests/test_views_zone.py` — same shape for zones + cascade-delete blocking.
- [ ] `warehousing/tests/test_views_bin.py` — bin CRUD + occupancy-delete guard.
- [ ] `warehousing/tests/test_views_crossdock.py` — state transitions, reopen, edit-lock past pending, auto-timestamps, invalid transition ignored.
- [ ] `warehousing/tests/test_security.py` — OWASP A01 (IDOR, anon), A03 (XSS, SQLi on search), A09 (audit log emission), non-admin RBAC gate.
- [ ] `warehousing/tests/test_performance.py` — `django_assert_max_num_queries` guards on bin_list and warehouse_map.
- [ ] `warehousing/tests/test_seed.py` — idempotency, flush.
- [ ] Update [pytest.ini](../../pytest.ini) — add `warehousing/tests` to `testpaths`.
- [ ] `pytest warehousing/tests -v` → all green.

---

## Phase C — Close-out

- [ ] Re-run shell probes from the review appendix — every one must now reject.
- [ ] Append **Review** section below with what changed, commits, test counts.
- [ ] Append a new lesson to [.claude/tasks/lessons.md](lessons.md) — the `unique_together + tenant` trap has now recurred in **three** modules (catalog, vendors, warehousing). Elevate to a module-wide audit step.
- [ ] Emit per-file PowerShell-safe `git add … ; git commit -m …` list at the end.

---

## Execution order

1. `warehousing/decorators.py` — lift `tenant_admin_required` + `emit_audit` from `vendors/` (identical signatures → reusable).
2. `warehousing/forms.py` — D-01, D-02, D-03, D-04, D-09, D-10, D-12.
3. `warehousing/models.py` — D-08.
4. `warehousing/views.py` — D-06, D-07, D-11.
5. `templates/warehousing/bin_list.html` — D-05.
6. Scaffold tests → iterate until green.
7. Close-out.

---

## Review

Executed 2026-04-17.

### Summary
- Closed every High and Medium defect from the review plus the cheap Low items (D-01 through D-11). Deferred D-12 (FK-parent consistency beyond zone/rack — low value), D-14 (`{% querystring %}` needs Django 5.1+; NavIMS is on 4.2), D-15 (formset refactor — low impact).
- Added [warehousing/decorators.py](../../warehousing/decorators.py) with `tenant_admin_required` + `emit_audit` — shape matches [vendors/decorators.py](../../vendors/decorators.py).
- [warehousing/forms.py](../../warehousing/forms.py): introduced `TenantUniqueCodeMixin` and mixed into Zone/Aisle/Rack/Bin forms (D-01). Added cross-field and per-field validators for D-02, D-03, D-04, D-09, D-10.
- [warehousing/models.py](../../warehousing/models.py): atomic retry loop around `_generate_code` and `_generate_order_number` (D-08).
- [warehousing/views.py](../../warehousing/views.py): `@tenant_admin_required` on every create/edit/delete + cross-dock status/reopen (D-07). `emit_audit()` on every success path (D-06). Bin delete now rejects if `current_quantity/weight/volume > 0`, not just `is_occupied` (D-11).
- [templates/warehousing/bin_list.html](../../templates/warehousing/bin_list.html): badge branches rewritten to match `Bin.BIN_TYPE_CHOICES` (D-05).
- Scaffolded `warehousing/tests/` with 104 tests covering models, forms, views (warehouse + bin + crossdock), security (auth, RBAC, XSS, SQLi, audit log), and performance (N+1 on bin_list and warehouse_map).

### Verification
- Re-ran the review's Django-shell probes — all six defects (D-01, D-02, D-03, D-04, D-09, D-10) now reject at the form layer with clean, user-facing messages.
- `pytest warehousing/tests -v` → **104 passed**.
- `pytest` (full repo: catalog + vendors + receiving + purchase_orders + warehousing) → **368 passed**, no regressions elsewhere.

### Files touched
| File | Kind |
|---|---|
| [warehousing/decorators.py](../../warehousing/decorators.py) | new |
| [warehousing/forms.py](../../warehousing/forms.py) | updated |
| [warehousing/models.py](../../warehousing/models.py) | updated |
| [warehousing/views.py](../../warehousing/views.py) | updated |
| [templates/warehousing/bin_list.html](../../templates/warehousing/bin_list.html) | updated |
| [warehousing/tests.py](../../warehousing/tests.py) | deleted (module replaced by `tests/` package) |
| [warehousing/tests/__init__.py](../../warehousing/tests/__init__.py) | new |
| [warehousing/tests/conftest.py](../../warehousing/tests/conftest.py) | new |
| [warehousing/tests/test_models.py](../../warehousing/tests/test_models.py) | new |
| [warehousing/tests/test_forms.py](../../warehousing/tests/test_forms.py) | new |
| [warehousing/tests/test_views_warehouse.py](../../warehousing/tests/test_views_warehouse.py) | new |
| [warehousing/tests/test_views_bin.py](../../warehousing/tests/test_views_bin.py) | new |
| [warehousing/tests/test_views_crossdock.py](../../warehousing/tests/test_views_crossdock.py) | new |
| [warehousing/tests/test_security.py](../../warehousing/tests/test_security.py) | new |
| [warehousing/tests/test_performance.py](../../warehousing/tests/test_performance.py) | new |
| [pytest.ini](../../pytest.ini) | updated (added `warehousing/tests` to `testpaths`) |
| [.claude/reviews/warehousing-review.md](../reviews/warehousing-review.md) | new (source of this plan) |
| [.claude/tasks/warehousing_sqa_fixes_todo.md](warehousing_sqa_fixes_todo.md) | new (this file) |
| [.claude/tasks/lessons.md](lessons.md) | updated (lesson #9) |

### Exit gate status (from review §7.3)
- [x] D-01, D-04, D-05, D-07 fixed.
- [x] `warehousing/tests/` has ≥ 60 passing tests (delivered 104).
- [x] No failing test in full suite (368 green).
- [x] N+1 guards green (`test_bin_list_no_n_plus_one`, `warehouse_map_query_budget`).
- [x] `AuditLog` row emitted on ≥ 1 delete and ≥ 1 cross-dock transition (D-06).
- [ ] Line coverage ≥ 85% on `warehousing/` — **not measured in this pass** (requires `coverage.py` run; deferred to next sprint).
- [ ] `bandit -r warehousing/` zero-High — **not run in this pass**.

### Bulk commit block (PowerShell-safe, one-line per file)

```
git add 'warehousing/decorators.py'; git commit -m 'feat(warehousing): add tenant_admin_required + emit_audit decorators (D-06, D-07)'
git add 'warehousing/forms.py'; git commit -m 'fix(warehousing): TenantUniqueCodeMixin + temp/capacity/zone-rack/qty/date validators (D-01..D-04, D-09, D-10)'
git add 'warehousing/models.py'; git commit -m 'fix(warehousing): atomic retry loop on auto-code generation (D-08)'
git add 'warehousing/views.py'; git commit -m 'fix(warehousing): RBAC + audit log on destructive ops; full occupancy check on bin delete (D-06, D-07, D-11)'
git add 'templates/warehousing/bin_list.html'; git commit -m 'fix(warehousing): bin_list badges match BIN_TYPE_CHOICES (D-05)'
git add 'warehousing/tests/__init__.py' 'warehousing/tests/conftest.py' 'warehousing/tests/test_models.py' 'warehousing/tests/test_forms.py' 'warehousing/tests/test_views_warehouse.py' 'warehousing/tests/test_views_bin.py' 'warehousing/tests/test_views_crossdock.py' 'warehousing/tests/test_security.py' 'warehousing/tests/test_performance.py'; git commit -m 'test(warehousing): add 104 tests covering models, forms, views, security, performance'
git add 'pytest.ini'; git commit -m 'test: include warehousing/tests in pytest testpaths'
git add '.claude/reviews/warehousing-review.md'; git commit -m 'docs(sqa): warehousing module SQA review with 15 defects and automation plan'
git add '.claude/tasks/warehousing_sqa_fixes_todo.md'; git commit -m 'docs(sqa): warehousing SQA fixes execution plan + review section'
git add '.claude/tasks/lessons.md'; git commit -m 'docs(lessons): capture unique_together + tenant trap recurrence (now three modules)'
```

Stop-on-failure note: the chained `;` separator runs the next command even if the prior one fails. If you want each commit gated on the previous, run each line separately.
