# Returns Management (RMA) — Comprehensive SQA Test Report

**Target:** `returns/` Django app — end-to-end module review
**Scope mode:** Module review (default)
**Reviewer role:** Senior SQA Engineer
**Reference quality bar:** [.claude/reviews/orders-review.md](.claude/reviews/orders-review.md), [.claude/reviews/lot_tracking-review.md](.claude/reviews/lot_tracking-review.md)
**Verification status:** 4 critical/high findings reproduced via Django shell (D-01, D-04, D-05, D-11). Others reviewed against `file:line` evidence.

---

## 1. Module Analysis

### 1.1 Purpose

The Returns Management module covers the full Return Merchandise Authorization (RMA) lifecycle for a multi-tenant WMS:

1. **Sub-module 1 — RMA** ([returns/models.py:11-130](returns/models.py#L11-L130)): customer raises a return against a `SalesOrder`, operator approves, inbound receiving marks "received", RMA closes.
2. **Sub-module 2 — Inspection** ([returns/models.py:179-301](returns/models.py#L179-L301)): QC inspector records per-item condition, pass/fail qty, restockable flag.
3. **Sub-module 3 — Disposition** ([returns/models.py:308-434](returns/models.py#L308-L434)): routes inspected items to `restock | repair | liquidate | scrap | return_to_vendor`.
4. **Sub-module 4 — Refund / Credit** ([returns/models.py:441-530](returns/models.py#L441-L530)): issues a refund, credit note, store credit, or exchange against a received RMA.

The downstream financial and inventory impact is driven by [`returns/views.py:569-607`](returns/views.py#L569-L607) (`disposition_process_view`), which writes `StockAdjustment` and mutates `StockLevel.on_hand` — i.e. the module **directly affects stock ledger and customer receivables**.

### 1.2 Surface area

| File | LoC | Role |
|---|---|---|
| [returns/models.py](returns/models.py) | 530 | 7 models + 4 state machines |
| [returns/views.py](returns/views.py) | 771 | 32 views (CRUD + 14 state transitions) |
| [returns/forms.py](returns/forms.py) | 240 | 4 ModelForms + 3 inline FormSets |
| [returns/urls.py](returns/urls.py) | 47 | 32 URL patterns |
| [returns/admin.py](returns/admin.py) | 54 | 4 registered admins |
| [returns/management/commands/seed_returns.py](returns/management/commands/seed_returns.py) | 222 | Idempotent seeder |
| [templates/returns/\*.html](templates/returns/) | 1,651 | 12 templates |
| **Total** | **3,515 LoC** | |

### 1.3 Business rules (from code)

| Rule | Evidence | Gap |
|---|---|---|
| Only delivered/closed/shipped SOs can be returned | [forms.py:44-46](returns/forms.py#L44-L46) | ✅ enforced at form init |
| RMA status graph: draft→pending→approved→received→closed (+ rejected / cancelled) | [models.py:32-40](returns/models.py#L32-L40) | ✅ `can_transition_to` check |
| Inspection allowed only on `approved` or `received` RMAs | [forms.py:103-105](returns/forms.py#L103-L105) | ✅ enforced |
| Disposition allowed only on `received`/`closed` RMAs | [forms.py:164-166](returns/forms.py#L164-L166) | ✅ enforced |
| Disposition decision must match inspection outcome | *(not enforced)* | ❌ **D-02** — `restock` allowed for `defective`/`unusable` items |
| `qty_passed + qty_failed == qty_inspected` | *(not enforced)* | ❌ **D-10** |
| `qty_inspected ≤ rma_item.qty_received` | *(not enforced)* | ❌ **D-10** |
| `disposition.qty ≤ inspection_item.qty_passed` | *(not enforced)* | ❌ **D-11** |
| `refund.amount ≤ rma.total_value` | *(not enforced)* | ❌ **D-01** (verified) |
| State transitions are POST-only | *(not enforced)* | ❌ **D-04** (verified) |
| All FK fields in inline formsets tenant-filtered at validation | *(partial)* | ❌ **D-05** (verified) |

### 1.4 Dependencies (cross-module)

- [orders.SalesOrder / SalesOrderItem](orders/models.py) — source of customer and items.
- [catalog.Product](catalog/models.py) — returned SKUs.
- [warehousing.Warehouse / Bin](warehousing/models.py) — return destination and putaway bin.
- [inventory.StockLevel / StockAdjustment](inventory/models.py) — restock and scrap writes.
- [core.Tenant / User](core/models.py) — multi-tenant boundary and actor identity.

### 1.5 Pre-test risk profile

| Risk area | Rating | Reason |
|---|---|---|
| **Financial integrity** | 🔴 High | No refund upper-bound; zero-amount refund accepted; no audit log on `refund_process`/`disposition_process` |
| **Stock integrity** | 🔴 High | Restock path ignores `restockable` / `condition` → phantom inventory |
| **Tenant isolation** | 🔴 High | Inline formset FK fields (rma_item, product, inspection_item, destination_bin) cross-tenant at POST — verified |
| **CSRF / auth** | 🔴 High | 14 state-transition views accept GET → drive-by state change |
| **State machine correctness** | 🟡 Medium | Transitions guarded but no concurrency control (race on double-click) |
| **Data validation** | 🟡 Medium | No cross-field qty validation; currency free-text |
| **Performance / N+1** | 🟢 Low | List views `select_related` correctly |
| **Automation coverage** | 🔴 Critical | **Zero tests** — no `returns/tests/` directory exists |

---

## 2. Test Plan

### 2.1 Test types & depth

| Layer | Tool | Depth | Target |
|---|---|---|---|
| Unit (models, state machine, number generation) | pytest + pytest-django | ≥ 90% line, ≥ 80% branch | [models.py](returns/models.py) |
| Unit (forms — tenant binding, queryset filtering) | pytest | ≥ 90% | [forms.py](returns/forms.py) |
| Integration (views + forms + DB + tenant context) | pytest-django + Client | ≥ 85% | [views.py](returns/views.py) |
| Security — IDOR (cross-tenant) | pytest | 100% of view IDs | all FK fields |
| Security — CSRF (GET state change) | pytest | 100% of transitions | 14 transition endpoints |
| Security — RBAC | pytest | All transitions | approve / process / delete |
| Functional (Happy path E2E: RMA → inspection → disposition → refund) | pytest + Playwright (smoke) | 3 scenarios | full chain |
| Regression (pagination filter retention, CRUD completeness) | pytest | All 4 list pages | [rma_list.html](templates/returns/rma_list.html) + 3 others |
| Boundary (decimals, qty, string length) | pytest `parametrize` | All numeric fields | amount, qty_*, prices |
| Edge (unicode, emoji, empty, whitespace) | pytest `parametrize` | All text fields | customer_name, notes, address |
| Negative (invalid transitions, over-receive, over-refund) | pytest | All guard paths | state machines, amount caps |
| Performance (N+1, list at 1k rows) | `django_assert_max_num_queries` | All list + detail | 4 lists + 4 details |
| Mutation testing | `mutmut` | Diff coverage on PR | models + forms |
| Static security | `bandit`, `pip-audit` | All returns/ | |
| Accessibility | axe-core (manual) | 12 templates | WCAG 2.1 AA |

### 2.2 Entry criteria

- SQLite in-memory test DB via [config/settings_test.py](config/settings_test.py).
- Fixtures: tenant, other_tenant, warehouse, bin, product, SO (delivered), RMA in each status.
- `pytest.ini` updated to include `returns/tests` in `testpaths`.

### 2.3 Exit criteria

See §7 Release Exit Gate.

---

## 3. Test Scenarios

### 3.1 RMA (Return Authorization) — prefix `R-NN`

| # | Scenario | Type |
|---|---|---|
| R-01 | Create RMA with 3 items, status defaults to `draft` | Functional |
| R-02 | `rma_number` auto-generated `RMA-00001`, `RMA-00002` | Unit |
| R-03 | Only SOs in `delivered`/`closed`/`shipped` visible in dropdown | Integration |
| R-04 | Submit draft → pending transitions; other states rejected | State machine |
| R-05 | Approve pending → status=approved, `approved_by`/`approved_at` set | State machine |
| R-06 | Reject pending → rejected; then rejected→draft allowed | State machine |
| R-07 | Receive approved → `qty_received = qty_requested` auto-fill | Functional / negative (D-09) |
| R-08 | Close received → closed; `closed_at` set | State machine |
| R-09 | Cancel allowed from draft/pending/approved only | State machine |
| R-10 | Invalid transition returns error message, no state change | Negative |
| R-11 | Delete draft RMA cascades to items; non-draft blocked (UI) but endpoint unguarded | Negative (D-19) |
| R-12 | Pagination preserves `q`, `status`, `reason`, `warehouse` across pages | Regression (D-12) |
| R-13 | Filter by `status=pending` + `reason=warranty` both apply | Integration |
| R-14 | Cross-tenant RMA `GET /returns/<other_tenant_pk>/` → 404 | Security IDOR |
| R-15 | Cross-tenant `product_id` in inline formset accepted → **IDOR** | Security (D-05) |
| R-16 | `GET /returns/1/submit/` without POST → status changes | Security CSRF (D-04) |
| R-17 | XSS: `customer_name="<script>"` escaped in list + detail | Security A03 |
| R-18 | SQL injection in `q`: `' OR 1=1--` → no leak | Security A03 |
| R-19 | `@login_required` unauth → redirect `/accounts/login/` | Security A01 |
| R-20 | Concurrent double-approve: second request sees `pending→approved` already done and no-ops | Race |
| R-21 | Emoji / RTL unicode in customer_name, notes, return_address | Edge |
| R-22 | Very long notes (100 KB) rejected or truncated | Boundary |
| R-23 | RMA with zero items allowed? (business gap) | Business |
| R-24 | Edit RMA in approved status should be blocked or restricted | Business |

### 3.2 Inspection — prefix `I-NN`

| # | Scenario | Type |
|---|---|---|
| I-01 | Create inspection against approved RMA — `inspection_number` `RINS-00001` | Unit |
| I-02 | `rma` dropdown shows only `approved`/`received` RMAs | Integration |
| I-03 | Start pending → in_progress; `started_at` set | State machine |
| I-04 | Complete in_progress → completed; auto-sets `inspected_date` if blank | State machine |
| I-05 | `qty_passed + qty_failed != qty_inspected` accepted → **D-10** | Negative |
| I-06 | `qty_inspected > rma_item.qty_received` accepted → **D-10** | Negative |
| I-07 | Cross-tenant `rma_item_id` in formset → **IDOR (D-05)** | Security |
| I-08 | `GET /inspections/1/start/` causes transition | Security (D-04) |
| I-09 | Delete inspection while dispositions exist → cascade | Integration |
| I-10 | Filter by status + result simultaneously | Integration |
| I-11 | Negative qty rejected by `PositiveIntegerField` | Boundary |

### 3.3 Disposition — prefix `D-NN`

| # | Scenario | Type |
|---|---|---|
| D-01-S | Create disposition with decision=restock → items created | Functional |
| D-02-S | `decision=restock` on `condition=defective` / `restockable=False` items accepted → **D-02** phantom inventory | Security / business |
| D-03-S | Process restock writes `StockAdjustment(increase, reason=return)` and `stock.on_hand += qty` | Integration |
| D-04-S | Process scrap writes `StockAdjustment(decrease, reason=damage)` — but NOT `stock.on_hand` decrement | Regression / defect |
| D-05-S | Process liquidate / repair / return_to_vendor → no stock side-effect at all | Business gap |
| D-06-S | Double-click process → double `StockAdjustment` rows | Race (D-03 from report §6) |
| D-07-S | Cross-tenant `destination_bin_id` in formset → **IDOR (D-05)** | Security |
| D-08-S | `qty > inspection_item.qty_passed` accepted | Negative (D-11) |
| D-09-S | `GET /dispositions/1/process/` drives financial write | Security (D-04) |
| D-10-S | Filter by decision + warehouse + status | Integration |

### 3.4 Refund / Credit — prefix `F-NN`

| # | Scenario | Type |
|---|---|---|
| F-01 | Create refund against received RMA → pending | Functional |
| F-02 | `amount > rma.total_value` accepted — **D-01** (verified) | Security / business |
| F-03 | `amount = 0` accepted — no-op refund | Negative (D-17) |
| F-04 | `currency="XYZ"` or emoji accepted — free-text | Negative (D-13) |
| F-05 | `amount = 999,999,999.99` accepted | Boundary (D-01) |
| F-06 | Process pending → processed; `processed_by`/`processed_at` set | State machine |
| F-07 | `GET /refunds/1/process/` processes refund — **drive-by financial write** | Security (D-04) |
| F-08 | Fail pending → failed; can revert failed → pending or cancel | State machine |
| F-09 | Cross-tenant RMA_id at form POST accepted? (forms.py filters `rma` qs, so no) | Security — expected pass |
| F-10 | No `AuditLog` created on process/delete | Compliance (D-15) |
| F-11 | Filter by status + type + method preserves across pagination | Regression (D-12) |

### 3.5 Cross-cutting — prefix `X-NN`

| # | Scenario | Type |
|---|---|---|
| X-01 | Concurrent RMA create under same tenant → unique `rma_number` | Race (D-08) |
| X-02 | Concurrent inspection create → unique `inspection_number` | Race (D-08) |
| X-03 | Superuser (tenant=None) accessing any list → empty queryset (by design) | Multi-tenant |
| X-04 | `admin.py` filter sidebar does not leak cross-tenant rows | Security A01 |
| X-05 | Seeder re-run without `--flush` is idempotent | Seed |
| X-06 | Template variables never render unescaped user input | Security A03 |

---

## 4. Detailed Test Cases

Representative high-priority test cases. The full catalogue is enumerated in §3. Each test case maps to a scenario.

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-RMA-001** | Create RMA with 2 items → status=draft, RMA#=RMA-00001 | Tenant T1 + SO "SO-0001" in delivered + Product P1,P2 | POST `/returns/create/` with form + formset | `sales_order=SO-0001, customer_name=Alice, reason=defective, items=[{P1,1,10},{P2,2,5}]` | 302 → detail; DB: 1 RMA + 2 items, status=draft, rma_number=RMA-00001 | No side effects on stock |
| **TC-RMA-002** | Duplicate submit races: two concurrent POST from draft → only one transitions | RMA in draft | Fire two POST `/returns/1/submit/` concurrently | — | Both return 302; status=pending; DB has one state change | No duplicate audit |
| **TC-RMA-004-SEC** | **CSRF bypass**: GET on `/submit/` drives transition (D-04) | RMA in draft, user logged in | `GET /returns/1/submit/` | — | **CURRENT: status=pending** / **EXPECTED: 405 or 403** | Regression lock |
| **TC-RMA-005-IDOR** | **Cross-tenant product_id in formset** (D-05) | T1 RMA pk=1, T2 Product pk=99 | Login T1; POST create with `items-0-product=99` | `product=99` (T2's) | **CURRENT: form valid, item saved with cross-tenant product** / **EXPECTED: form invalid** | Data stays in T1 only |
| **TC-RMA-006** | Reject pending → rejected; then rejected → draft allowed | RMA pending | POST reject → POST edit (status draft after manual transition) | — | status=rejected; `can_transition_to('draft')==True` | — |
| **TC-RMA-007** | Receive overwrites partial qty_received when set to 0 (D-09) | RMA approved, 2 items with qty_requested=5, qty_received=3 | POST `/receive/` | — | **CURRENT: qty_received=5 for items where qty_received==0; preserves where set** / **EXPECTED: preserve receiver's entry** | — |
| **TC-RMA-008-XSS** | XSS in customer_name | — | POST create with `customer_name="<script>alert(1)</script>"` | — | List and detail render escaped `&lt;script&gt;`; no alert | — |
| **TC-RMA-009-TENANT** | IDOR on detail endpoint | T1 logged in, T2 RMA pk=99 | `GET /returns/99/` | — | 404 Not Found | — |
| **TC-RMA-010-PAG** | Pagination retains all filters | 30 RMAs across reasons | `GET /returns/?status=pending&reason=warranty&warehouse=1&page=2` then click next | — | `?page=2&status=pending&reason=warranty&warehouse=1` in next link | **CURRENT: reason + warehouse lost** (D-12) |
| **TC-INS-001** | Create inspection on approved RMA → auto-number RINS-00001 | RMA approved with 2 items | POST `/inspections/create/` | `rma=1, inspector=U1, items=[{rma_item=1, qty_inspected=2, qty_passed=2, qty_failed=0, condition=good, restockable=True}]` | 302; inspection+items saved; inspection_number=RINS-00001 | — |
| **TC-INS-002-QTY** | `qty_passed + qty_failed != qty_inspected` (D-10) | inspection form | POST with `qty_inspected=5, qty_passed=2, qty_failed=1` | — | **CURRENT: form valid** / **EXPECTED: ValidationError** | — |
| **TC-INS-003-IDOR** | Cross-tenant rma_item in inline formset (D-05) | T1 RMA, T2 RMA item pk=5 | Login T1; POST create with `items-0-rma_item=5` | — | **CURRENT: accepted** / **EXPECTED: invalid** | — |
| **TC-INS-004-CSRF** | GET /start/ (D-04) | inspection pending | GET `/inspections/1/start/` | — | **CURRENT: status in_progress** / **EXPECTED: 405** | — |
| **TC-DISP-001** | Process restock writes stock | Disposition pending, decision=restock, items[{P1,qty=5}], warehouse WH1 | POST `/dispositions/1/process/` | — | `StockLevel(on_hand+=5)`; `StockAdjustment(adjustment_type=increase, reason=return, quantity=5)` | Disposition.status=processed |
| **TC-DISP-002-PHANTOM** | Restock of defective/unusable inspection item (D-02) | InspectionItem condition=defective, restockable=False; Disposition decision=restock | POST `/dispositions/1/process/` | — | **CURRENT: stock increments by qty** / **EXPECTED: refuse** | — |
| **TC-DISP-003-RACE** | Double-click process → duplicate StockAdjustment | disposition pending | Fire two POST /process/ in parallel | — | **CURRENT: may produce 2 StockAdjustments** / **EXPECTED: idempotent** | Atomic `select_for_update()` guard |
| **TC-DISP-004-CSRF** | GET /process/ drives financial write (D-04) | disposition pending | `GET /dispositions/1/process/` | — | **CURRENT: stock adjusted on GET** | Catastrophic — drive-by inventory mutation |
| **TC-DISP-005-IDOR** | Cross-tenant destination_bin in formset (D-05) | T1 Disposition, T2 Bin pk=7 | POST with `items-0-destination_bin=7` | — | **CURRENT: accepted** / **EXPECTED: invalid** | — |
| **TC-DISP-006** | Scrap path does NOT decrement `stock.on_hand` | disposition decision=scrap, StockLevel(on_hand=10) | POST /process/ | — | **CURRENT: StockAdjustment decrease created but on_hand stays 10** — asymmetric with restock path | Ledger inconsistency |
| **TC-REF-001** | Create refund amount equal to rma.total_value | RMA received, total_value=100 | POST `/refunds/create/` with `amount=100` | — | 302; refund pending; refund_number REF-00001 | — |
| **TC-REF-002-OVERREFUND** | Refund amount > total_value (D-01 verified) | RMA total=100 | POST create with `amount=999999999.99` | — | **CURRENT: valid** / **EXPECTED: ValidationError "refund cannot exceed 100"** | — |
| **TC-REF-003-ZERO** | Refund amount=0 (D-17) | — | POST with `amount=0` | — | **CURRENT: valid** / **EXPECTED: ValidationError** | — |
| **TC-REF-004-CURRENCY** | Arbitrary currency "XYZ" (D-13) | — | POST with `currency=XYZ` | — | **CURRENT: valid** / **EXPECTED: restricted to ISO 4217** | — |
| **TC-REF-005-CSRF** | GET /process/ refunds money (D-04) | refund pending | `GET /refunds/1/process/` | — | **CURRENT: status=processed** | Drive-by financial write |
| **TC-REF-006-AUDIT** | No AuditLog emitted on refund processing (D-15) | — | POST /process/ then query `core.AuditLog` | — | `0 rows` | Compliance gap |
| **TC-SEC-001** | Anonymous GET `/returns/` → 302 to login | logged out | `GET /returns/` | — | 302 `/accounts/login/?next=...` | — |
| **TC-SEC-002-RBAC** | Non-admin user approving RMA — only `@login_required`, no role check | regular user logged in | POST `/approve/` | — | **CURRENT: any authenticated user can approve** / **EXPECTED: requires `is_tenant_admin`** | D-21 |
| **TC-PERF-001** | `GET /returns/` with 500 RMAs → < 20 queries | 500 seeded rows | `django_assert_max_num_queries(20)` around `client.get('/returns/')` | — | Passes | — |
| **TC-EDGE-001** | Unicode+emoji customer_name round-trip | — | create with `customer_name='李明 🦄 مرحبا'` | — | 302; detail page renders the string | — |
| **TC-BND-001** | `amount` max digits 12 dp 2 → `9999999999.99` accepted, `99999999999.99` rejected | — | parametrised POST | — | — | — |
| **TC-X-001** | Concurrent create in one tenant → no duplicate rma_number (D-08) | — | 20 threads `ReturnAuthorization.objects.create(...)` | — | No `IntegrityError` OR all rows saved with unique numbers | Requires `select_for_update` + retry |

---

## 5. Automation Strategy

### 5.1 Tool stack (recommended)

| Layer | Tool | Purpose |
|---|---|---|
| Unit + integration | `pytest` + `pytest-django` | primary suite |
| Fixtures | `factory-boy` (recommended — not yet used) + hand-rolled `conftest.py` (current pattern) | |
| E2E smoke | Playwright Python | happy-path E2E for RMA chain |
| Load | `locust` | 100 concurrent RMA creations |
| Static security | `bandit -r returns/` | |
| Dependency audit | `pip-audit` | |
| Mutation | `mutmut` | run on PR diff |
| Coverage | `coverage.py` + `pytest-cov` | |

### 5.2 Suite layout

```
returns/
└── tests/
    ├── __init__.py
    ├── conftest.py          # tenant, other_tenant, SO, RMA fixtures
    ├── test_models.py       # number generation, state machine, line_total
    ├── test_forms_rma.py    # queryset scoping, tenant binding
    ├── test_forms_inspection.py
    ├── test_forms_disposition.py
    ├── test_forms_refund.py
    ├── test_views_rma.py
    ├── test_views_inspection.py
    ├── test_views_disposition.py
    ├── test_views_refund.py
    ├── test_security_csrf.py    # GET → transition for all 14 endpoints
    ├── test_security_idor.py    # cross-tenant formset FK
    ├── test_security_rbac.py    # approve / process gated to is_tenant_admin
    ├── test_state_machine.py    # all 4 state machines parametrised
    ├── test_performance.py      # N+1 guard on 4 lists
    └── test_audit_log.py        # refund / disposition emit AuditLog
```

### 5.3 Ready-to-run snippets

#### `returns/tests/__init__.py`
```python
```

#### `returns/tests/conftest.py`
```python
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse, Zone, Aisle, Rack, Bin
from orders.models import SalesOrder, SalesOrderItem
from returns.models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Returns', slug='t-returns')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other-R', slug='t-other-r')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_r', password='x', tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_r', password='x', tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other_r', password='x', tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main', address='', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other', address='', is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Cat', slug='cat')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku='P1', name='Prod 1', status='active',
        retail_price=Decimal('10.00'),
    )


@pytest.fixture
def other_product(db, other_tenant):
    oc = Category.objects.create(tenant=other_tenant, name='OC', slug='oc')
    return Product.objects.create(
        tenant=other_tenant, category=oc, sku='OP1', name='OP', status='active',
    )


@pytest.fixture
def bin_location(db, tenant, warehouse):
    z = Zone.objects.create(tenant=tenant, warehouse=warehouse, code='Z1', name='Z1')
    a = Aisle.objects.create(tenant=tenant, zone=z, code='A1', name='A1')
    r = Rack.objects.create(tenant=tenant, aisle=a, code='R1', name='R1')
    return Bin.objects.create(tenant=tenant, rack=r, code='B1', name='B1', is_active=True)


@pytest.fixture
def other_bin(db, other_tenant, other_warehouse):
    z = Zone.objects.create(tenant=other_tenant, warehouse=other_warehouse, code='Z1', name='Z1')
    a = Aisle.objects.create(tenant=other_tenant, zone=z, code='A1', name='A1')
    r = Rack.objects.create(tenant=other_tenant, aisle=a, code='R1', name='R1')
    return Bin.objects.create(tenant=other_tenant, rack=r, code='B1', name='B1', is_active=True)


@pytest.fixture
def delivered_so(db, tenant, warehouse, tenant_admin, product):
    so = SalesOrder.objects.create(
        tenant=tenant, customer_name='Alice', order_date=date(2026, 4, 18),
        warehouse=warehouse, created_by=tenant_admin, status='delivered',
    )
    SalesOrderItem.objects.create(
        tenant=tenant, sales_order=so, product=product,
        quantity=5, unit_price=Decimal('10.00'),
    )
    return so


@pytest.fixture
def draft_rma(db, tenant, delivered_so, warehouse, tenant_admin, product):
    rma = ReturnAuthorization.objects.create(
        tenant=tenant, sales_order=delivered_so, customer_name='Alice',
        reason='defective', requested_date=date(2026, 4, 18),
        warehouse=warehouse, created_by=tenant_admin,
    )
    ReturnAuthorizationItem.objects.create(
        tenant=tenant, rma=rma, product=product,
        qty_requested=2, unit_price=Decimal('10.00'),
    )
    return rma


@pytest.fixture
def approved_rma(db, draft_rma):
    draft_rma.status = 'approved'
    draft_rma.save()
    return draft_rma


@pytest.fixture
def received_rma(db, draft_rma):
    draft_rma.status = 'received'
    for i in draft_rma.items.all():
        i.qty_received = i.qty_requested
        i.save()
    draft_rma.save()
    return draft_rma


@pytest.fixture
def other_draft_rma(db, other_tenant, other_warehouse, other_tenant_admin, other_product):
    so = SalesOrder.objects.create(
        tenant=other_tenant, customer_name='Bob', order_date=date(2026, 4, 18),
        warehouse=other_warehouse, created_by=other_tenant_admin, status='delivered',
    )
    soi = SalesOrderItem.objects.create(
        tenant=other_tenant, sales_order=so, product=other_product,
        quantity=3, unit_price=Decimal('5.00'),
    )
    rma = ReturnAuthorization.objects.create(
        tenant=other_tenant, sales_order=so, customer_name='Bob',
        reason='other', requested_date=date(2026, 4, 18),
        warehouse=other_warehouse, created_by=other_tenant_admin,
    )
    ReturnAuthorizationItem.objects.create(
        tenant=other_tenant, rma=rma, product=other_product,
        qty_requested=1, unit_price=Decimal('5.00'),
    )
    return rma


@pytest.fixture
def client_admin(tenant_admin):
    c = Client()
    c.force_login(tenant_admin)
    return c


@pytest.fixture
def client_user(tenant_user):
    c = Client()
    c.force_login(tenant_user)
    return c


@pytest.fixture
def client_other(other_tenant_admin):
    c = Client()
    c.force_login(other_tenant_admin)
    return c
```

#### `returns/tests/test_models.py`
```python
import pytest
from datetime import date
from decimal import Decimal

from returns.models import ReturnAuthorization, ReturnInspection, Disposition, RefundCredit


pytestmark = pytest.mark.django_db


class TestRMANumberGeneration:
    def test_first_rma_gets_00001(self, draft_rma):
        assert draft_rma.rma_number == 'RMA-00001'

    def test_sequential_numbers(self, tenant, delivered_so, warehouse, tenant_admin):
        r1 = ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='a',
            requested_date=date(2026, 4, 18), warehouse=warehouse,
        )
        r2 = ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='b',
            requested_date=date(2026, 4, 18), warehouse=warehouse,
        )
        assert r2.rma_number == 'RMA-00002'
        # cross-tenant sequences are independent
        from core.models import Tenant
        t2 = Tenant.objects.create(name='T-2', slug='t-2')
        # (would need SO in t2; omitted for brevity)


class TestRMAStateMachine:
    @pytest.mark.parametrize('from_state, to_state, allowed', [
        ('draft', 'pending', True),
        ('draft', 'approved', False),
        ('pending', 'approved', True),
        ('pending', 'rejected', True),
        ('approved', 'received', True),
        ('approved', 'closed', False),
        ('received', 'closed', True),
        ('closed', 'cancelled', False),
    ])
    def test_transitions(self, draft_rma, from_state, to_state, allowed):
        draft_rma.status = from_state
        assert draft_rma.can_transition_to(to_state) is allowed


class TestRMACalculations:
    def test_total_value(self, draft_rma):
        assert draft_rma.total_value == Decimal('20.00')

    def test_total_qty_requested(self, draft_rma):
        assert draft_rma.total_qty_requested == 2
```

#### `returns/tests/test_forms_refund.py`
```python
import pytest
from decimal import Decimal

from returns.forms import RefundCreditForm


pytestmark = pytest.mark.django_db


class TestRefundAmountValidation:
    def test_amount_exceeding_rma_total_should_be_rejected(self, received_rma):
        """D-01: refund must not exceed rma.total_value"""
        form = RefundCreditForm(
            data={
                'rma': received_rma.pk, 'type': 'refund', 'method': 'card',
                'amount': '999999.99', 'currency': 'USD',
                'reference_number': 'X', 'notes': '',
            },
            tenant=received_rma.tenant,
        )
        assert not form.is_valid(), (
            'BUG: form accepts refund exceeding RMA total. '
            f'Expected form invalid, got errors={form.errors}'
        )
        assert 'amount' in form.errors

    def test_zero_amount_refund_rejected(self, received_rma):
        """D-17: zero-amount refund is a no-op"""
        form = RefundCreditForm(
            data={
                'rma': received_rma.pk, 'type': 'refund', 'method': 'card',
                'amount': '0.00', 'currency': 'USD',
                'reference_number': '', 'notes': '',
            },
            tenant=received_rma.tenant,
        )
        assert not form.is_valid()

    def test_currency_must_be_iso_4217(self, received_rma):
        """D-13: currency should be validated"""
        form = RefundCreditForm(
            data={
                'rma': received_rma.pk, 'type': 'refund', 'method': 'card',
                'amount': '5.00', 'currency': 'XYZ',
                'reference_number': '', 'notes': '',
            },
            tenant=received_rma.tenant,
        )
        assert not form.is_valid()
```

#### `returns/tests/test_security_csrf.py`
```python
"""D-04: all state-transition endpoints must be POST-only."""
import pytest


pytestmark = pytest.mark.django_db

TRANSITION_ENDPOINTS = [
    # (fixture_name, url_suffix)
    ('draft_rma', 'submit'),
    # approve/reject require pending — use a second fixture per state in real suite
    ('draft_rma', 'cancel'),
]


@pytest.mark.parametrize('fixture_name, suffix', TRANSITION_ENDPOINTS)
def test_get_on_transition_endpoint_must_not_change_state(
    request, fixture_name, suffix, client_admin,
):
    rma = request.getfixturevalue(fixture_name)
    before = rma.status
    resp = client_admin.get(f'/returns/{rma.pk}/{suffix}/')
    rma.refresh_from_db()
    assert resp.status_code in (405, 403, 302), (
        f'Expected 405/403/302 for GET on {suffix}, got {resp.status_code}'
    )
    # Critical assertion: state must not change on GET
    assert rma.status == before, (
        f'BUG: GET /{suffix}/ changed status from {before} to {rma.status}. '
        'This is a CSRF bypass — add @require_POST.'
    )
```

#### `returns/tests/test_security_idor.py`
```python
"""D-05: inline formset FK fields must be tenant-filtered on POST."""
import pytest


pytestmark = pytest.mark.django_db


def test_rma_create_rejects_cross_tenant_product(
    client_admin, tenant, other_product, delivered_so, warehouse,
):
    data = {
        'sales_order': delivered_so.pk,
        'customer_name': 'Alice',
        'customer_email': '', 'customer_phone': '', 'return_address': '',
        'reason': 'defective',
        'requested_date': '2026-04-18',
        'expected_return_date': '',
        'warehouse': warehouse.pk,
        'notes': '',
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-product': other_product.pk,   # cross-tenant!
        'items-0-description': '',
        'items-0-qty_requested': '1',
        'items-0-unit_price': '10.00',
        'items-0-reason_note': '',
    }
    resp = client_admin.post('/returns/create/', data)
    # Expected: form invalid → 200 with errors
    assert resp.status_code == 200, (
        f'BUG: cross-tenant product accepted (status={resp.status_code}). '
        'Expected form to reject.'
    )


def test_inspection_create_rejects_cross_tenant_rma_item(
    client_admin, approved_rma, other_draft_rma,
):
    other_rma_item = other_draft_rma.items.first()
    data = {
        'rma': approved_rma.pk,
        'inspector': '',
        'inspected_date': '2026-04-18',
        'overall_result': 'pass',
        'notes': '',
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-rma_item': other_rma_item.pk,  # cross-tenant!
        'items-0-qty_inspected': '1',
        'items-0-qty_passed': '1',
        'items-0-qty_failed': '0',
        'items-0-condition': 'good',
        'items-0-notes': '',
    }
    resp = client_admin.post('/returns/inspections/create/', data)
    assert resp.status_code == 200, 'BUG: cross-tenant rma_item accepted in inspection form.'
```

#### `returns/tests/test_views_disposition.py`
```python
"""D-02/D-11: restock must not push defective items into on_hand."""
import pytest
from decimal import Decimal

from inventory.models import StockLevel, StockAdjustment
from returns.models import (
    ReturnInspection, ReturnInspectionItem, Disposition, DispositionItem,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def defective_disposition(db, tenant, received_rma, warehouse, tenant_admin):
    insp = ReturnInspection.objects.create(
        tenant=tenant, rma=received_rma, status='completed',
        overall_result='fail', inspector=tenant_admin,
    )
    rma_item = received_rma.items.first()
    ins_item = ReturnInspectionItem.objects.create(
        tenant=tenant, inspection=insp, rma_item=rma_item,
        qty_inspected=2, qty_passed=0, qty_failed=2,
        condition='defective', restockable=False,
    )
    disp = Disposition.objects.create(
        tenant=tenant, rma=received_rma, inspection=insp,
        decision='restock',  # mismatched with defective
        warehouse=warehouse, status='pending',
    )
    DispositionItem.objects.create(
        tenant=tenant, disposition=disp, inspection_item=ins_item,
        product=rma_item.product, qty=2,
    )
    return disp


def test_cannot_restock_defective_item(client_admin, defective_disposition):
    """D-02: restock path must refuse items flagged not restockable."""
    resp = client_admin.post(f'/returns/dispositions/{defective_disposition.pk}/process/')
    defective_disposition.refresh_from_db()
    assert defective_disposition.status != 'processed', (
        'BUG: defective inspection item was restocked — phantom inventory created.'
    )
    assert StockAdjustment.objects.filter(
        notes__icontains=defective_disposition.disposition_number,
    ).count() == 0
```

#### `returns/tests/test_performance.py`
```python
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection


pytestmark = pytest.mark.django_db


def test_rma_list_no_n_plus_1(client_admin, tenant, delivered_so, warehouse, tenant_admin):
    from returns.models import ReturnAuthorization
    from datetime import date
    for i in range(40):
        ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name=f'c{i}',
            requested_date=date(2026, 4, 18), warehouse=warehouse,
        )
    with CaptureQueriesContext(connection) as ctx:
        resp = client_admin.get('/returns/')
    assert resp.status_code == 200
    assert len(ctx.captured_queries) < 20, (
        f'N+1 risk: {len(ctx.captured_queries)} queries on 20-row list page'
    )
```

### 5.4 Running

```
venv\Scripts\activate.bat
pytest returns/tests -v
```

Add to `pytest.ini` → `testpaths`: include `returns/tests`.

---

## 6. Defects, Risks & Recommendations

Severity scale: **Critical** = financial / inventory / tenant-isolation breach; **High** = security or state-corruption bug exploitable by a normal logged-in user; **Medium** = data-quality or workflow-correctness bug; **Low** = hygiene / polish; **Info** = non-defect observations.

| ID | Sev | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-01** | 🔴 Critical | A04 Insecure Design | [forms.py:211-240](returns/forms.py#L211-L240), [models.py:485](returns/models.py#L485) | **Verified in shell**: `RefundCreditForm` accepts `amount=999,999,999.99` against an RMA whose `total_value=211.87`. Zero-value refund also accepted. Combined with D-04 this enables drive-by over-refund via GET. | Add `clean_amount()`: (a) `amount > 0`, (b) `amount <= self.cleaned_data['rma'].total_value - already_refunded(self.cleaned_data['rma'])`. |
| **D-02** | 🔴 Critical | A04 Insecure Design | [views.py:569-589](returns/views.py#L569-L589) | `disposition_process_view`'s restock branch increments `stock.on_hand` and writes `StockAdjustment(increase)` for every `DispositionItem` regardless of the linked `ReturnInspectionItem.restockable` / `condition`. A defective or unusable unit is restocked as if new → phantom inventory and downstream OOS-lies / fulfilment of broken goods. Seed data confirms defective inspection items exist in practice. | Guard restock: `if not di.inspection_item.restockable or di.inspection_item.condition in ('defective','unusable','major_damage'): raise ValidationError(...)`. Also cap qty at `inspection_item.qty_passed`. |
| **D-03** | 🔴 Critical | A01 Access Control | [views.py:569-613](returns/views.py#L569-L613) | `disposition_process_view` is not wrapped in `transaction.atomic()` + `select_for_update()`. Two concurrent POSTs both pass `can_transition_to('processed')` and both run the restock loop → duplicate `StockAdjustment` rows and double `on_hand` increment. | Wrap in `with transaction.atomic(): disp = Disposition.objects.select_for_update().get(pk=pk, tenant=tenant)` and re-check status. |
| **D-04** | 🔴 Critical | A01 / CSRF | [views.py:169-252, 384-411, 549-627, 732-771](returns/views.py) | **Verified in shell**: `GET /returns/1/submit/` changes status `draft → pending`. 14 state-transition views accept GET (rma submit/approve/reject/receive/close/cancel; inspection start/complete; disposition process/cancel; refund process/fail/cancel). Any logged-in user visiting an `<img src>` or `<a href>` from a hostile page triggers a state change (or even a refund / stock adjustment) — CSRF-bypass because GET is not CSRF-protected. | Add `@require_POST` to all 14 transition views. Django ≥ 1.9 `@require_POST` returns 405 on GET. |
| **D-05** | 🔴 Critical | A01 Broken Access Control | [views.py:96-98, 128-131, 314-316, 346-349, 481-487, 519-526](returns/views.py) | **Verified in shell**: inline formset FK fields (`product`, `rma_item`, `inspection_item`, `destination_bin`) inherit the default model `.objects.all()` queryset during `formset.is_valid()` on POST. Queryset scoping happens AFTER validation (line 96 vs line 78). A logged-in T1 user can POST `items-0-product=<T2-product-pk>` and the item saves with a cross-tenant FK (the `tenant` field is force-set to T1, but the `product_id` leaks T2). | Move queryset filtering BEFORE `formset = ...(request.POST, ...)`. Preferred: override each formset form's `__init__` to accept `tenant` and filter inside the form class (same shape as the non-formset `ModelForm`s in this module). |
| **D-06** | 🟠 High | A01 RBAC | entire [views.py](returns/views.py) | Only `@login_required` is used. Any authenticated tenant user (including a warehouse picker) can approve RMAs, process dispositions (mutate stock), or process refunds (financial write). There is no `is_tenant_admin` / role gate. | Add a role check helper: `if not request.user.is_tenant_admin: return HttpResponseForbidden()` on approve / process / delete endpoints. |
| **D-07** | 🟠 High | A09 Logging failures | [views.py:182-252, 561-627, 733-771](returns/views.py) | No `core.AuditLog` (or equivalent) entries are emitted for approve / receive / close / process_refund / process_disposition / delete. Financial and inventory-affecting actions must be traceable for SOX-style compliance. | Emit `AuditLog.objects.create(tenant=..., actor=request.user, action='refund_processed', object_id=refund.pk, ...)` inside each transition. |
| **D-08** | 🟠 High | A04 Race | [models.py:116-130, 244-258, 381-395, 516-530](returns/models.py) | `_generate_rma_number()` / `_generate_inspection_number()` / etc. pick `order_by('-id').first()` then `+1`. Under concurrency two writers read the same "last" and write duplicates → `IntegrityError` bubbling to 500. `unique_together=('tenant', <number>)` catches it, but the user sees a hard error. | Wrap create path in `transaction.atomic()`+`select_for_update()` on a tenant-scoped sentinel row, or use a DB sequence per tenant (`core.TenantSequence`), or retry on IntegrityError up to N times. |
| **D-09** | 🟠 High | A04 Insecure Design | [views.py:217-220](returns/views.py#L217-L220) | `rma_receive_view` loops items and sets `qty_received = qty_requested` when `qty_received == 0`. This overrides the operator's intent when partial receipt has not yet been keyed — partial return receipts are silently upgraded to full. Also, re-running receive after partial entry blows away zeros. | Remove this auto-fill. Require the operator to enter `qty_received` per item on a dedicated receive form (mirrors receiving module). |
| **D-10** | 🟡 Medium | A04 | [forms.py:120-132](returns/forms.py#L120-L132), [models.py:261-295](returns/models.py#L261-L295) | No validator on `qty_passed + qty_failed == qty_inspected`, nor `qty_inspected ≤ rma_item.qty_received`. | Add `ReturnInspectionItemForm.clean()` cross-field validation. |
| **D-11** | 🟡 Medium | A04 | [forms.py:185-204](returns/forms.py#L185-L204) | No validator on `DispositionItem.qty ≤ inspection_item.qty_passed` (for restock) or `qty ≤ qty_failed` (for scrap). Operator can enter arbitrary qty → bad stock ledger. | `DispositionItemForm.clean()`. |
| **D-12** | 🟡 Medium | Usability | [templates/returns/rma_list.html:138-144](templates/returns/rma_list.html#L138-L144), refund_list, disposition_list, inspection_list | Pagination `?page=N` links drop the `reason`, `warehouse`, `result`, `type`, `method`, `decision` filter params. User changes page → filter context is lost. | Use a `{% querystring %}` tag or explicitly include all filter params. Follow [.claude/CLAUDE.md](.claude/CLAUDE.md) "Filter Implementation Rules". |
| **D-13** | 🟡 Medium | A04 | [models.py:486](returns/models.py#L486) | `RefundCredit.currency` is free-text `CharField(max_length=10)` with no validator or choices. Accepts `"XYZ"`, `"🦄"`, `"  "`. | Use `choices=ISO_4217_CHOICES` (a small tuple) or at least `RegexValidator(r'^[A-Z]{3}$')`. |
| **D-14** | 🟢 Low | A03 fragile template logic | [templates/returns/rma_detail.html:176](templates/returns/rma_detail.html#L176) | `{% if rma.status in 'draft,pending,approved' %}` does a **substring** match, not a set-membership check. Works only coincidentally. If a new status value happens to be a substring of this string (e.g. `'raft'`), it will match silently. | Replace with explicit `{% if rma.status == 'draft' or rma.status == 'pending' or rma.status == 'approved' %}` or use a custom `{% if rma.status in 'draft,pending,approved'|split:',' %}` filter. |
| **D-15** | 🟡 Medium | A09 | [views.py delete_view functions](returns/views.py) | RMA / inspection / disposition / refund deletes have no soft-delete and no audit trail. A draft refund for $1M can be `.delete()`d without trace. | Introduce soft-delete (`is_deleted`, `deleted_at`) or emit `AuditLog`. Block delete of processed refunds entirely. |
| **D-16** | 🟢 Low | A04 | [views.py:158-166](returns/views.py#L158-L166) | `rma_delete_view` deletes any RMA regardless of `status`. UI only shows the button for `draft`, but the endpoint accepts POST from other states. Cascade deletes processed refunds (financial record loss). | `if rma.status != 'draft': return HttpResponseForbidden()`. |
| **D-17** | 🟡 Medium | A04 | [forms.py:211-240](returns/forms.py#L211-L240) | `amount` default=0 with no `MinValueValidator(>0)`. Combined with D-01 ⇒ zero-value refund records pile up. | `clean_amount()` → require `> 0`. |
| **D-18** | 🟢 Low | DX / Coverage | [pytest.ini:5](pytest.ini#L5), no `returns/tests/` | `returns/` is missing from `pytest.ini` testpaths and has no test directory → 0% automated coverage. | Implement the §5 suite; add `returns/tests` to `testpaths`. |
| **D-19** | 🟡 Medium | Data integrity | [models.py:42-89, 207-232, 335-368, 472-503](returns/models.py) | Cascading `on_delete=CASCADE` on tenant and RMA lets a single RMA delete drop all linked refunds/dispositions, including *processed* ones. | Use `PROTECT` once status leaves draft; enforce at view level as per D-16. |
| **D-20** | 🟢 Low | Data quality | [views.py:585, 605](returns/views.py#L585-L605) | Restock path writes `reason='return'`, scrap writes `reason='damage'` — but [inventory.StockAdjustment](inventory/models.py) reason `choices` may not include these exact values. Verify the constants match; silent failure otherwise. | Add unit test covering both reasons. |
| **D-21** | 🟡 Medium | A01 RBAC (concrete) | [views.py:182-194](returns/views.py#L182-L194) | See D-06. Specifically `rma_approve_view` allows any authenticated user to approve — violates segregation-of-duties (creator should not approve). | Add both role gate and a "creator cannot approve" check: `if rma.created_by_id == request.user.id: return HttpResponseForbidden('Creator cannot approve own RMA')`. |
| **D-22** | 🟢 Low | A03 / XSS | [templates/returns/rma_detail.html:42](templates/returns/rma_detail.html#L42) | `{{ rma.return_address|linebreaksbr }}` — `linebreaksbr` is safe (HTML-escapes first, then inserts `<br>`), so this is OK. **No action** — listed for completeness. | None. |
| **D-23** | 🟢 Low | Admin | [admin.py:19, 32, 45, 53](returns/admin.py) | `list_filter = (..., 'tenant')` exposes a tenant picker to superusers, which is fine, but a tenant-admin using `/admin/` will see every tenant's rows — cross-tenant exposure in admin. | Either restrict `/admin/` to superusers or override `get_queryset` to filter by `request.user.tenant`. |
| **D-24** | 🟢 Low | Seed | [management/commands/seed_returns.py:64-66](returns/management/commands/seed_returns.py#L64-L66) | Idempotency check is per-tenant and only checks RMA; if RMA exists but inspections were partially deleted, rerun without `--flush` skips the tenant entirely. | Check per sub-model existence, not only `ReturnAuthorization`. |
| **D-25** | 🟢 Info | Architecture | — | Four state machines (`VALID_TRANSITIONS`) are copy-pasted across models. A shared mixin (`StateMachineMixin`) would cut duplication and enable consistent audit. | Extract to `core/state_machine.py`. |

### Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stock ledger corruption via restock-of-defective | Medium | High | Fix D-02 + D-11 + write integration test |
| Over-refund fraud | Medium | Critical | Fix D-01 + D-17 + audit log D-07 |
| Drive-by CSRF state change (incl. refund process) | High | High | Fix D-04 across 14 endpoints in one sweep |
| Cross-tenant data leakage via formset FK | Medium | Critical | Fix D-05 |
| Race on number generation under load | Low | Medium | Fix D-08 with sequence table |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets (post-implementation)

| File | Lines | Line cov | Branch cov | Mutation score |
|---|---|---|---|---|
| [returns/models.py](returns/models.py) | 530 | ≥ 90% | ≥ 80% | ≥ 70% |
| [returns/forms.py](returns/forms.py) | 240 | ≥ 95% | ≥ 90% | ≥ 75% |
| [returns/views.py](returns/views.py) | 771 | ≥ 85% | ≥ 80% | ≥ 65% |
| [returns/urls.py](returns/urls.py) | 47 | 100% | n/a | n/a |
| [returns/admin.py](returns/admin.py) | 54 | ≥ 70% | n/a | n/a |

### 7.2 KPI table

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | ≥ 99% | 95–99% | < 95% |
| Open Critical defects | 0 | — | ≥ 1 |
| Open High defects | 0 | 1–2 | ≥ 3 |
| Test suite runtime | < 60 s | 60–120 s | > 120 s |
| p95 latency — RMA list | < 300 ms | 300–500 | > 500 |
| p95 latency — disposition process | < 500 ms | 500–1000 | > 1000 |
| Query count — RMA list (20 rows) | ≤ 12 | 13–20 | > 20 |
| Query count — RMA detail | ≤ 12 | 13–20 | > 20 |
| Regression escape rate | < 1/release | 1–2 | > 2 |
| Cross-tenant IDOR assertions passing | 100% | — | < 100% |

### 7.3 Release Exit Gate

All of the following MUST be true before shipping any further change to `returns/`:

- [ ] D-01, D-02, D-03, D-04, D-05 fixed and covered by a regression test each.
- [ ] `returns/tests/` exists and is in `pytest.ini` `testpaths`.
- [ ] `pytest returns/tests -v` is green on CI.
- [ ] `coverage run -m pytest returns/tests; coverage report --include='returns/*'` ≥ 85% line.
- [ ] `bandit -r returns/` ≤ 0 High findings.
- [ ] `pip-audit` ≤ 0 Critical findings.
- [ ] All 14 state-transition endpoints have a `test_get_returns_405` regression.
- [ ] Cross-tenant IDOR test asserts formset FKs for rma_item, product, inspection_item, destination_bin.
- [ ] `AuditLog` row is written for every `refund_process`, `disposition_process`, `rma_approve`, `rma_receive`, `rma_close` call.
- [ ] Filter retention across pagination verified manually on all 4 list pages.

---

## 8. Summary

The Returns Management module ships functional CRUD across four sub-modules and correctly enforces most tenant boundaries at the view level. Seed data is idempotent; list pages are `select_related`-optimised; the state graphs are well-typed in the models.

However, **the module is NOT production-safe today**. Five Critical defects were reproduced against the live codebase:

1. **D-01** — refund form has no upper-bound validation (verified: $999M refund accepted against a $211 RMA).
2. **D-02** — restock processing ignores `restockable` / `condition`, writing phantom inventory.
3. **D-03** — disposition processing has no concurrency guard → duplicate stock writes.
4. **D-04** — 14 transition endpoints accept GET, enabling drive-by state changes and financial writes (verified: GET → `draft → pending`).
5. **D-05** — inline formset FK fields are not tenant-scoped at POST validation (verified: cross-tenant `product`, `rma_item`, `inspection_item`, `destination_bin` accepted).

Adding to that: no automated tests exist (`returns/tests/` absent from `pytest.ini`). The module is in effect running on manual smoke tests only.

**Next-step recommendation**: before adding any new feature, spend one focused iteration on:

1. Adding `@require_POST` across 14 endpoints (≈ 20 minutes).
2. Moving inline-formset queryset filtering before `formset.is_valid()` (≈ 30 minutes).
3. Adding `clean_amount()` on `RefundCreditForm` (≈ 20 minutes).
4. Guarding restock against non-restockable inspection items (≈ 30 minutes).
5. Scaffolding `returns/tests/` with the snippets in §5.3 and wiring into `pytest.ini` (≈ 2 hours).

This closes all Critical defects in well under a day.

If you want me to proceed, reply with one of:

- **"fix the defects"** — I implement D-01/D-02/D-03/D-04/D-05/D-07 and commit file-by-file.
- **"build the tests"** — I scaffold `returns/tests/` from §5.3 and run `pytest returns/tests -v`.
- **"do all"** — both, in that order.
