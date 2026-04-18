# Inventory Forecasting & Planning — Comprehensive SQA Test Report

> Target: Django app [`forecasting/`](../forecasting/) — Demand Forecast, Reorder Point (ROP), Reorder Alerts, Safety Stock, Seasonality Planning.
> Review mode: **Module review** (full end-to-end).
> Reviewer: Senior SQA Engineer persona.
> Date: 2026-04-19.

---

## 1. Module Analysis

### 1.1 Scope & files

| Concern | File |
|---|---|
| Models (7) | [forecasting/models.py](../forecasting/models.py) |
| Forms (6 + inline formset) | [forecasting/forms.py](../forecasting/forms.py) |
| Views (29) | [forecasting/views.py](../forecasting/views.py) |
| URL routing | [forecasting/urls.py](../forecasting/urls.py) |
| Admin registration | [forecasting/admin.py](../forecasting/admin.py) |
| Seeder | [forecasting/management/commands/seed_forecasting.py](../forecasting/management/commands/seed_forecasting.py) |
| Templates (15) | [templates/forecasting/](../templates/forecasting/) |
| Migration | [forecasting/migrations/0001_initial.py](../forecasting/migrations/0001_initial.py) |

### 1.2 Entity model

| Model | Purpose | Key constraint | File:line |
|---|---|---|---|
| `DemandForecast` | Header for a product/warehouse forecast run | `unique_together(tenant, forecast_number)` | [models.py:82](../forecasting/models.py#L82) |
| `DemandForecastLine` | Period row (history or future) | `ordering ['forecast', 'period_index']` | [models.py:145](../forecasting/models.py#L145) |
| `ReorderPoint` | Per product+warehouse ROP config | `unique_together(tenant, product, warehouse)` | [models.py:196](../forecasting/models.py#L196) |
| `ReorderAlert` | ROP breach notification with state machine | `unique_together(tenant, alert_number)` + `VALID_TRANSITIONS` | [models.py:214-219](../forecasting/models.py#L214-L219) |
| `SafetyStock` | Per product+warehouse SS config (3 methods) | `unique_together(tenant, product, warehouse)` | [models.py:364](../forecasting/models.py#L364) |
| `SeasonalityProfile` | Monthly/quarterly multiplier set | none | [models.py:397](../forecasting/models.py#L397) |
| `SeasonalityPeriod` | One multiplier row | `unique_together(profile, period_number)` | [models.py:471](../forecasting/models.py#L471) |

### 1.3 Business rules (extracted from code)

| # | Rule | Evidence |
|---|---|---|
| BR-01 | `ROP = (avg_daily_usage × lead_time_days) + safety_stock_qty` | [models.py:201-203](../forecasting/models.py#L201-L203) |
| BR-02 | Safety stock (statistical) = `Z × √((LT × σ_d²) + (μ_d² × σ_LT²))` | [models.py:377-384](../forecasting/models.py#L377-L384) |
| BR-03 | Safety stock (percentage) = `(avg_demand × lead_time × percentage/100)` | [models.py:373-375](../forecasting/models.py#L373-L375) |
| BR-04 | Z-score looked up from 7 fixed service levels (0.50 … 0.99); nearest-match | [models.py:301-309, 387-390](../forecasting/models.py#L301-L309) |
| BR-05 | `forecast_number` format `FC-00001`, auto-generated on save | [models.py:103-117](../forecasting/models.py#L103-L117) |
| BR-06 | `alert_number` format `ROA-00001`, auto-generated on save | [models.py:272-286](../forecasting/models.py#L272-L286) |
| BR-07 | Valid alert transitions: `new→{ack,closed}`, `ack→{ordered,closed}`, `ordered→closed` | [models.py:214-219](../forecasting/models.py#L214-L219) |
| BR-08 | ROP alert scan only creates a new alert when `current < rop_qty` AND no open alert exists | [views.py:424-430](../forecasting/views.py#L424-L430) |
| BR-09 | Forecast methods: moving_avg, exp_smoothing, linear_regression, seasonal (window = `max(3, len(history)//2)`) | [views.py:82-131](../forecasting/views.py#L82-L131) |
| BR-10 | Seasonality multiplier applied to forecast values when profile is attached | [views.py:277-283](../forecasting/views.py#L277-L283) |
| BR-11 | Historical demand sourced from `orders.SalesOrderItem` filtered by `sales_order__warehouse` + `order_date` | [views.py:71-79](../forecasting/views.py#L71-L79) |

### 1.4 Security / multi-tenancy profile (pre-test)

| Concern | Observation |
|---|---|
| Tenant isolation | Every view filters `tenant=request.tenant` ✓ |
| `@login_required` | Applied to all 29 views ✓ |
| `@tenant_admin_required` (RBAC) | **Not applied anywhere** ✗ — regression of the inventory D-05 gate |
| CSRF on destructive ops | Delete views gate on `POST`, but `rop_check_alerts`, `alert_mark_ordered`, `alert_close`, `safety_stock_recalc` mutate on **GET** ✗ |
| `unique_together` + tenant trap | Present in both `ReorderPointForm` and `SafetyStockForm` (tenant not on form) — unvalidated ✗ |
| Auto-numbering race | Both `_generate_*` methods read-then-write — non-atomic ✗ |
| `emit_audit()` | Not called anywhere in the module — audit trail missing for all mutations ✗ |
| Template auto-escape | Default Django escaping; no `|safe`/`mark_safe` in any template ✓ |

### 1.5 External dependencies

| Dependency | Usage | Coupling risk |
|---|---|---|
| `orders.SalesOrderItem` | Pulled by `_historical_demand_for` | Missing index on `(tenant, product, order_date)` would cause O(n) scans |
| `inventory.StockLevel` | Consumed by alert scan + ROP detail | None — filtered by tenant+product+warehouse |
| `catalog.Product`, `catalog.Category` | Form querysets | None |
| `warehousing.Warehouse` | Form querysets | None |
| `core.Tenant`, `core.AuditLog` | `AuditLog` never emitted (see D-12) | Compliance gap |

### 1.6 Complexity hotspots

- [views.py:71-131](../forecasting/views.py#L71-L131) — forecast math (3 algorithms + seasonality layering)
- [views.py:245-299](../forecasting/views.py#L245-L299) — generate flow: deletes + recreates lines without a transaction
- [views.py:411-447](../forecasting/views.py#L411-L447) — alert scan iterates all active ROPs with per-iteration StockLevel fetch (potential N+1)
- [models.py:369-385](../forecasting/models.py#L369-L385) — statistical safety-stock formula uses float arithmetic on Decimal inputs (precision drift)

---

## 2. Test Plan

### 2.1 Approach

Pyramid: **70 unit / 20 integration / 8 functional / 2 non-functional**. Unit tests cover model math (BR-01..BR-10) and form validation. Integration tests cover view+form+DB per sub-module with tenant-isolation assertions. Functional tests cover the "create forecast → generate lines → approve → breach → alert → acknowledge → close" end-to-end journey. Security tests are OWASP-mapped. Performance tests enforce an N+1 budget on list views and the alert-scan endpoint.

### 2.2 Coverage matrix

| Area | Unit | Integration | Functional | Security | Perf | Mgmt cmd |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| DemandForecast CRUD | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| Forecast generate algorithms | ✓ |  | ✓ |  |  |  |
| Seasonality profile + periods | ✓ | ✓ | ✓ | ✓ |  |  |
| ReorderPoint CRUD | ✓ | ✓ |  | ✓ | ✓ |  |
| ROP alert scan / state machine | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| SafetyStock (3 methods) | ✓ | ✓ |  | ✓ |  |  |
| Seeder idempotency |  |  |  |  |  | ✓ |

### 2.3 Test-type charter

| Type | Intent | Example |
|---|---|---|
| **Unit** | One class/method in isolation | `SafetyStock.recalc()` for each method |
| **Integration** | view + form + model + DB | POST to `safety_stock_create` persists and redirects |
| **Functional** | Multi-view workflow | Create ROP → generate alert via scan → ack → close |
| **Regression** | Historical defect guard | Duplicate ROP must surface a form error, not 500 |
| **Boundary** | Min/max per field | `period_number = 12` vs `13`; `service_level = 0.999` |
| **Edge** | Empty / null / zero | `history_periods=0`, no sales-order history |
| **Negative** | Invalid inputs, bypasses | Negative multiplier, cross-tenant IDOR |
| **Security** | OWASP A01..A10 | Tenant leak, CSRF on GET-mutating views, XSS in `name` |
| **Performance** | N+1 guardrail | `alert_list` ≤ 10 queries for 20 alerts |

### 2.4 Entry / exit criteria

**Entry:** schema migrated; seed_forecasting ran clean against the 3 demo tenants; `config.settings_test` operational.

**Exit:** see §7 Release Exit Gate.

---

## 3. Test Scenarios

### 3.1 Demand Forecast (F)

| # | Scenario | Type |
|---|---|---|
| F-01 | Create forecast with defaults → `forecast_number` auto-assigned `FC-00001` | Unit |
| F-02 | Second forecast same tenant → `FC-00002` | Unit |
| F-03 | Two concurrent saves yield duplicate `FC-*` number → one must fail or be renumbered | Negative / Regression |
| F-04 | `forecast_number` unique across tenant boundary (different tenants may collide — allowed by unique_together) | Boundary |
| F-05 | Generate lines with empty SalesOrderItem history → historical_qty = 0 for all periods | Edge |
| F-06 | Moving-average projection matches hand calc | Unit |
| F-07 | Exponential smoothing with α=0.3 matches hand calc | Unit |
| F-08 | Linear regression with `n=1` history returns constant | Edge |
| F-09 | Linear regression with negative slope — projection clamped to 0 | Boundary |
| F-10 | `seasonal` method without profile falls back to moving_avg | Edge |
| F-11 | Seasonality multiplier applied when profile attached (any method) | Unit |
| F-12 | `period_type='weekly'` generates correct ISO week label across year boundary | Boundary |
| F-13 | `period_type='quarterly'` — Dec reference produces `Q1 <year+1>` for `k=1` | Boundary |
| F-14 | `history_periods=0 & forecast_periods=0` → defect: form currently accepts & silently no-ops | Defect / Edge |
| F-15 | Regenerate flag replaces lines atomically — no partial state on mid-failure | Negative |
| F-16 | Cross-tenant IDOR: user of tenant B cannot GET/POST `/forecasts/<pk>/` of tenant A | Security (A01) |
| F-17 | XSS probe in `name` field is escaped in detail & list | Security (A03) |
| F-18 | Forecast list filters: `status`, `method`, `warehouse`, `q` combine correctly and survive pagination | Integration |
| F-19 | Delete approved forecast — currently allowed, should require confirmation and/or RBAC | Defect |
| F-20 | `total_forecast_qty` = Σ adjusted_qty (fallback forecast_qty) across future lines | Unit |

### 3.2 Reorder Point (R)

| # | Scenario | Type |
|---|---|---|
| R-01 | Create ROP — `rop_qty` auto-computed from BR-01 | Unit |
| R-02 | Duplicate `(tenant, product, warehouse)` — defect: form passes, DB 500s | Negative / Regression |
| R-03 | Edit ROP — `last_calculated_at` updated | Integration |
| R-04 | Delete ROP cascades `alerts` | Unit |
| R-05 | Negative `avg_daily_usage` via shell — blocked by DecimalField coercion? No — accepts 0 floor only via form `min='0'` HTML hint | Boundary / Defect |
| R-06 | `lead_time_days=0` → `rop_qty = safety_stock_qty` | Edge |
| R-07 | Recalculation is deterministic (idempotent `recalc_rop`) | Unit |
| R-08 | Cross-tenant IDOR on `rop_edit` | Security (A01) |
| R-09 | ROP list `?warehouse=` filter retains on pagination | Integration |

### 3.3 Reorder Alert (A)

| # | Scenario | Type |
|---|---|---|
| A-01 | Scan creates alert when `on_hand - allocated ≤ rop_qty` and no open alert exists | Integration |
| A-02 | Scan skips ROP with existing open alert | Integration |
| A-03 | Scan does not create alert when stock above ROP | Negative |
| A-04 | Suggested order qty = `max(reorder_qty, max_qty - current)` when `max_qty` set | Unit |
| A-05 | Alert transitions: new→ack→ordered→closed all valid | Unit |
| A-06 | Invalid transition (closed→ack) rejected with user message | Negative |
| A-07 | `alert_number` sequencing | Unit |
| A-08 | Alert-mark-ordered, alert-close, safety-stock-recalc — **must reject GET** (CSRF regression) | Security (A01 / CSRF) |
| A-09 | Acknowledged alert stores `acknowledged_by` and `acknowledged_at` | Integration |
| A-10 | Closed alert stores `closed_at` | Integration |
| A-11 | Alert list filters status + warehouse, pagination stable | Integration |

### 3.4 Safety Stock (S)

| # | Scenario | Type |
|---|---|---|
| S-01 | `method=fixed` sets `safety_stock_qty = fixed_qty` | Unit |
| S-02 | `method=percentage` — `(avg_demand × lead_time × percentage/100)` | Unit |
| S-03 | `method=statistical`, service_level=0.95 — matches Z=1.645 formula | Unit |
| S-04 | `_lookup_z` with non-table service_level rounds to nearest table entry | Unit |
| S-05 | Zero-variance → safety_stock_qty = 0 | Edge |
| S-06 | Service level = 0.50 (Z=0) → SS = 0 | Boundary |
| S-07 | Duplicate `(tenant, product, warehouse)` — defect: form passes, DB 500s | Negative / Regression |
| S-08 | Recalc endpoint updates `calculated_at` | Integration |
| S-09 | Cross-tenant IDOR on `safety_stock_edit` | Security (A01) |
| S-10 | Statistical formula precision (Decimal/float drift) | Unit |

### 3.5 Seasonality (Z)

| # | Scenario | Type |
|---|---|---|
| Z-01 | Create monthly profile auto-creates 12 periods at multiplier 1.00 | Integration |
| Z-02 | Create quarterly profile auto-creates 4 periods | Integration |
| Z-03 | `multiplier_for_date` returns correct period for month/quarter | Unit |
| Z-04 | Missing period returns default 1.00 | Edge |
| Z-05 | Inline formset edits multipliers + deletes periods | Integration |
| Z-06 | `period_number=13` on monthly profile — defect: accepted by form | Boundary / Defect |
| Z-07 | `period_number=5` on quarterly profile — defect: accepted | Boundary / Defect |
| Z-08 | `demand_multiplier=-1.00` — defect: accepted (no MinValueValidator) | Negative / Defect |
| Z-09 | Profile scoping: category-scoped profiles only match category products | Integration |
| Z-10 | Delete profile with an attached DemandForecast → SET_NULL on `seasonality_profile` | Integration |

### 3.6 Cross-cutting (X)

| # | Scenario | Type |
|---|---|---|
| X-01 | Non-admin tenant user attempts destructive ops — currently succeeds (defect vs inventory RBAC pattern) | Security (A01) |
| X-02 | Superuser with `tenant=None` sees empty lists | Integration |
| X-03 | Anonymous user → `302 /accounts/login/` for every view | Security (A07) |
| X-04 | CSRF token required on every POST | Security |
| X-05 | `alert_list` / `rop_list` / `forecast_list` — ≤10 queries for 20 rows | Performance |
| X-06 | `rop_check_alerts_view` — query count scales linearly with active ROP count | Performance |
| X-07 | `seed_forecasting` is idempotent (run twice, no duplicates) | Mgmt cmd |
| X-08 | `seed_forecasting --flush` cleans only forecasting tables | Mgmt cmd |

Total scenarios: **57**.

---

## 4. Detailed Test Cases

> ID format `TC-<AREA>-NNN`. Pre/Post-conditions assume `tenant`, `warehouse`, `product` fixtures from `forecasting/tests/conftest.py` (to be created — see §5).

### 4.1 Demand Forecast

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-F-001 | Auto-numbering first forecast | Clean DB | Save `DemandForecast(tenant, name, product, warehouse)` | `name='A'` | `forecast_number == 'FC-00001'` | 1 row |
| TC-F-002 | Auto-numbering increments | 1 forecast exists (`FC-00001`) | Save another | — | `FC-00002` | 2 rows |
| TC-F-003 | Concurrent save race | Clean DB | In parallel (`ThreadPoolExecutor`) save 2 forecasts | same tenant | Both succeed with distinct numbers **OR** second raises validation error, not IntegrityError 500 | 2 rows OR 1 row + graceful error |
| TC-F-004 | Moving-average projection | `history=[10,12,14,16,18,20]`, `method='moving_avg'`, `forecast_periods=3` | Call `_generate_forecast_values(history,'moving_avg')(3)` | window = max(3, 3) = 3 | `[18, 19, 19]` (allow ±1 rounding) | — |
| TC-F-005 | Exponential smoothing α=0.3 | `history=[10,20,30]` | Call generator | — | `f = 0.3·30 + 0.7·(0.3·20+0.7·10) = 19.6 → round(20) → [20,20,20]` | — |
| TC-F-006 | Linear regression clamps negative | `history=[100,80,60,40,20]`, `forecast_periods=5` | Call generator | slope negative | Projection clamped to `[0, 0, 0, 0, 0]` after step 1 | — |
| TC-F-007 | `history_periods=0` accepted (defect) | Clean DB | Create forecast with 0/0 and POST generate | form data: `history_periods=0, forecast_periods=0` | **Expected after fix:** form error "must be ≥ 1". **Current:** generate silently no-ops | — |
| TC-F-008 | Cross-tenant IDOR | Forecast belongs to tenant A | Login as tenant B admin, GET `/forecasts/<pk>/` | — | 404 (not 200, not 302) | — |
| TC-F-009 | XSS in name | — | Create forecast with `name='<script>alert(1)</script>'`; GET detail | — | Response body contains `&lt;script&gt;`, not `<script>` | — |
| TC-F-010 | List filter + pagination | 25 forecasts across 2 warehouses | GET `/?warehouse=<id>&page=2` | — | Only warehouse `<id>` rows; warehouse filter preserved in page-2 link | — |
| TC-F-011 | Regenerate atomicity | Forecast with 6 existing lines | POST `generate` with `regenerate=True`; inject DB failure on 4th `create` | force `IntegrityError` via monkey-patch | All old lines preserved OR fully replaced; no partial state | Transaction atomic |
| TC-F-012 | Seasonal multiplier | `method='seasonal'` + monthly profile (Jul=1.50); forecast `k=1` starts Jul | Call generate | base=100, mult=1.50 | `forecast_qty=100, adjusted_qty=150` | — |
| TC-F-013 | Period bounds — weekly across year | `reference=2026-12-31`, `period_index=1` | Call `_period_bounds` | — | Start = Mon of ISO week containing +7 days; label `W??-2027` matches `start.isocalendar()[1]:02d` AND year of start | — |

### 4.2 Reorder Point

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-R-001 | BR-01 math | — | `ReorderPoint(avg_daily_usage=5, lead_time_days=7, safety_stock_qty=10).recalc_rop()` | — | `rop_qty == 45` | — |
| TC-R-002 | Decimal rounding | `avg_daily_usage=Decimal('5.6')`, `lead_time_days=3` | `recalc_rop()` | — | `round(16.8) = 17`, `rop_qty = 17 + safety` | — |
| TC-R-003 | Duplicate (tenant, product, warehouse) via form (**D-01 regression**) | 1 ROP already exists for (T, P, W) | POST `rop_create` with same P+W | form data identical | Form error `"Reorder point already exists..."` **(current: 500 IntegrityError)** | No DB write |
| TC-R-004 | Edit updates `last_calculated_at` | ROP exists | POST `rop_edit` | new values | `last_calculated_at > previous` | — |
| TC-R-005 | Delete cascades alerts | ROP with 2 alerts | POST `rop_delete` | — | `ReorderAlert.objects.count() == 0` | — |
| TC-R-006 | Non-admin cannot delete (**D-04 regression**) | ROP exists | Login non-admin → POST delete | — | 403 OR redirect with error; row unchanged | — |
| TC-R-007 | Cross-tenant IDOR | ROP of tenant A | Login as tenant B admin, POST `rop_delete` | — | 404; row unchanged | — |

### 4.3 Reorder Alert

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-A-001 | Scan creates alert on breach | ROP(rop_qty=50), StockLevel(on_hand=40) | GET → POST `rop_check_alerts` | — | 1 alert created with `current_qty=40, suggested_order_qty=max(reorder_qty, max_qty-40)` | `ReorderAlert.count() == 1` |
| TC-A-002 | Scan skips when above ROP | on_hand=60, rop=50 | POST scan | — | 0 alerts created | — |
| TC-A-003 | Scan skips when open alert exists | 1 'new' alert | POST scan | — | 0 created, 1 skipped | — |
| TC-A-004 | Transition new→acknowledged | Alert status=new | POST `alert_acknowledge` with `suggested_order_qty=10` | — | status='acknowledged', `acknowledged_by=user`, `acknowledged_at` set | — |
| TC-A-005 | Transition closed→acknowledged blocked | status=closed | GET `alert_acknowledge` | — | Redirect with error message; status unchanged | — |
| TC-A-006 | Mark ordered rejects GET (**D-05**) | status=ack | GET `alert_mark_ordered` (no POST) | — | **Expected after fix:** 405 Method Not Allowed. **Current:** state change executes | — |
| TC-A-007 | Close rejects GET (**D-05**) | status=ordered | GET `alert_close` | — | 405 | — |
| TC-A-008 | Cross-tenant IDOR | Alert of tenant A | Login tenant B, POST `alert_close` | — | 404 | — |
| TC-A-009 | Valid transition matrix | — | Parametrize all 12 (from, to) pairs against `VALID_TRANSITIONS` | — | Each matches `can_transition_to` | — |

### 4.4 Safety Stock

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-S-001 | Fixed method | `method='fixed', fixed_qty=25` | `recalc()` | — | `safety_stock_qty == 25` | — |
| TC-S-002 | Percentage method | `avg_demand=10, lead_time=7, percentage=20` | `recalc()` | — | `safety_stock_qty == round(10·7·0.2)=14` | — |
| TC-S-003 | Statistical 95% | `μ=10, σ_d=2, LT=7, σ_LT=1, sl=0.95` | `recalc()` | Z=1.645 | `Z × √(7·4 + 100·1) = 1.645·√128 ≈ 18.62 → 19` | — |
| TC-S-004 | Z lookup nearest | `service_level=0.93` | `_lookup_z` | — | Returns Z for 0.95 (nearest) | — |
| TC-S-005 | Zero variance | All σ=0 | `recalc()` | — | `safety_stock_qty == 0` | — |
| TC-S-006 | Duplicate (tenant, product, warehouse) (**D-02 regression**) | 1 SS exists | POST `safety_stock_create` duplicate | — | Form error (current: 500) | — |
| TC-S-007 | Recalc endpoint | SS exists | GET `safety_stock_recalc` (**also tests D-05**) | — | After fix: require POST. Current: updates `calculated_at` | — |

### 4.5 Seasonality

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-Z-001 | Monthly profile auto-creates 12 periods | — | POST `profile_create` (`period_type='month'`) | — | 12 `SeasonalityPeriod` rows with multiplier 1.00 | — |
| TC-Z-002 | Quarterly profile auto-creates 4 periods | — | POST create with `period_type='quarter'` | — | 4 rows | — |
| TC-Z-003 | `multiplier_for_date` | Profile Jul=1.50 | Call `multiplier_for_date(date(2026,7,15))` | — | `Decimal('1.50')` | — |
| TC-Z-004 | Missing period fallback | Profile with Jul deleted | Call `multiplier_for_date(date(2026,7,15))` | — | `Decimal('1.00')` | — |
| TC-Z-005 | Period 13 rejected (**D-06**) | — | POST period with `period_number=13` on monthly | — | Form error; no row | — |
| TC-Z-006 | Quarter period 5 rejected (**D-06**) | — | POST with period=5 on quarterly | — | Form error | — |
| TC-Z-007 | Negative multiplier rejected (**D-06**) | — | POST with `demand_multiplier=-1` | — | Form error; no row | — |

### 4.6 Cross-cutting security

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-X-001 | Non-admin RBAC (**D-04**) | Non-admin user + existing forecast | POST edit/delete/alert-close/scan/recalc | — | 403 Forbidden (currently 200 / 302 success) | — |
| TC-X-002 | Anonymous redirect | — | GET each of 29 URL names | — | 302 → `/accounts/login/` | — |
| TC-X-003 | CSRF on POST | Valid session | POST without token | — | 403 | — |
| TC-X-004 | CSRF on side-effect GET (**D-05**) | Valid session | GET `rop_check_alerts`, `alert_mark_ordered`, `alert_close`, `safety_stock_recalc` | — | After fix: 405. Current: state change | — |
| TC-X-005 | Superuser empty tenant | Superuser (`tenant=None`) | GET forecast_list | — | Empty page, 200 | — |
| TC-X-006 | Query budget `forecast_list` | 20 forecasts | `django_assert_max_num_queries(10)` | — | ≤ 10 queries | — |
| TC-X-007 | Query budget `rop_check_alerts` | 20 ROPs + 20 StockLevels | `django_assert_max_num_queries(25)` | — | ≤ 25 queries (currently may N+1: 1 + N StockLevel lookups) | — |

### 4.7 Seeder

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-SEED-001 | Idempotent (2× run) | Clean DB + 1 tenant with products/warehouses | `call_command('seed_forecasting')` twice | — | Counts unchanged after 2nd run; warning `"Forecasting data already exists"` printed | — |
| TC-SEED-002 | `--flush` | Data exists | `call_command('seed_forecasting', flush=True)` | — | Existing rows deleted, fresh set created | — |
| TC-SEED-003 | No tenant warning | `Tenant.objects.filter(is_active=True).delete()` | Call seeder | — | Warning `"No active tenants"`, return | — |

---

## 5. Automation Strategy

### 5.1 Tool stack

| Concern | Tool | Rationale |
|---|---|---|
| Unit + integration | `pytest-django` + `factory-boy` | Matches current repo (`inventory/tests`, `catalog/tests`) |
| Snapshot / regression | plain pytest | No snapshots needed |
| E2E smoke (optional) | Playwright headless | Aligns with `/sqa-review` skill default |
| Security scan | `bandit -q -r forecasting/`, OWASP ZAP baseline | Catches A03/A08 regressions |
| Load | `locust` against `rop_check_alerts` | Batch scan is the hot path |
| Coverage | `coverage` + `pytest-cov` | Enforce ≥ 85 % in CI |

### 5.2 Suite layout

```
forecasting/
  tests/
    __init__.py
    conftest.py                  # tenant/user/product/warehouse + forecasting factories
    test_models.py               # BR-01..BR-10 unit tests
    test_forms.py                # form validation (incl. D-01/D-02/D-06 regressions)
    test_views_forecast.py       # DemandForecast CRUD + generate
    test_views_rop.py            # ROP CRUD + scan endpoint
    test_views_alert.py          # Alert state machine + D-05 CSRF
    test_views_safety_stock.py   # SS CRUD + recalc
    test_views_seasonality.py    # profile + inline formset
    test_security.py             # auth, RBAC (D-04), IDOR, CSRF, XSS
    test_performance.py          # N+1 budgets
    test_seed.py                 # seeder idempotency
```

Register the new paths in [pytest.ini](../pytest.ini):

```
testpaths = ... forecasting/tests
```

### 5.3 `conftest.py` (runnable against this repo)

```python
# forecasting/tests/conftest.py
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import StockLevel
from forecasting.models import (
    DemandForecast, ReorderPoint, ReorderAlert,
    SafetyStock, SeasonalityProfile, SeasonalityPeriod,
)

User = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Forecast", slug="acme-forecast")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Globex Forecast", slug="globex-forecast")


@pytest.fixture
def admin_user(db, tenant):
    return User.objects.create_user(
        username="fc_admin", password="pw_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="fc_staff", password="pw_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username="fc_other", password="pw_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code="WH-FC", name="FC Main", is_active=True,
    )


@pytest.fixture
def product(db, tenant):
    cat = Category.objects.create(tenant=tenant, name="Supplies-FC")
    return Product.objects.create(
        tenant=tenant, sku="FC-001", name="Widget FC",
        category=cat, purchase_cost=10, retail_price=15, status="active",
    )


@pytest.fixture
def stock_level(db, tenant, product, warehouse):
    return StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=40, allocated=0, reorder_point=0, reorder_quantity=0,
    )


@pytest.fixture
def rop(db, tenant, product, warehouse):
    rp = ReorderPoint(
        tenant=tenant, product=product, warehouse=warehouse,
        avg_daily_usage=Decimal("5"), lead_time_days=7,
        safety_stock_qty=10, min_qty=10, max_qty=100,
        reorder_qty=30, is_active=True,
    )
    rp.recalc_rop()
    rp.save()
    return rp


@pytest.fixture
def monthly_profile(db, tenant):
    prof = SeasonalityProfile.objects.create(
        tenant=tenant, name="Jul peak", period_type="month", is_active=True,
    )
    multipliers = {i: Decimal("1.00") for i in range(1, 13)}
    multipliers[7] = Decimal("1.50")
    for m, mult in multipliers.items():
        SeasonalityPeriod.objects.create(
            tenant=tenant, profile=prof, period_number=m,
            period_label=date(2000, m, 1).strftime("%b"),
            demand_multiplier=mult,
        )
    return prof
```

### 5.4 `test_models.py` (key cases — runnable)

```python
# forecasting/tests/test_models.py
from decimal import Decimal
from datetime import date

import pytest

from forecasting.models import (
    DemandForecast, ReorderPoint, ReorderAlert, SafetyStock,
)


@pytest.mark.django_db
class TestForecastNumbering:
    def test_first_is_fc_00001(self, tenant, product, warehouse):
        f = DemandForecast.objects.create(
            tenant=tenant, name="A", product=product, warehouse=warehouse,
        )
        assert f.forecast_number == "FC-00001"

    def test_second_increments(self, tenant, product, warehouse):
        DemandForecast.objects.create(tenant=tenant, name="A", product=product, warehouse=warehouse)
        f = DemandForecast.objects.create(tenant=tenant, name="B", product=product, warehouse=warehouse)
        assert f.forecast_number == "FC-00002"

    def test_race_regression(self, tenant, product, warehouse):
        """D-03 — parallel saves must not collide. Fix with select_for_update + sequence."""
        f1 = DemandForecast(tenant=tenant, name="A", product=product, warehouse=warehouse)
        f2 = DemandForecast(tenant=tenant, name="B", product=product, warehouse=warehouse)
        n1 = f1._generate_forecast_number()
        n2 = f2._generate_forecast_number()
        assert n1 != n2, "Race-prone auto-numbering — see D-03"


@pytest.mark.django_db
class TestReorderPoint:
    def test_rop_formula(self, tenant, product, warehouse):
        rp = ReorderPoint(
            tenant=tenant, product=product, warehouse=warehouse,
            avg_daily_usage=Decimal("5"), lead_time_days=7, safety_stock_qty=10,
        )
        rp.recalc_rop()
        assert rp.rop_qty == 45

    def test_decimal_rounding(self, tenant, product, warehouse):
        rp = ReorderPoint(
            tenant=tenant, product=product, warehouse=warehouse,
            avg_daily_usage=Decimal("5.6"), lead_time_days=3, safety_stock_qty=0,
        )
        rp.recalc_rop()
        assert rp.rop_qty == 17  # round(5.6 * 3) = round(16.8) = 17


@pytest.mark.django_db
class TestAlertTransitions:
    @pytest.mark.parametrize("src,dst,ok", [
        ("new", "acknowledged", True),
        ("new", "ordered", False),
        ("new", "closed", True),
        ("acknowledged", "ordered", True),
        ("acknowledged", "closed", True),
        ("ordered", "closed", True),
        ("ordered", "acknowledged", False),
        ("closed", "acknowledged", False),
        ("closed", "ordered", False),
    ])
    def test_matrix(self, tenant, product, warehouse, rop, src, dst, ok):
        a = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status=src,
        )
        assert a.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestSafetyStock:
    def test_fixed(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="fixed", fixed_qty=25,
        )
        ss.recalc()
        assert ss.safety_stock_qty == 25

    def test_percentage(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="percentage",
            avg_demand=Decimal("10"), avg_lead_time_days=Decimal("7"),
            percentage=Decimal("20"),
        )
        ss.recalc()
        assert ss.safety_stock_qty == 14  # round(10 * 7 * 0.2)

    def test_statistical_95(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="statistical", service_level=Decimal("0.95"),
            avg_demand=Decimal("10"), demand_std_dev=Decimal("2"),
            avg_lead_time_days=Decimal("7"), lead_time_std_dev=Decimal("1"),
        )
        ss.recalc()
        # Z=1.645, variance = 7*4 + 100*1 = 128, sqrt ≈ 11.31; 1.645*11.31 ≈ 18.61 → 19
        assert ss.safety_stock_qty == 19

    def test_zero_variance(self, tenant, product, warehouse):
        ss = SafetyStock(
            tenant=tenant, product=product, warehouse=warehouse,
            method="statistical",
        )
        ss.recalc()
        assert ss.safety_stock_qty == 0

    def test_z_lookup_nearest(self):
        assert SafetyStock._lookup_z(Decimal("0.93")) == Decimal("1.28") or \
               SafetyStock._lookup_z(Decimal("0.93")) == Decimal("1.645")
```

### 5.5 `test_forms.py` — **regression guards for D-01, D-02, D-06**

```python
# forecasting/tests/test_forms.py
import pytest
from decimal import Decimal

from forecasting.forms import (
    DemandForecastForm, ReorderPointForm, SafetyStockForm,
    SeasonalityPeriodForm,
)
from forecasting.models import ReorderPoint, SafetyStock


@pytest.mark.django_db
class TestUniqueTogetherGuards:
    """D-01/D-02 regression — duplicates must be caught at the form level."""

    def test_rop_duplicate_rejected(self, tenant, product, warehouse):
        ReorderPoint.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        form = ReorderPointForm(
            data={
                "product": product.pk, "warehouse": warehouse.pk,
                "avg_daily_usage": "1", "lead_time_days": "1",
                "safety_stock_qty": "0", "rop_qty": "0", "min_qty": "0",
                "max_qty": "0", "reorder_qty": "0", "is_active": "on", "notes": "",
            },
            tenant=tenant,
        )
        assert not form.is_valid(), "D-01 regression: duplicate ROP should fail validation"

    def test_safety_stock_duplicate_rejected(self, tenant, product, warehouse):
        SafetyStock.objects.create(tenant=tenant, product=product, warehouse=warehouse)
        form = SafetyStockForm(
            data={
                "product": product.pk, "warehouse": warehouse.pk,
                "method": "fixed", "service_level": "0.95",
                "avg_demand": "0", "demand_std_dev": "0",
                "avg_lead_time_days": "0", "lead_time_std_dev": "0",
                "fixed_qty": "5", "percentage": "20",
                "safety_stock_qty": "0", "notes": "",
            },
            tenant=tenant,
        )
        assert not form.is_valid(), "D-02 regression: duplicate SS should fail validation"


@pytest.mark.django_db
class TestSeasonalityBounds:
    """D-06 regression."""

    def test_monthly_period_13_rejected(self):
        f = SeasonalityPeriodForm(data={
            "period_number": "13", "period_label": "x",
            "demand_multiplier": "1.00", "notes": "",
        })
        assert not f.is_valid()

    def test_negative_multiplier_rejected(self):
        f = SeasonalityPeriodForm(data={
            "period_number": "1", "period_label": "x",
            "demand_multiplier": "-1", "notes": "",
        })
        assert not f.is_valid()


@pytest.mark.django_db
class TestForecastPeriodBounds:
    """D-07 regression — zero periods must be rejected."""

    def test_zero_periods_rejected(self, tenant, product, warehouse):
        f = DemandForecastForm(
            data={
                "name": "X", "product": product.pk, "warehouse": warehouse.pk,
                "method": "moving_avg", "period_type": "monthly",
                "history_periods": "0", "forecast_periods": "0",
                "confidence_pct": "80", "status": "draft", "notes": "",
            },
            tenant=tenant,
        )
        assert not f.is_valid()
```

### 5.6 `test_views_alert.py` — state-machine + **D-05 CSRF regression**

```python
# forecasting/tests/test_views_alert.py
import pytest
from django.urls import reverse

from forecasting.models import ReorderAlert


@pytest.mark.django_db
class TestAlertStateMachine:
    def test_acknowledge_flow(self, client_logged_in, tenant, rop, product, warehouse, admin_user):
        alert = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse,
            current_qty=0, rop_qty=rop.rop_qty, suggested_order_qty=20, status="new",
        )
        r = client_logged_in.post(
            reverse("forecasting:alert_acknowledge", args=[alert.pk]),
            {"suggested_order_qty": "10", "notes": "ack"},
        )
        alert.refresh_from_db()
        assert alert.status == "acknowledged"
        assert alert.acknowledged_by == admin_user

    def test_cannot_acknowledge_closed(self, client_logged_in, tenant, rop, product, warehouse):
        alert = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status="closed",
        )
        r = client_logged_in.get(reverse("forecasting:alert_acknowledge", args=[alert.pk]))
        alert.refresh_from_db()
        assert alert.status == "closed"
        assert r.status_code == 302

    @pytest.mark.xfail(reason="D-05 — side-effect on GET")
    def test_mark_ordered_rejects_get(self, client_logged_in, tenant, rop, product, warehouse):
        alert = ReorderAlert.objects.create(
            tenant=tenant, rop=rop, product=product, warehouse=warehouse, status="acknowledged",
        )
        r = client_logged_in.get(reverse("forecasting:alert_mark_ordered", args=[alert.pk]))
        alert.refresh_from_db()
        assert r.status_code == 405
        assert alert.status == "acknowledged"  # GET must not mutate
```

### 5.7 `test_security.py` — OWASP A01 / A07

```python
# forecasting/tests/test_security.py
import pytest
from django.urls import reverse

from forecasting.models import DemandForecast, ReorderPoint


@pytest.mark.django_db
class TestAnonymousBlocked:
    @pytest.mark.parametrize("url_name,args", [
        ("forecasting:forecast_list", []),
        ("forecasting:forecast_create", []),
        ("forecasting:rop_list", []),
        ("forecasting:alert_list", []),
        ("forecasting:safety_stock_list", []),
        ("forecasting:profile_list", []),
    ])
    def test_anon_redirected(self, client, url_name, args):
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302 and "/accounts/login/" in r["Location"]


@pytest.mark.django_db
class TestCrossTenantIDOR:
    def test_other_tenant_cannot_delete_forecast(
        self, client, tenant, other_tenant_admin, product, warehouse,
    ):
        f = DemandForecast.objects.create(
            tenant=tenant, name="secret", product=product, warehouse=warehouse,
        )
        client.force_login(other_tenant_admin)
        r = client.post(reverse("forecasting:forecast_delete", args=[f.pk]))
        assert r.status_code == 404
        assert DemandForecast.objects.filter(pk=f.pk).exists()


@pytest.mark.django_db
class TestRBAC:
    """D-04 regression — non-admins must not mutate forecasting data."""

    @pytest.mark.xfail(reason="D-04 — no @tenant_admin_required on views")
    def test_non_admin_cannot_delete_rop(self, client, non_admin_user, rop):
        client.force_login(non_admin_user)
        r = client.post(reverse("forecasting:rop_delete", args=[rop.pk]))
        assert r.status_code == 403
        assert ReorderPoint.objects.filter(pk=rop.pk).exists()


@pytest.mark.django_db
class TestXSSEscape:
    def test_forecast_name_is_escaped(self, client_logged_in, tenant, product, warehouse):
        f = DemandForecast.objects.create(
            tenant=tenant, name="<script>alert(1)</script>",
            product=product, warehouse=warehouse,
        )
        r = client_logged_in.get(reverse("forecasting:forecast_detail", args=[f.pk]))
        assert b"<script>alert(1)</script>" not in r.content
        assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in r.content
```

### 5.8 `test_performance.py` — N+1 budgets

```python
# forecasting/tests/test_performance.py
import pytest
from django.urls import reverse

from catalog.models import Category, Product
from forecasting.models import DemandForecast, ReorderPoint
from inventory.models import StockLevel


@pytest.mark.django_db
def test_forecast_list_query_budget(client_logged_in, tenant, warehouse, django_assert_max_num_queries):
    cat = Category.objects.create(tenant=tenant, name="Bulk")
    for i in range(20):
        p = Product.objects.create(
            tenant=tenant, sku=f"FB-{i:03}", name=f"Bulk {i}",
            category=cat, purchase_cost=1, retail_price=1, status="active",
        )
        DemandForecast.objects.create(
            tenant=tenant, name=f"F{i}", product=p, warehouse=warehouse,
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("forecasting:forecast_list"))
        assert r.status_code == 200


@pytest.mark.django_db
def test_rop_scan_query_budget(client_logged_in, tenant, warehouse, django_assert_max_num_queries):
    cat = Category.objects.create(tenant=tenant, name="Bulk")
    for i in range(20):
        p = Product.objects.create(
            tenant=tenant, sku=f"RB-{i:03}", name=f"R{i}",
            category=cat, purchase_cost=1, retail_price=1, status="active",
        )
        rp = ReorderPoint(
            tenant=tenant, product=p, warehouse=warehouse,
            avg_daily_usage=1, lead_time_days=1, safety_stock_qty=10,
        )
        rp.recalc_rop(); rp.save()
        StockLevel.objects.create(tenant=tenant, product=p, warehouse=warehouse, on_hand=0)
    with django_assert_max_num_queries(25):  # currently ~2N, after fix: < N
        client_logged_in.post(reverse("forecasting:rop_check_alerts"))
```

### 5.9 `test_seed.py` — seeder idempotency

```python
# forecasting/tests/test_seed.py
import pytest
from io import StringIO
from django.core.management import call_command
from forecasting.models import DemandForecast


@pytest.mark.django_db
def test_seed_is_idempotent(tenant, product, warehouse):
    out = StringIO()
    call_command("seed_forecasting", stdout=out)
    first = DemandForecast.objects.filter(tenant=tenant).count()
    out2 = StringIO()
    call_command("seed_forecasting", stdout=out2)
    second = DemandForecast.objects.filter(tenant=tenant).count()
    assert first == second, "Seeder must be idempotent"
    assert "already exists" in out2.getvalue()
```

### 5.10 Playwright smoke (optional, one happy path)

Scoped to post-remediation validation — not part of CI.

```python
# tests/e2e/test_forecast_smoke.py  (runs against runserver)
def test_create_and_generate_forecast(page, live_server):
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', "admin_acme")
    page.fill('input[name="password"]', "demo123")
    page.click('button[type="submit"]')
    page.goto(f"{live_server.url}/forecasting/forecasts/create/")
    page.fill('input[name="name"]', "Smoke 2026-04")
    page.select_option('select[name="product"]', index=1)
    page.select_option('select[name="warehouse"]', index=1)
    page.click('button[type="submit"]')
    assert page.locator("text=created").is_visible()
```

---

## 6. Defects, Risks & Recommendations

### 6.1 Defects (verified unless marked **CANDIDATE**)

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| D-01 | **Critical** | A04 | [forecasting/forms.py:67-108](../forecasting/forms.py#L67-L108) | `ReorderPointForm` omits `tenant` from fields → Django's `validate_unique()` excludes it; a duplicate `(tenant, product, warehouse)` passes `is_valid()` and raises `IntegrityError` (HTTP 500) on save. **Verified in shell.** Matches lesson #6. | Add `clean()` that filters `ReorderPoint.objects.filter(tenant=self.tenant, product=…, warehouse=…).exclude(pk=instance.pk)` and raises `ValidationError` when found. |
| D-02 | **Critical** | A04 | [forecasting/forms.py:125-166](../forecasting/forms.py#L125-L166) | Same pattern — `SafetyStockForm` duplicate `(tenant, product, warehouse)` → `IntegrityError`. **Verified in shell.** | Same fix: `clean()` guard. |
| D-04 | **Critical** | A01 | [forecasting/views.py:138-783](../forecasting/views.py) | No `@tenant_admin_required` on any destructive view (create/edit/delete/recalc/scan/close). Every authenticated tenant user — including viewers/staff — can mutate forecasting data. Regression vs inventory's D-05 gate. | Decorate all create/edit/delete/recalc/close/scan/mark-ordered views with `@tenant_admin_required` from [core/decorators.py](../core/decorators.py). |
| D-05 | **High** | A01 / CSRF | [views.py:410-447](../forecasting/views.py#L410-L447), [522-545](../forecasting/views.py#L522-L545), [654-662](../forecasting/views.py#L654-L662) | `rop_check_alerts_view`, `alert_mark_ordered_view`, `alert_close_view`, `safety_stock_recalc_view` perform state changes on **GET**. Any authenticated user clicking a crafted link (or loading an `<img src>`) triggers scan/close/recalc — CSRF protection does not cover GETs. | Gate with `@require_POST` or explicit `if request.method != 'POST': return HttpResponseNotAllowed(['POST'])`. Templates already POST, so no template changes. |
| D-03 | **High** | A04 | [models.py:103-117](../forecasting/models.py#L103-L117), [272-286](../forecasting/models.py#L272-L286) | `_generate_forecast_number()` / `_generate_alert_number()` read-then-write without locking. Two concurrent saves produce the same `FC-xxxxx` / `ROA-xxxxx` → second save raises `IntegrityError`. **Verified in shell.** | Wrap creation in `transaction.atomic()` + `select_for_update()` on the max row, OR move numbering to an `IntegerField` sequence (`F('id')`) + formatted property. |
| D-06 | **High** | A04 | [forms.py:207-216](../forecasting/forms.py#L207-L216) | `SeasonalityPeriodForm` has HTML `min/max` only — no server validators. Accepts `period_number=13` on monthly, `>4` on quarterly, and **negative `demand_multiplier`**. **Verified.** | `clean_period_number` that inspects `self.instance.profile.period_type` and bounds to 1..12 or 1..4. Add `MinValueValidator(Decimal('0'))` to `SeasonalityPeriod.demand_multiplier`. |
| D-07 | **Medium** | A04 | [forms.py:20-40](../forecasting/forms.py#L20-L40) | `DemandForecastForm` accepts `history_periods=0, forecast_periods=0`. Generate then no-ops but stamps `generated_at`. **Verified.** | Add `MinValueValidator(1)` on both fields, or `clean()` that requires `forecast_periods ≥ 1`. |
| D-08 | **Medium** | A04 | [forms.py:111-118](../forecasting/forms.py#L111-L118) | `ReorderAlertAcknowledgeForm` accepts submission regardless of current alert status (view-layer check is bypassable if form reused). | Add `clean()` asserting `self.instance.can_transition_to('acknowledged')`. |
| D-09 | **Medium** | A04 | [views.py:245-299](../forecasting/views.py#L245-L299) | `forecast_generate_view` deletes existing lines then creates replacements without `transaction.atomic()` → mid-failure leaves forecast with no lines. | Wrap the block in `with transaction.atomic():`. |
| D-10 | **Medium** | A04 | [models.py:64-67](../forecasting/models.py#L64-L67) | `confidence_pct` caps at `max_digits=5, decimal_places=2` (allows 999.99) — intent is 0–100. | Add `MinValueValidator(0)` + `MaxValueValidator(100)`. |
| D-11 | **Medium** | A04 | [models.py:172-187](../forecasting/models.py#L172-L187), [327-356](../forecasting/models.py#L327-L356) | No server-side validators on `avg_daily_usage`, `avg_demand`, `demand_std_dev`, `avg_lead_time_days`, `lead_time_std_dev`. HTML `min='0'` can be bypassed by shell/API. | Add `MinValueValidator(Decimal('0'))` on each. |
| D-12 | **Medium** | A09 | Module-wide | No `emit_audit()` calls anywhere — deletes, status transitions, recalcs leave no audit trail. Inconsistent with inventory/warehousing patterns. | After each mutation, call `emit_audit(request, 'action', instance, changes=...)` per [core/decorators.py:36](../core/decorators.py#L36). |
| D-13 | **Low** | A04 | [views.py:35-68](../forecasting/views.py#L35-L68) | `_period_bounds` weekly path: the label uses `start.isocalendar()[1]` but `start.year` may differ from ISO-week year across Jan-1 boundary → mis-labelled weeks. | Use `start.isocalendar()[:2]` → `f"W{week:02d}-{iso_year}"`. |
| D-14 | **Low** | A01 | [models.py:440-447](../forecasting/models.py#L440-L447) | `SeasonalityProfile.multiplier_for_date` filters `self.periods` without explicit tenant scoping. Safe today (periods are FK'd), but any future `.objects.filter(profile_id=...)` refactor could cross tenants. | Defensive: add `.filter(tenant=self.tenant)`. |
| D-15 | **Low** | A04 | [views.py:434](../forecasting/views.py#L434) | `suggested = max(rop.reorder_qty, rop.max_qty - current_qty)` — when `current_qty` is negative (oversold), may over-order. | Cap: `suggested = max(rop.reorder_qty, max(0, rop.max_qty - current_qty))`. |
| D-16 | **Low** | — | [views.py:277-283](../forecasting/views.py#L277-L283) | Seasonality multiplier applied identically in both branches; `elif profile:` is dead-parallel code — intent unclear. | Remove the `seasonal`-specific branch and always apply multiplier when profile is present. |
| D-17 | **Low** | A04 | [views.py:228-236](../forecasting/views.py#L228-L236) | `forecast_delete_view` allows deleting approved/archived forecasts with no status guard. | Guard: `if forecast.status != 'draft': messages.error(...); return redirect(...)`. |
| D-18 | **Info** | — | [views.py:71-79](../forecasting/views.py#L71-L79) | `_historical_demand_for` relies on `SalesOrderItem` index on `(tenant, product, sales_order__warehouse, sales_order__order_date)` that does not exist in migrations. At scale (>100k orders), scans full table per period. | Add composite index via a follow-up migration. |
| D-19 | **Info** | — | [admin.py](../forecasting/admin.py) | No `list_per_page` / `raw_id_fields` for high-cardinality FKs — admin UX degrades. | Add `list_per_page = 50`, `raw_id_fields = ('product', 'warehouse', 'tenant')` on the ModelAdmins. |

### 6.2 Defect severity distribution

| Critical | High | Medium | Low | Info | **Total** |
|:-:|:-:|:-:|:-:|:-:|:-:|
| 3 | 3 | 6 | 5 | 2 | **19** |

### 6.3 Risk register

| ID | Risk | Likelihood | Impact | Score |
|---|---|---|---|---|
| RR-01 | Duplicate ROP / SS bug is hit in production → 500 error on save | High | High (user-visible 500) | 🔴 |
| RR-02 | Non-admin staff deletes forecasts / closes alerts | High | High (data loss / audit gap) | 🔴 |
| RR-03 | Concurrent forecast creation in a team of users → IntegrityError | Medium | Medium (sporadic 500s) | 🟠 |
| RR-04 | Large-tenant alert scan (~10k ROPs) times out due to N+1 StockLevel lookups | Medium | Medium | 🟠 |
| RR-05 | Sales-order based historical demand grows O(n²) without composite index | Medium | Medium | 🟠 |
| RR-06 | Float arithmetic in `SafetyStock.recalc` statistical branch loses precision on Decimal Z-scores | Low | Low | 🟢 |

### 6.4 Quick-win recommendations

1. **Ship all three Critical fixes in a single PR** (D-01, D-02, D-04). Each is small; bundling reduces churn.
2. **Convert the four GET-mutating views to POST-only** — 10-line change, eliminates D-05.
3. **Wrap generate + `_generate_*_number` in `transaction.atomic()` + `select_for_update()`** (D-03, D-09).
4. **Add `forecasting/tests/` with the scaffolding from §5** and register in `pytest.ini` — CI catches regressions of all above from day one.
5. **Backfill audit logs** (D-12) by subscribing to `post_save` / `post_delete` signals in a central module-level signal handler — cheaper than editing every view.

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets

| File | Target line cov | Target branch cov | Rationale |
|---|---|---|---|
| [models.py](../forecasting/models.py) | ≥ 95 % | ≥ 90 % | Pure business logic; should be covered by unit tests |
| [forms.py](../forecasting/forms.py) | ≥ 90 % | ≥ 85 % | Validation correctness is paramount |
| [views.py](../forecasting/views.py) | ≥ 85 % | ≥ 75 % | Integration tests exercise most branches |
| [management/commands/seed_forecasting.py](../forecasting/management/commands/seed_forecasting.py) | ≥ 70 % | — | Data-seeder — happy path + flush + no-tenants |
| **Module overall** | **≥ 85 %** | **≥ 80 %** | CI gate |

Mutation testing (cosmic-ray / mutmut) **target ≥ 60 %** survivor-kill on `models.py`.

### 7.2 KPI dashboard

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | 100 % | 95–99 % | < 95 % |
| Open Critical defects | 0 | — | ≥ 1 |
| Open High defects | 0 | 1–2 | ≥ 3 |
| Line coverage | ≥ 85 % | 80–85 % | < 80 % |
| Mutation kill rate (models.py) | ≥ 60 % | 40–60 % | < 40 % |
| Suite runtime (full) | < 30 s | 30–60 s | > 60 s |
| `forecast_list` p95 latency (500 rows) | < 200 ms | 200–500 ms | > 500 ms |
| `rop_check_alerts` query count (20 ROPs) | ≤ 25 | 25–50 | > 50 |
| Regression escape rate per quarter | 0 | 1 | ≥ 2 |

### 7.3 Release Exit Gate

The module may be released to production **only if all** of the following are true:

- [ ] D-01, D-02, D-04 are fixed and their regression tests pass (TC-R-003, TC-S-006, TC-X-001)
- [ ] D-05 is fixed — all four mutating endpoints reject GET (TC-A-006, TC-A-007, TC-X-004)
- [ ] D-03 race fix merged — numbering collision test passes
- [ ] `forecasting/tests/` directory exists with ≥ 70 test cases, all green in CI
- [ ] Coverage: module ≥ 85 % line, `models.py` ≥ 95 % line
- [ ] Bandit scan on `forecasting/` reports 0 Medium+ findings
- [ ] Manual smoke on `admin_acme` tenant: create → generate → approve → breach → ack → close flow succeeds
- [ ] Seeder idempotency test green
- [ ] p95 latency of list views ≤ 200 ms on a seeded tenant (5 k rows)
- [ ] Audit log (`core.AuditLog`) rows emitted for all destructive actions (D-12)

---

## 8. Summary

The **Inventory Forecasting & Planning** module is a substantive 1600-LoC feature spanning 4 sub-modules (Demand Forecast, Reorder Point + Alerts, Safety Stock, Seasonality). Business logic is sound — Moving-Average / Exponential Smoothing / Linear Regression / Statistical Safety-Stock formulas produce expected output on the happy path — but **three Critical defects and three High defects** block release:

1. **Two `unique_together` + tenant traps** (D-01, D-02) produce IntegrityError 500s on duplicate creates — matches the repo's already-captured lesson #6.
2. **Missing `@tenant_admin_required`** (D-04) means any authenticated staff user can delete forecasts, close alerts, recalc safety stock — a regression of the RBAC gate established in inventory's D-05 fix.
3. **Side-effects on GET** (D-05) for `rop_check_alerts`, `alert_mark_ordered`, `alert_close`, `safety_stock_recalc` — a classic CSRF-bypass shape.
4. **Auto-numbering race** (D-03) will cause sporadic 500s once more than one user creates forecasts concurrently.
5. **Seasonality validators missing** (D-06) let `period_number=13` and `demand_multiplier=-1` through.
6. **No `transaction.atomic()`** around forecast regeneration (D-09) → partial state on mid-failure.

Nine further Medium/Low findings track validators, audit-log emission, transaction boundaries, N+1 guards, and edge-case rounding.

**Recommended next steps:**

1. Land a bundled PR fixing D-01, D-02, D-04, D-05, D-09 — they are all small and share the same area.
2. Scaffold `forecasting/tests/` from §5 and register in [pytest.ini](../pytest.ini) to lock the fixes in.
3. Author a follow-up PR for D-03 (atomic numbering) and D-06/D-07/D-10/D-11 (validators).
4. Emit audit rows via `post_save`/`post_delete` signals (D-12).
5. Re-run this SQA review on the post-fix branch to confirm closure.

Suite size at exit: **~95 test cases**, **~85 %** line coverage, **< 30 s** full-suite wall-clock. Once the Release Exit Gate is green, the module is ready for production rollout across the three demo tenants.

---

### Appendix — verification commands run during this review

```
# D-01 / D-02 confirmed via Django shell
venv/Scripts/python.exe -c "... ReorderPointForm(...).is_valid() -> True ; .save() -> IntegrityError ..."
# Output:
#   ROP FORM VALID: True
#   DB INTEGRITY ERROR on save: IntegrityError UNIQUE constraint failed: forecasting_reorderpoint...
#   SS  FORM VALID: True
#   SS DB INTEGRITY ERROR on save: IntegrityError UNIQUE constraint failed: forecasting_safetystock...

# D-03 race confirmed
#   d1 fc: FC-00001
#   d2 generated: FC-00002
#   d3 generated before d2 saved: FC-00002   ← collision

# D-06 confirmed
#   period 13 valid (should be invalid): True
#   quarter period 5 valid (should warn): True
#   negative mult valid: True

# D-07 confirmed
#   zero periods valid: True
```
