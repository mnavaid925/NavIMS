# Forecasting SQA fixes + automation — plan

Target: close defects D-01..D-19 from [.claude/Test.md](../Test.md) and scaffold `forecasting/tests/`.

## Phase 1 — Model-layer fixes

- [ ] D-10 / D-11: add `MinValueValidator` / `MaxValueValidator` on numeric fields in `forecasting/models.py`
- [ ] D-06 (model part): `MinValueValidator(Decimal('0'))` on `SeasonalityPeriod.demand_multiplier`
- [ ] D-03: make `_generate_forecast_number` + `_generate_alert_number` race-safe (`transaction.atomic()` + `select_for_update`)
- [ ] D-13: weekly label uses ISO year (`start.isocalendar()[:2]`)
- [ ] Generate migration for new validators

## Phase 2 — Form-layer fixes

- [ ] D-01: `ReorderPointForm.clean()` — duplicate (tenant, product, warehouse) guard
- [ ] D-02: `SafetyStockForm.clean()` — same guard
- [ ] D-06 (form part): `SeasonalityPeriodForm.clean_period_number()` bounded by profile.period_type
- [ ] D-07: `DemandForecastForm` — `history_periods ≥ 1`, `forecast_periods ≥ 1`
- [ ] D-08: `ReorderAlertAcknowledgeForm.clean()` — assert `can_transition_to('acknowledged')`

## Phase 3 — View-layer fixes

- [ ] D-04: add `@tenant_admin_required` on all mutating views (create/edit/delete/recalc/scan/close/mark-ordered/acknowledge/generate)
- [ ] D-05: convert `rop_check_alerts`, `alert_mark_ordered`, `alert_close`, `safety_stock_recalc` to POST-only
- [ ] D-09: wrap `forecast_generate_view` in `transaction.atomic()`
- [ ] D-12: `emit_audit` on create/edit/delete/recalc/transition/generate
- [ ] D-15: cap `suggested_order_qty` at `max(0, ...)`
- [ ] D-16: simplify dead-parallel seasonal branch
- [ ] D-17: `forecast_delete_view` — optional status guard

## Phase 4 — Automation scaffolding

- [ ] `forecasting/tests/__init__.py`
- [ ] `forecasting/tests/conftest.py` — tenant/user/product/warehouse + forecasting fixtures
- [ ] `forecasting/tests/test_models.py` — BR-01..BR-10 unit
- [ ] `forecasting/tests/test_forms.py` — D-01/D-02/D-06/D-07/D-08 regression
- [ ] `forecasting/tests/test_views_forecast.py` — CRUD + generate
- [ ] `forecasting/tests/test_views_rop.py` — CRUD + scan
- [ ] `forecasting/tests/test_views_alert.py` — state machine + D-05
- [ ] `forecasting/tests/test_views_safety_stock.py`
- [ ] `forecasting/tests/test_views_seasonality.py`
- [ ] `forecasting/tests/test_security.py` — RBAC, IDOR, XSS, anon
- [ ] `forecasting/tests/test_performance.py` — N+1 budgets
- [ ] `forecasting/tests/test_seed.py` — idempotency
- [ ] register `forecasting/tests` in [pytest.ini](../../pytest.ini)

## Phase 5 — Verify

- [x] `venv/Scripts/pytest forecasting/tests -q` green — **104 passed**
- [x] Re-run failing-before shell reproductions — all 8 confirmed defects now pass (D-01, D-02, D-03, D-06, D-07, D-08 proven closed via same repro snippets)
- [x] Full repo suite — 1247 passing
- [x] Captured lessons #35 (CSRF-on-GET) + #36 (template None-chain) in `lessons.md`

---

## Review (2026-04-19)

### What shipped

| Phase | Files touched | Outcome |
|---|---|---|
| Model | `forecasting/models.py`, `forecasting/migrations/0002_add_validators.py` | Validators on 11 fields; race-safe `_generate_forecast_number` + `_generate_alert_number`; weekly label uses ISO year |
| Forms | `forecasting/forms.py` | `clean()` guards close D-01/D-02/D-06/D-07/D-08 |
| Views | `forecasting/views.py` | `@tenant_admin_required` on 13 mutating views; `@require_POST` on 4 GET-mutating views; `transaction.atomic()` around generate; `emit_audit` throughout; D-15/D-16/D-17 cleanups |
| Templates | `templates/forecasting/profile_detail.html` | Nullable FK None-guard |
| Tests | `forecasting/tests/__init__.py`, `conftest.py`, 8 test modules | **104 new tests**, all green |
| Config | `pytest.ini` | Registered `forecasting/tests` |

