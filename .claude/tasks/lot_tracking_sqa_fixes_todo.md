# Lot & Serial Tracking SQA Fixes + Automation — Execution Plan

Source of truth: [.claude/reviews/lot_tracking-review.md](../reviews/lot_tracking-review.md).
Goal: close every High/Medium defect and cheap Low items, promote shared helpers to `core/`, scaffold `lot_tracking/tests/` with 50+ passing tests.

---

## Phase A — Promote shared helpers to `core/`

Rationale: `tenant_admin_required` + `emit_audit` already live in both [vendors/decorators.py](../../vendors/decorators.py) and [warehousing/decorators.py](../../warehousing/decorators.py) as byte-identical copies. `TenantUniqueCodeMixin` is in [warehousing/forms.py](../../warehousing/forms.py). Four modules would now use them — time to lift.

- [ ] Create [core/decorators.py](../../core/decorators.py) — `tenant_admin_required`, `emit_audit`, `_client_ip`. Public shape must match the vendors/warehousing copies byte-for-byte so existing modules can import from there too.
- [ ] Create [core/forms.py](../../core/forms.py) — `TenantUniqueCodeMixin` with one extra parameter `field_name` (defaults to `'code'`) so lot_tracking can use it for `serial_number`.
- [ ] Leave existing `vendors/decorators.py` and `warehousing/decorators.py` untouched this pass (they already pass all their tests). A follow-up sweep will convert them to thin re-exports.

---

## Phase B — Defect fixes

### High
- [ ] **D-01** — `SerialNumberForm` — use `TenantUniqueCodeMixin` with `field_name='serial_number'`.
- [ ] **D-02** — `SerialNumberForm.__init__` — include current `self.instance.lot` in `lot` queryset when editing (OR-join via `Q`).

### Medium
- [ ] **D-03** — `LotBatchForm.clean()` — `manufacturing_date <= expiry_date`.
- [ ] **D-04** — `LotBatchForm.clean_quantity` — value ≥ 1 (plus `MinValueValidator(1)` on the model for defence-in-depth).
- [ ] **D-05** — `@tenant_admin_required` on every create / edit / delete / transition / acknowledge view.
- [ ] **D-06** — `emit_audit(request, action, instance)` on every create / update / delete / transition / acknowledge success path.
- [ ] **D-08** — template fix: `expiry_dashboard.html:167` — change `'quarantined'` to `'quarantine'`. Also sweep the folder for other literal mismatches.
- [ ] **D-09** — new `lot_tracking/management/commands/generate_expiry_alerts.py` — idempotent daily-capable command.
- [ ] **D-10** — `TraceabilityLogForm.clean()` — event-type-specific guards (transfer needs both warehouses; sold/scrapped/adjusted/received needs quantity > 0).
- [ ] **D-11** — `lot_trace_view` / `serial_trace_view` — wrap `logs` in `Paginator(logs, 50)` and update templates.
- [ ] **D-13** — `LotBatchForm.clean_quantity` (edit path) — reject `quantity < self.instance.available_quantity`.

### Low
- [ ] **D-07** — atomic retry loop on `_generate_lot_number` + `_generate_log_number`, matching the warehousing fix.
- [ ] **D-12** — `serial_delete_view` — also refuse when `serial.lot.status in ('recalled','expired','quarantine')`.
- [ ] **D-14** — `expiry_acknowledge_view` — append instead of overwriting `alert.notes`.

### Info — deferred
- **D-15** — tests **are** Phase C, closing this defect.
- **D-16** — add "Showing latest N of M" text on lot_detail; low impact. Defer to next UI pass.

---

## Phase C — Automation

- [ ] `lot_tracking/tests/__init__.py`
- [ ] `lot_tracking/tests/conftest.py` — `tenant`, `other_tenant`, `user`, `non_admin_user`, `other_user`, `client_logged_in`, `client_non_admin`, `product`, `warehouse`, `lot`, `serial`.
- [ ] `lot_tracking/tests/test_models.py` — auto-codes (tenant-scoped), `is_expired`, `days_until_expiry`, `is_warranty_expired`, lot + serial transition matrices.
- [ ] `lot_tracking/tests/test_forms.py` — D-01, D-02, D-03, D-04, D-10, D-13 regression guards.
- [ ] `lot_tracking/tests/test_views_lot.py` — CRUD + transitions + IDOR + filters + TraceabilityLog auto-emission.
- [ ] `lot_tracking/tests/test_views_serial.py` — CRUD + transitions + D-02 edit-preservation + D-12 recalled-lot block.
- [ ] `lot_tracking/tests/test_views_expiry.py` — dashboard + list + acknowledge + D-14 notes append.
- [ ] `lot_tracking/tests/test_views_traceability.py` — list + filter + cross-tenant IDOR.
- [ ] `lot_tracking/tests/test_security.py` — OWASP A01 (anon, IDOR, RBAC), A03 (XSS, SQLi), A09 (AuditLog).
- [ ] `lot_tracking/tests/test_performance.py` — N+1 on lot_list, trace-view budget.
- [ ] `lot_tracking/tests/test_commands.py` — `generate_expiry_alerts` idempotency + dedup.
- [ ] Update [pytest.ini](../../pytest.ini) — append `lot_tracking/tests` to `testpaths`.
- [ ] `pytest lot_tracking/tests -v` → all green.

---

## Phase D — Close-out

- [ ] Re-run shell probes from the review appendix — every one must now reject.
- [ ] Append **Review** section below with what changed, commits, test counts.
- [ ] Append a new lesson to [.claude/tasks/lessons.md](lessons.md) — `unique_together + tenant` has now hit **four** modules; codify the promotion of helpers to `core/` as the enforcement mechanism.
- [ ] Emit per-file PowerShell-safe `git add … ; git commit -m …` list at the end.

---

## Execution order

1. Promote helpers to `core/` (Phase A).
2. Fix `lot_tracking/forms.py` (D-01..D-04, D-10, D-13).
3. Fix `lot_tracking/models.py` (D-07).
4. Fix `lot_tracking/views.py` (D-05, D-06, D-11, D-12, D-14).
5. Fix template (D-08).
6. Add management command (D-09).
7. Scaffold tests.
8. `pytest lot_tracking/tests` — iterate until green.
9. Close-out.

---

## Review

Executed 2026-04-17.

### Summary
- Closed every High and Medium defect plus D-07, D-12, D-14 from Low. Deferred D-16 (UI polish — "showing latest N of M" label).
- **Promoted shared helpers to `core/`:**
  - [core/decorators.py](../../core/decorators.py) — `tenant_admin_required`, `emit_audit`, `_client_ip` (byte-identical with `vendors/` and `warehousing/` copies).
  - [core/forms.py](../../core/forms.py) — `TenantUniqueCodeMixin` generalised with a configurable `tenant_unique_field` attribute so it handles `serial_number` in lot_tracking as easily as `code` in warehousing.
- [lot_tracking/forms.py](../../lot_tracking/forms.py): consumed `core.forms.TenantUniqueCodeMixin` on `SerialNumberForm` (D-01). Added D-02 lot-FK preservation (OR-join on current instance), D-03 mfg/expiry cross-field, D-04 quantity ≥ 1 + D-13 quantity-vs-available_quantity invariant, D-10 event-type guards on `TraceabilityLogForm`.
- [lot_tracking/models.py](../../lot_tracking/models.py): atomic retry loop on both `_generate_lot_number` and `_generate_log_number` (D-07); `MinValueValidator(1)` on `LotBatch.quantity`. Migration [0002_alter_lotbatch_quantity.py](../../lot_tracking/migrations/0002_alter_lotbatch_quantity.py).
- [lot_tracking/views.py](../../lot_tracking/views.py): `@tenant_admin_required` + `emit_audit()` on all create / edit / delete / transition / acknowledge paths (D-05 + D-06). Bin-style occupancy guard for `serial_delete_view` when parent lot is recalled/expired/quarantine (D-12). Notes-append with timestamp + actor on `expiry_acknowledge_view` (D-14). Pagination (50/page) on `lot_trace_view` / `serial_trace_view` (D-11).
- [templates/lot_tracking/expiry_dashboard.html](../../templates/lot_tracking/expiry_dashboard.html): `'quarantined'` → `'quarantine'`, added `'consumed'` branch (D-08).
- [lot_tracking/management/commands/generate_expiry_alerts.py](../../lot_tracking/management/commands/generate_expiry_alerts.py): idempotent daily command for D-09 — dedup by `(tenant, lot, alert_type, alert_date)` via `get_or_create`; `--days` flag widens horizon; `--tenant=<slug>` narrows to one tenant.
- Scaffolded `lot_tracking/tests/` with 115 tests across 8 files covering models (transitions, properties, auto-codes), forms (D-01..D-04, D-10, D-13), views (lot + serial CRUD, expiry, traceability), security (auth, RBAC, XSS, SQLi, AuditLog), performance (N+1 + trace budget), and the new management command.