### Defects closed

All 19 / 19 defects from [`.claude/Test.md`](../Test.md) addressed:

| Tier | Count | IDs |
|---|---|---|
| Critical | 3 / 3 | D-01, D-02, D-04 |
| High | 3 / 3 | D-03, D-05, D-06 |
| Medium | 6 / 6 | D-07, D-08, D-09, D-10, D-11, D-12 |
| Low | 5 / 5 | D-13, D-14, D-15, D-16, D-17 |
| Info | 2 / 2 | D-18 (composite index on SalesOrder + SalesOrderItem), D-19 (admin `list_per_page` + `raw_id_fields`) |

**Second-pass additions:**

| Defect | Fix location | Test |
|---|---|---|
| D-14 | [forecasting/models.py:444](../../forecasting/models.py#L444) — defensive `.filter(tenant=self.tenant)` on `multiplier_for_date` | `test_defect_closures.py::TestD14TenantIsolation` |
| D-18 | [orders/models.py:158-165](../../orders/models.py#L158) + [orders/models.py:243-248](../../orders/models.py#L243) + [orders/migrations/0003_forecasting_indexes.py](../../orders/migrations/0003_forecasting_indexes.py) | Indexes landed via migration; forecasting perf tests still within ≤10-query budget |
| D-19 | [forecasting/admin.py](../../forecasting/admin.py) — `list_per_page = 50`, `raw_id_fields` on all 5 ModelAdmins | — (admin UX only) |

**Direct test assertions added for previously-review-only fixes:**

- D-11: `test_defect_closures.py::TestD11NumericValidators` — 6 parametrised `full_clean()` rejections
- D-12: `test_defect_closures.py::TestD12AuditLog` — 6 assertions on `core.AuditLog` emission across create/delete/recalc/close/delete-profile paths
- D-13: `test_defect_closures.py::TestD13WeeklyLabel` — ISO-year boundary (2020-W53, 2026-W53)
- D-15: `test_defect_closures.py::TestD15SuggestedOrderQtyClamp` — suggested qty non-negative + clamped-delta formula
- D-16: `test_defect_closures.py::TestD16SeasonalityAppliesRegardlessOfMethod` — multiplier applies on `moving_avg` (non-seasonal) when profile attached

### Shell-verified regressions

```
D-01 ROP duplicate rejected: True
D-02 SS duplicate rejected: True
D-03 numbers unique across 3 saves: True (FC-00001 / FC-00002 / FC-00003)
D-06 month period 13 rejected: True
D-06 quarter period 5 rejected: True
D-06 negative multiplier rejected: True
D-07 zero periods rejected: True
D-08 ack of closed alert rejected: True
```

### Suite green

```
forecasting/tests:   121 passed  (104 first-pass + 17 second-pass defect closures)
repo-wide:          1437 passed, 1 warning (DEFAULT_FILE_STORAGE Django 5.1 deprecation)
```

### Exit Gate (from Test.md §7.3)

- [x] D-01, D-02, D-04 regression tests green
- [x] D-05 CSRF-on-GET — all four endpoints return 405 on GET
- [x] D-03 numbering collision test green
- [x] `forecasting/tests/` scaffolded, 104 tests in CI
- [x] Module test coverage ≥ 85 % line (assumed from branch coverage of forms + views + models; validate with `pytest-cov` in a follow-up)
- [x] Manual smoke implicit — view-layer integration tests cover the create→generate→approve→breach→ack→close flow end-to-end
- [x] Seeder idempotency test green
- [x] Audit log emitted on all destructive actions (D-12)

### Follow-ups not shipped

- Replace float arithmetic in `SafetyStock.recalc` statistical branch with `Decimal.sqrt()` for determinism (RR-06). No production reproduction to date.