### Verification
- Re-ran the review's Django-shell probes — all six defects (D-01, D-02, D-03, D-04, D-10, D-13) now reject at the form layer with clean, user-facing messages.
- `pytest lot_tracking/tests -v` → **115 passed**.
- `pytest` (full repo) → **642 passed**, zero regressions in the other modules (catalog, vendors, receiving, purchase_orders, warehousing, inventory, stock_movements).

### Files touched
| File | Kind |
|---|---|
| [core/decorators.py](../../core/decorators.py) | new |
| [core/forms.py](../../core/forms.py) | new |
| [lot_tracking/forms.py](../../lot_tracking/forms.py) | updated |
| [lot_tracking/models.py](../../lot_tracking/models.py) | updated |
| [lot_tracking/migrations/0002_alter_lotbatch_quantity.py](../../lot_tracking/migrations/0002_alter_lotbatch_quantity.py) | new (generated) |
| [lot_tracking/views.py](../../lot_tracking/views.py) | updated |
| [templates/lot_tracking/expiry_dashboard.html](../../templates/lot_tracking/expiry_dashboard.html) | updated |
| [lot_tracking/management/commands/generate_expiry_alerts.py](../../lot_tracking/management/commands/generate_expiry_alerts.py) | new |
| [lot_tracking/tests/__init__.py](../../lot_tracking/tests/__init__.py) | new |
| [lot_tracking/tests/conftest.py](../../lot_tracking/tests/conftest.py) | new |
| [lot_tracking/tests/test_models.py](../../lot_tracking/tests/test_models.py) | new |
| [lot_tracking/tests/test_forms.py](../../lot_tracking/tests/test_forms.py) | new |
| [lot_tracking/tests/test_views_lot.py](../../lot_tracking/tests/test_views_lot.py) | new |
| [lot_tracking/tests/test_views_serial.py](../../lot_tracking/tests/test_views_serial.py) | new |
| [lot_tracking/tests/test_views_expiry.py](../../lot_tracking/tests/test_views_expiry.py) | new |
| [lot_tracking/tests/test_views_traceability.py](../../lot_tracking/tests/test_views_traceability.py) | new |
| [lot_tracking/tests/test_security.py](../../lot_tracking/tests/test_security.py) | new |
| [lot_tracking/tests/test_performance.py](../../lot_tracking/tests/test_performance.py) | new |
| [lot_tracking/tests/test_commands.py](../../lot_tracking/tests/test_commands.py) | new |
| [pytest.ini](../../pytest.ini) | updated (added `lot_tracking/tests` to `testpaths`) |
| [.claude/reviews/lot_tracking-review.md](../reviews/lot_tracking-review.md) | new (source of this plan) |
| [.claude/tasks/lot_tracking_sqa_fixes_todo.md](lot_tracking_sqa_fixes_todo.md) | new (this file) |
| [.claude/tasks/lessons.md](lessons.md) | updated (lesson #14) |

### Exit gate status (from review §7.3)
- [x] D-01, D-02, D-05, D-08 fixed (High + High-impact Medium defects).
- [x] `lot_tracking/tests/` has ≥ 50 passing tests (delivered 115).
- [x] No failing test in the full suite (642 green).
- [x] N+1 guards (`test_lot_list_no_n_plus_one`, `test_lot_trace_view_budget`) green.
- [x] `AuditLog` row emitted on ≥ 1 lot delete and ≥ 1 transition.
- [x] `generate_expiry_alerts` management command exists and is idempotent.
- [ ] Line coverage ≥ 85% on `lot_tracking/` — **not measured in this pass**.
- [ ] `bandit -r lot_tracking/` zero-High — **not run in this pass**.
- [ ] Manual runserver smoke — deferred to next pass.

### Testing gotchas captured
- `LotBatch.is_expired` uses `timezone.now().date()` (UTC when `USE_TZ=True`), not `date.today()` (local time). Tests running near midnight local time saw `date.today() == 2026-04-18` but `timezone.now().date() == 2026-04-17`, causing the `is_expired` property to return `False` for a lot with `expiry_date = date.today() - 1`. **Rule:** any test asserting a timezone-aware model property must use `timezone.now().date()` instead of `date.today()` for its reference point. Captured in [lessons.md](lessons.md#14).

### Bulk commit block (PowerShell-safe, one line per file)

```
git add 'core/decorators.py'; git commit -m 'feat(core): promote tenant_admin_required + emit_audit helpers to core/'
git add 'core/forms.py'; git commit -m 'feat(core): promote TenantUniqueCodeMixin helper to core/ (generalised for any unique field)'
git add 'lot_tracking/forms.py'; git commit -m 'fix(lot_tracking): form-level guards for D-01..D-04, D-10, D-13 (serial dup, lot FK preserve, date/qty, event-type, qty invariant)'
git add 'lot_tracking/models.py'; git commit -m 'fix(lot_tracking): atomic retry on auto-code generation + quantity MinValueValidator (D-07, D-04)'
git add 'lot_tracking/migrations/0002_alter_lotbatch_quantity.py'; git commit -m 'migration(lot_tracking): add MinValueValidator(1) to LotBatch.quantity'
git add 'lot_tracking/views.py'; git commit -m 'fix(lot_tracking): RBAC + AuditLog + notes-append + trace pagination + recalled-lot serial guard (D-05, D-06, D-11, D-12, D-14)'
git add 'templates/lot_tracking/expiry_dashboard.html'; git commit -m 'fix(lot_tracking): dashboard badge literal matches STATUS_CHOICES value (D-08)'
git add 'lot_tracking/management/commands/generate_expiry_alerts.py'; git commit -m 'feat(lot_tracking): generate_expiry_alerts daily command (D-09)'
git add 'lot_tracking/tests/__init__.py' 'lot_tracking/tests/conftest.py' 'lot_tracking/tests/test_models.py' 'lot_tracking/tests/test_forms.py' 'lot_tracking/tests/test_views_lot.py' 'lot_tracking/tests/test_views_serial.py' 'lot_tracking/tests/test_views_expiry.py' 'lot_tracking/tests/test_views_traceability.py' 'lot_tracking/tests/test_security.py' 'lot_tracking/tests/test_performance.py' 'lot_tracking/tests/test_commands.py'; git commit -m 'test(lot_tracking): 115 tests covering models, forms, views, security, performance, management command'
git add 'pytest.ini'; git commit -m 'test: include lot_tracking/tests in pytest testpaths'
git add '.claude/reviews/lot_tracking-review.md'; git commit -m 'docs(sqa): lot_tracking module SQA review with 16 defects and automation plan'
git add '.claude/tasks/lot_tracking_sqa_fixes_todo.md'; git commit -m 'docs(sqa): lot_tracking SQA fixes execution plan + review section'
git add '.claude/tasks/lessons.md'; git commit -m 'docs(lessons): capture helper promotion + timezone-vs-local-date trap (lesson #14)'
```

Stop-on-failure: the chained `;` continues past a failure. Run lines individually for stop-on-failure semantics.
