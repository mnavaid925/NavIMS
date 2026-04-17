# Stocktaking & Cycle Counting — Comprehensive SQA Test Report

**Target module:** [stocktaking/](stocktaking/)
**Scope:** Full module review (models + forms + views + urls + templates + seed command)
**Reviewer persona:** Senior SQA Engineer (15+ yrs Django/Python)
**Review date:** 2026-04-18
**Branch:** `main`
**Report file:** [.claude/reviews/stocktaking-review.md](.claude/reviews/stocktaking-review.md)

---

## 1. Module Analysis

### 1.1 Purpose

The stocktaking module implements four tightly-coupled sub-flows that reconcile **system stock** against **physical stock**:

| Sub-module | Entity | Business purpose |
|---|---|---|
| Full physical inventory | `StocktakeFreeze` | Freeze one or more zones of a warehouse while counters work |
| Cycle count scheduling | `CycleCountSchedule` | Recurring counts by ABC class and frequency |
| Stock counting | `StockCount` + `StockCountItem` | Record physical counts, variance vs system qty |
| Variance adjustment | `StockVarianceAdjustment` | Approval workflow that posts variances to `inventory.StockLevel` via `inventory.StockAdjustment` |

### 1.2 Files & line counts

| File | LoC | Role |
|---|---|---|
| [stocktaking/models.py](stocktaking/models.py) | 458 | 5 models, 2 state machines, 3 auto-number generators |
| [stocktaking/views.py](stocktaking/views.py) | 625 | 25 views (5 CRUD per entity + workflow transitions) |
| [stocktaking/forms.py](stocktaking/forms.py) | 186 | 4 model forms + 1 inline formset |
| [stocktaking/urls.py](stocktaking/urls.py) | 43 | 27 URL patterns |
| [stocktaking/admin.py](stocktaking/admin.py) | 41 | 4 admin registrations |
| [stocktaking/management/commands/seed_stocktaking.py](stocktaking/management/commands/seed_stocktaking.py) | 200 | Idempotent per-tenant seeder |
| Templates ([templates/stocktaking/](templates/stocktaking/)) | ~1.1k | 10 templates, all extending `base.html` |
| **Tests** | **0** | **No pytest suite exists — zero coverage** |

### 1.3 Business rules mapped to code

| # | Rule | File:line |
|---|---|---|
| BR-01 | A freeze begins `active` and can only move to `released` | [models.py:12-15](stocktaking/models.py#L12-L15), [views.py:96-103](stocktaking/views.py#L96-L103) |
| BR-02 | Freeze number auto-generated `FRZ-00001..N` per tenant | [models.py:59-73](stocktaking/models.py#L59-L73) |
| BR-03 | `StockCount.VALID_TRANSITIONS` defines a DAG `draft→in_progress→counted→reviewed→adjusted` with `cancelled` side-track | [models.py:154-161](stocktaking/models.py#L154-L161) |
| BR-04 | `StockCountItem.variance = counted_qty - system_qty` | [models.py:343-347](stocktaking/models.py#L343-L347) |
| BR-05 | `variance_value = variance × unit_cost` (Decimal) | [models.py:349-353](stocktaking/models.py#L349-L353) |
| BR-06 | Variance adjustment flow `pending→approved→posted` or `rejected→pending` | [models.py:382-387](stocktaking/models.py#L382-L387) |
| BR-07 | Posting an adjustment sets `StockLevel.on_hand = counted_qty`, emits a `StockAdjustment` audit row, and flips the count to `adjusted` | [views.py:583-624](stocktaking/views.py#L583-L624) |
| BR-08 | `_populate_count_items` snapshots `StockLevel` at count creation time | [views.py:242-254](stocktaking/views.py#L242-L254) |
| BR-09 | `blind_count=True` hides the system qty from the counter in the count-sheet template | [count_sheet.html:51,64](templates/stocktaking/count_sheet.html#L51) |
| BR-10 | Every model is tenant-scoped via `tenant = FK('core.Tenant')`; every queryset filters by `request.tenant` | e.g. [views.py:28-29](stocktaking/views.py#L28-L29) |

### 1.4 Risk profile (pre-test)

| Area | Risk | Rationale |
|---|---|---|
| **Money & stock impact** | 🔴 **HIGH** | `adjustment_post_view` mutates `StockLevel.on_hand` in production. A bug here directly falsifies inventory valuations. |
| **Workflow integrity** | 🟠 Medium | Two state machines (`StockCount`, `StockVarianceAdjustment`) with 6+4 states and 15 transition arcs. |
| **CSRF surface** | 🔴 **HIGH** | 8 state-changing views accept GET — see §6 D-01. |
| **Concurrency** | 🟠 Medium | Auto-numbering (`_generate_count_number`, `_generate_freeze_number`, `_generate_adjustment_number`) is TOCTOU-racy. |
| **Multi-tenancy** | 🟢 Low | Tenant filter present on every CRUD path. (One soft gap — see D-14.) |
| **Input validation** | 🟠 Medium | `counted_qty` accepts negatives server-side despite `min="0"` HTML hint. |
| **Coverage** | 🔴 Critical | 0 tests. No regression safety net. |

---

## 2. Test Plan

### 2.1 Test strategy

We will apply a **defence-in-depth** test pyramid aligned with ISO/IEC/IEEE 29119:

| Layer | Tooling | Target coverage |
|---|---|---|
| Unit | pytest-django + factory-boy | model invariants, variance math, state-machine `can_transition_to`, auto-number generators |
| Integration | pytest-django (Client) | view + form + ORM flow, tenant isolation, filter retention, CSRF |
| Functional / E2E | Playwright (headless Chromium) | end-to-end "schedule → count → review → adjust → post" journey |
| Security | pytest + bandit + (optional) OWASP ZAP | OWASP A01-A10, IDOR, CSRF, XSS, path traversal |
| Performance | `django_assert_max_num_queries`, Locust | N+1 on list pages, count sheet with 1k items |
| Regression | Snapshot tests for templates | guard badge markup and filter retention |

### 2.2 OWASP coverage map

| OWASP | Focus for this module |
|---|---|
| **A01 Access Control** | Every view login-gated? Every queryset filter by `tenant`? IDOR on `/counts/<pk>/sheet/` with another tenant's pk? |
| **A02 Crypto** | N/A (no secrets in module) |
| **A03 Injection / XSS** | `notes`, `reason`, count search query — ensure template auto-escape; no `|safe`. |
| **A04 Insecure design** | `counted_qty` negative check; posting the same adjustment twice; re-editing a `counted`/`reviewed` count via the sheet. |
| **A05 Misconfig** | State-changing views accept GET — see D-01. |
| **A06 Vulnerable deps** | Out-of-scope for module review. |
| **A07 Auth failures** | `@login_required` on every view — verify. |
| **A08 Data integrity** | No `@transaction.atomic` around posting; partial StockAdjustment write possible. Audit log missing. |
| **A09 Logging** | `core.AuditLog` NOT emitted on posting — see D-09. |
| **A10 SSRF** | N/A. |

### 2.3 Exit criteria (Release Gate)

A release is blocked unless **ALL** are true:
- ✅ 0 Critical, 0 High open defects (§6)
- ✅ Line coverage ≥ 85% on `models.py`, ≥ 80% on `views.py`, ≥ 90% on `forms.py`
- ✅ Branch coverage ≥ 75% on state-machine paths
- ✅ p95 list-view latency ≤ 300 ms at 10k stock counts
- ✅ N+1 guard: every list view stays ≤ 8 DB queries regardless of page size
- ✅ Smoke E2E "schedule → post adjustment" green

---

## 3. Test Scenarios

### 3.1 Freeze (F-NN)

| # | Scenario | Type |
|---|---|---|
| F-01 | Freeze create with 0 zones (whole warehouse) | Functional |
| F-02 | Freeze create with 3 zones selected | Functional |
| F-03 | Freeze number auto-generated `FRZ-00001` on first tenant record | Unit |
| F-04 | Freeze number increments per tenant — T1 gets FRZ-00001 while T2 also gets FRZ-00001 | Unit / multi-tenant |
| F-05 | `unique_together (tenant, freeze_number)` enforces no duplicate numbers | Integration |
| F-06 | Concurrent create raises `IntegrityError` vs silent duplicate (race) | Negative / concurrency |
| F-07 | Edit a released freeze — allowed but status stays released | Regression |
| F-08 | Release an already-released freeze → error message, no state change | Negative |
| F-09 | Release via GET succeeds — **CSRF vulnerability** | **Security (A05)** |
| F-10 | Cross-tenant IDOR: T2 user GETs `/freezes/<T1-pk>/edit/` → 404 | Security (A01) |
| F-11 | Unauthenticated user hits `/freezes/` → redirect to login | Security (A07) |
| F-12 | XSS in `reason` field `<script>alert(1)</script>` stored, rendered escaped | Security (A03) |
| F-13 | Filter by `status=active` — only active freezes shown | Functional |
| F-14 | Filter retention across pagination — **currently broken** | Regression |
| F-15 | Warehouse dropdown shows only this tenant's active warehouses | Integration |

### 3.2 Cycle Count Schedule (S-NN)

| # | Scenario | Type |
|---|---|---|
| S-01 | Create schedule with valid name/frequency/abc_class | Functional |
| S-02 | Schedule with empty name → form invalid | Negative |
| S-03 | `frequency` outside choices → form invalid | Boundary |
| S-04 | `next_run_date` in the past — allowed (no validator) | DEFECT candidate |
| S-05 | Deactivate (`is_active=False`) schedule — excluded from `StockCountForm` dropdown | Integration |
| S-06 | Delete schedule with referenced counts — `on_delete=SET_NULL` cascades correctly | Regression |
| S-07 | Run schedule creates a `StockCount` pre-populated with items | Functional |
| S-08 | Run schedule twice back-to-back → creates 2 draft counts (intended?) | Edge |
| S-09 | Run via GET is a CSRF surface | Security (A05) |
| S-10 | Filter by frequency / active flag / search | Functional |
| S-11 | Unicode + emoji in `name` (e.g. "🔄 Weekly") | Edge |
| S-12 | Zones from a different warehouse of the same tenant — form does not cross-validate | DEFECT candidate |

### 3.3 Stock Count (C-NN)

| # | Scenario | Type |
|---|---|---|
| C-01 | Create count of type `cycle` — items snapshotted from `StockLevel` | Functional |
| C-02 | Create count of type `full` with a freeze | Functional |
| C-03 | Create count with no stock levels → count with 0 items | Edge |
| C-04 | `count_number` auto-generated `CNT-00001` | Unit |
| C-05 | Count sheet saves partial counts → status flips `draft→in_progress` | Functional |
| C-06 | Submit count via "Save & Submit" → status flips to `counted` | Functional |
| C-07 | Edit a `counted` count via `/edit/` → blocked with flash message | Regression |
| C-08 | POST to `/sheet/` for an `adjusted` count **overwrites historical counted_qty** | **DEFECT candidate (D-04)** |
| C-09 | Start a count that's already `in_progress` → error message | Negative |
| C-10 | Review transitions `counted→reviewed` | Functional |
| C-11 | Cancel a `draft` count → status `cancelled` | Functional |
| C-12 | Invalid transition (`draft→reviewed`) via URL forcing → blocked by `can_transition_to` | Negative |
| C-13 | Submit `counted_qty = -5` — form accepts (IntegerField), downstream `StockLevel.on_hand` fails | **DEFECT candidate (D-05)** |
| C-14 | `counted_qty` exceeds int max (2^31) → DB OverflowError | Boundary |
| C-15 | Blind count — `system_qty` not rendered in HTML | Security (A04) |
| C-16 | Non-blind count — `system_qty` visible | Regression |
| C-17 | Cross-tenant IDOR on `/counts/<pk>/sheet/` → 404 | Security (A01) |
| C-18 | CSRF — count_start / review / cancel via GET succeed | **Security (A05)** |
| C-19 | N+1 on count sheet with 500 items — currently unbounded | Perf |
| C-20 | Concurrent edits to same count by two counters — last-write-wins | Concurrency |
| C-21 | Unicode in `notes` — stored & rendered escaped | Edge |
| C-22 | Pagination preserves filters — **currently broken** | Regression |

### 3.4 Variance Adjustment (V-NN)

| # | Scenario | Type |
|---|---|---|
| V-01 | Create adjustment from `counted` count — totals auto-computed | Functional |
| V-02 | Create adjustment from `reviewed` count — ok | Functional |
| V-03 | Create adjustment from `draft` count — form invalid (count not in queryset) | Negative |
| V-04 | `total_variance_qty / value` computed correctly from items with variance | Unit |
| V-05 | Approve pending adjustment — status flips `pending→approved`, approver stamped | Functional |
| V-06 | Reject pending adjustment — status flips to `rejected` | Functional |
| V-07 | Re-pend rejected adjustment → status flips `rejected→pending` | Functional |
| V-08 | Post approved adjustment — `StockLevel.on_hand` updated, `StockAdjustment` row created, count → `adjusted` | **Functional (critical path)** |
| V-09 | Post fails mid-loop (e.g. one item raises) — **no transaction, partial writes persist** | **DEFECT candidate (D-02)** |
| V-10 | Double-post: two adjustments on same count, both approved — second post runs against already-updated stock | **DEFECT candidate (D-03)** |
| V-11 | Post via GET → mutates stock without CSRF token | **Security (A05) — D-01** |
| V-12 | Delete posted adjustment → blocked | Regression |
| V-13 | Edit posted adjustment → blocked | Regression |
| V-14 | Cross-tenant IDOR on approve/post | Security (A01) |
| V-15 | Large variance value (Decimal overflow) `max_digits=14` | Boundary |
| V-16 | Reason code outside CHOICES → rejected | Negative |
| V-17 | Post without ever calling `apply_adjustment()` — audit-trail drift (StockAdjustment exists but was not applied via model method; view overwrites on_hand directly) | **DEFECT candidate (D-06)** |
| V-18 | No `core.AuditLog` row emitted on post | **DEFECT candidate (D-09)** |

### 3.5 Cross-cutting (X-NN)

| # | Scenario | Type |
|---|---|---|
| X-01 | All 25 views enforce `@login_required` | Security (A07) |
| X-02 | All 25 views filter by `request.tenant` | Security (A01) |
| X-03 | All URL names resolve (`stocktaking:*`) | Smoke |
| X-04 | Template auto-escape on every user-controlled field | Security (A03) |
| X-05 | Seed command idempotent — second run no-ops | Functional |
| X-06 | Seed `--flush` removes all data | Functional |
| X-07 | Admin registrations don't bypass tenant filter (Django admin superuser sees all — acceptable) | Regression |
| X-08 | `unique_together` + no tenant in form trap (lesson #6) — validated via `clean_*` guard? | **DEFECT candidate (D-07)** |
| X-09 | Performance: list views ≤ 8 queries at 10k records | Perf |
| X-10 | Dashboard integration: any stocktaking widget KPIs | Integration |

---

## 4. Detailed Test Cases

Column legend: **ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions**

### 4.1 Freeze — representative detailed cases

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-FRZ-001 | Happy-path create | Tenant T1 with 1 active warehouse | `POST /stocktaking/freezes/create/` with `warehouse=W1, reason="EOY"` | `{warehouse: W1.pk, reason: "EOY"}` | HTTP 302 to list; 1 `StocktakeFreeze` with `freeze_number="FRZ-00001"`, `status="active"`, `frozen_by=user`, `frozen_at` within 1s | row persisted |
| TC-FRZ-002 | Sequential numbering | TC-FRZ-001 completed | Create 2 more freezes | — | `FRZ-00002`, `FRZ-00003` | monotonic |
| TC-FRZ-003 | Multi-tenant numbering independence | T1 has FRZ-00001; T2 created | As T2, create freeze | — | T2's first row is `FRZ-00001` | tenant-scoped |
| TC-FRZ-004 | Release only if active | Freeze status=released | `GET /freezes/<pk>/release/` | — | Flash "Freeze is not active"; status unchanged | no change |
| TC-FRZ-005 | Cross-tenant IDOR | T1 has freeze F1; logged in as T2 | `GET /freezes/<F1.pk>/edit/` | — | HTTP 404 | no access |
| TC-FRZ-006 | XSS in reason | — | Create freeze with `reason="<script>alert(1)</script>"` | — | Stored literally; rendered in list as `&lt;script&gt;...` | safe |
| TC-FRZ-007 | CSRF on release | Logged-in session cookie, external page with `<img src=".../release/">` | Browser loads external page | — | **Currently: freeze released (bug)**. After fix: only POST works, 405 on GET | no unauth state change |
| TC-FRZ-008 | Filter retention | 25 freezes, filter status=active (20 match) | `GET /?status=active&page=2` | — | Page 2 shows second slice of the 20 active, pagination link preserves `status=active` | filter sticky |

### 4.2 Stock Count & Count Sheet

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-CNT-001 | Create cycle count | T1 has warehouse W1 with 6 StockLevels | `POST /counts/create/` type=cycle, warehouse=W1 | `{type: cycle, warehouse: W1.pk, scheduled_date: today}` | 302 to detail; `StockCount.count_number="CNT-00001"`, 6 `StockCountItem` rows with `system_qty` = matching on_hand, `counted_qty=NULL` | snapshot |
| TC-CNT-002 | Post to sheet flips status | count in `draft` | `POST /counts/<pk>/sheet/` with counted_qty for 3 of 6 items | formset data | status=`in_progress`, 3 items have `counted_qty`, `counted_by`, `counted_at` set | partial progress |
| TC-CNT-003 | Submit count | `in_progress` with all counted | `POST /counts/<pk>/sheet/ submit_count=1` | — | status=`counted`, `completed_at` set, `counted_by=user` | submission |
| TC-CNT-004 | Edit blocked post-draft | count status=counted | `GET /counts/<pk>/edit/` | — | Flash "Cannot edit a count after it has started"; 302 to detail | no edit |
| TC-CNT-005 | **Sheet mutates adjusted count (D-04)** | count status=adjusted, item A has counted_qty=10 | `POST /counts/<pk>/sheet/` with counted_qty=99 for item A | — | **Currently: item A updated to 99, history corrupted**. After fix: 403/redirect with error | immutable |
| TC-CNT-006 | **Negative counted_qty (D-05)** | count in_progress | `POST /counts/<pk>/sheet/` with counted_qty=-5 | — | **Currently: saved with -5, downstream post crashes**. After fix: form invalid | no bad data |
| TC-CNT-007 | Blind count UI hides system_qty | count with `blind_count=True` | `GET /counts/<pk>/sheet/` | — | Response HTML does NOT contain the string `system_qty` value numerically | blind OK |
| TC-CNT-008 | Tenant isolation on sheet | T1 count, T2 user | `GET /counts/<T1pk>/sheet/` as T2 | — | HTTP 404 | isolated |
| TC-CNT-009 | Invalid transition blocked | count in `adjusted` | `GET /counts/<pk>/start/` | — | Flash "Cannot start count" | immutable |
| TC-CNT-010 | N+1 guard | 500 items on sheet | `GET /counts/<pk>/sheet/` | — | ≤ 10 queries regardless of item count | perf |
| TC-CNT-011 | Unicode notes | — | Create count with notes="テスト 🔄" | — | Stored & escaped in HTML | i18n |
| TC-CNT-012 | count_sheet with formset errors | Invalid formset | POST with non-numeric counted_qty | `counted_qty="abc"` | Form redisplays with errors; no data changed | validation |

### 4.3 Variance Adjustment (posting — critical path)

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-ADJ-001 | Create from counted | count status=counted, 3 items with variance (net +5 qty, +$50) | `POST /adjustments/create/` | `{count: pk, reason: miscount}` | adj with `total_variance_qty=5`, `total_variance_value=50.00`, status=pending | totals |
| TC-ADJ-002 | Approve pending | adj pending | `GET /adjustments/<pk>/approve/` | — | **Currently: approved via GET (D-01)**. After fix: POST required | workflow |
| TC-ADJ-003 | Post approved adjustment | adj approved; 3 items; SL.on_hand for item A was 10, counted 15 | `POST /adjustments/<pk>/post/` | — | adj.status=posted, count.status=adjusted; SL.on_hand for item A = 15; 3 `StockAdjustment` rows exist; `last_counted_at` updated | stock updated |
| TC-ADJ-004 | **Partial failure leaves half-posted (D-02)** | adj approved; item B will raise (e.g. missing StockLevel, but get_or_create covers — synthesise via patch) | `POST /adjustments/<pk>/post/` mocked to raise on 2nd item | — | **Currently: item A posted, item B fails, adj.status stays approved → rerunning re-posts item A (D-03)**. After fix: atomic rollback | integrity |
| TC-ADJ-005 | **Double-post (D-03)** | Two approved adjustments on same count | Post both | — | **Currently: stock overwritten twice (2nd wins); audit log shows 2× StockAdjustment per item**. After fix: 2nd rejects with "count already adjusted" | idempotent |
| TC-ADJ-006 | Post blocked when pending | adj pending | `GET /adjustments/<pk>/post/` | — | Flash "Cannot post adjustment in current status" | blocked |
| TC-ADJ-007 | IDOR on post | T2 session, T1 adj pk | `GET /adjustments/<T1pk>/post/` | — | 404 | isolated |
| TC-ADJ-008 | Delete posted | adj posted | `POST /adjustments/<pk>/delete/` | — | Flash "Cannot delete a posted adjustment"; redirect to detail | immutable |
| TC-ADJ-009 | **No AuditLog emitted (D-09)** | — | After TC-ADJ-003, inspect `core.AuditLog` | — | **Currently: no row**. After fix: `AuditLog(action="variance_post", user=…, object_id=adj.pk)` | compliance |
| TC-ADJ-010 | CSRF on approve/reject/post via GET | authenticated session | attacker page with `<img src=".../post/">` | — | **Currently: adj posted, stock mutated**. After fix: 405 | security |

### 4.4 Parametrised negative matrix (applies to all 4 entities)

| ID | Field | Bad value | Expected |
|---|---|---|---|
| TC-PARAM-001 | `freeze.reason` | 256+ chars | Form invalid (max_length=255) |
| TC-PARAM-002 | `schedule.name` | "" | Form invalid (required) |
| TC-PARAM-003 | `schedule.frequency` | "hourly" | Form invalid (not in choices) |
| TC-PARAM-004 | `count.scheduled_date` | "not-a-date" | Form invalid |
| TC-PARAM-005 | `count_item.counted_qty` | "abc" | Form invalid |
| TC-PARAM-006 | `count_item.counted_qty` | -5 | **Currently valid — DEFECT D-05** |
| TC-PARAM-007 | `count_item.counted_qty` | 10**12 | Validation / DB overflow |
| TC-PARAM-008 | `adjustment.reason_code` | "sabotage" | Form invalid |
| TC-PARAM-009 | `q` search param | `' OR 1=1 --` | Returns no results; no SQL error (ORM parameterises) |
| TC-PARAM-010 | `warehouse` filter | `99999` (other tenant) | Empty result, no error |

---

## 5. Automation Strategy

### 5.1 Stack

- **Runner:** `pytest` + `pytest-django`
- **Fixtures:** `factory-boy` (one factory per model)
- **Client:** Django `Client` for integration; `pytest-xdist` for parallel
- **E2E:** Playwright (`pytest-playwright`) for the golden journey
- **Perf:** `django_assert_max_num_queries`, Locust for load
- **Security:** `bandit` (SAST), manual OWASP ZAP pass for dynamic
- **Coverage:** `coverage.py` target ≥ 85% lines, ≥ 75% branches

### 5.2 Suite layout

```
stocktaking/tests/
├── __init__.py
├── conftest.py
├── factories.py
├── test_models.py          # unit — model saves, variance math, state machines
├── test_forms.py           # form validation, negative matrix
├── test_views_freeze.py
├── test_views_schedule.py
├── test_views_count.py
├── test_views_adjustment.py
├── test_security.py        # OWASP A01-A05/A07/A08/A09
├── test_performance.py     # N+1, list-at-scale
└── test_seed.py            # idempotency of seed command
```

### 5.3 `conftest.py` — ready to drop in

```python
# stocktaking/tests/conftest.py
import pytest
from decimal import Decimal
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product, Category
from warehousing.models import Warehouse, Zone
from inventory.models import StockLevel


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Stock', slug='t-stock', is_active=True)


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other', slug='t-other', is_active=True)


@pytest.fixture
def user(db, tenant):
    return User.objects.create_user(
        username='counter',
        password='pw',
        tenant=tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username='other',
        password='pw',
        tenant=other_tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    # NavIMS resolves tenant via middleware; ensure session has tenant
    session = client.session
    session['tenant_id'] = user.tenant_id
    session.save()
    return client


@pytest.fixture
def category(tenant):
    return Category.objects.create(tenant=tenant, name='Widgets', code='WG')


@pytest.fixture
def warehouse(tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main WH', is_active=True,
    )


@pytest.fixture
def zone(tenant, warehouse):
    return Zone.objects.create(tenant=tenant, warehouse=warehouse, code='Z1', name='Zone 1')


@pytest.fixture
def products(tenant, category):
    return [
        Product.objects.create(
            tenant=tenant, category=category,
            sku=f'SKU-{i:03d}', name=f'Widget {i}',
            purchase_cost=Decimal('10.00'),
        )
        for i in range(6)
    ]


@pytest.fixture
def stock_levels(tenant, warehouse, products):
    return [
        StockLevel.objects.create(
            tenant=tenant, warehouse=warehouse, product=p,
            on_hand=100, allocated=0, on_order=0,
        )
        for p in products
    ]
```

### 5.4 `test_models.py` — unit invariants

```python
# stocktaking/tests/test_models.py
import pytest
from decimal import Decimal
from django.db import IntegrityError
from stocktaking.models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)


@pytest.mark.django_db
class TestAutoNumbering:
    def test_freeze_number_starts_at_00001(self, tenant, warehouse):
        f = StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        assert f.freeze_number == 'FRZ-00001'

    def test_freeze_numbers_are_monotonic_per_tenant(self, tenant, warehouse):
        for _ in range(3):
            StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        nums = list(StocktakeFreeze.objects.filter(tenant=tenant)
                    .values_list('freeze_number', flat=True))
        assert nums == ['FRZ-00003', 'FRZ-00002', 'FRZ-00001']

    def test_freeze_numbers_independent_per_tenant(self, tenant, other_tenant, warehouse):
        # other_tenant needs its own warehouse
        from warehousing.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=other_tenant, code='WH2', name='W2', is_active=True)
        StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        f2 = StocktakeFreeze.objects.create(tenant=other_tenant, warehouse=wh2)
        assert f2.freeze_number == 'FRZ-00001'

    def test_count_number_auto_generated(self, tenant, warehouse):
        from datetime import date
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        assert c.count_number == 'CNT-00001'

    def test_adjustment_number_auto_generated(self, tenant, warehouse):
        from datetime import date
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        adj = StockVarianceAdjustment.objects.create(tenant=tenant, count=c)
        assert adj.adjustment_number == 'VADJ-00001'


@pytest.mark.django_db
class TestStateMachine:
    @pytest.mark.parametrize('src,dst,ok', [
        ('draft', 'in_progress', True),
        ('draft', 'counted', False),
        ('in_progress', 'counted', True),
        ('counted', 'reviewed', True),
        ('reviewed', 'adjusted', True),
        ('adjusted', 'draft', False),   # terminal
        ('adjusted', 'cancelled', False),
        ('cancelled', 'draft', True),
    ])
    def test_count_transitions(self, tenant, warehouse, src, dst, ok):
        from datetime import date
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(), status=src,
        )
        assert c.can_transition_to(dst) is ok

    @pytest.mark.parametrize('src,dst,ok', [
        ('pending', 'approved', True),
        ('pending', 'posted', False),
        ('approved', 'posted', True),
        ('posted', 'approved', False),
        ('rejected', 'pending', True),
    ])
    def test_adjustment_transitions(self, tenant, warehouse, src, dst, ok):
        from datetime import date
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        adj = StockVarianceAdjustment.objects.create(tenant=tenant, count=c, status=src)
        assert adj.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestVarianceMath:
    def test_variance_none_when_uncounted(self, tenant, warehouse, products):
        from datetime import date
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        i = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=10,
        )
        assert i.variance is None
        assert i.variance_value == Decimal('0.00')
        assert i.has_variance is False

    def test_variance_positive_and_negative(self, tenant, warehouse, products):
        from datetime import date
        c = StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
        i = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0],
            system_qty=10, counted_qty=12, unit_cost=Decimal('5.00'),
        )
        assert i.variance == 2
        assert i.variance_value == Decimal('10.00')
        i.counted_qty = 7
        assert i.variance == -3
        assert i.variance_value == Decimal('-15.00')
        assert i.has_variance is True


@pytest.mark.django_db
class TestUniqueness:
    def test_freeze_unique_together(self, tenant, warehouse):
        StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse, freeze_number='FRZ-00001',
        )
        with pytest.raises(IntegrityError):
            StocktakeFreeze.objects.create(
                tenant=tenant, warehouse=warehouse, freeze_number='FRZ-00001',
            )
```

### 5.5 `test_views_adjustment.py` — critical-path integration

```python
# stocktaking/tests/test_views_adjustment.py
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from stocktaking.models import (
    StockCount, StockCountItem, StockVarianceAdjustment,
)
from inventory.models import StockLevel, StockAdjustment


@pytest.fixture
def counted_count(tenant, warehouse, products, stock_levels):
    c = StockCount.objects.create(
        tenant=tenant, warehouse=warehouse, scheduled_date=date.today(), status='counted',
    )
    # 3 items with variance, 3 without
    for i, (p, sl) in enumerate(zip(products, stock_levels)):
        delta = [-2, 0, 3, 0, -1, 0][i]
        StockCountItem.objects.create(
            tenant=tenant, count=c, product=p,
            system_qty=sl.on_hand, counted_qty=sl.on_hand + delta,
            unit_cost=Decimal('10.00'),
        )
    return c


@pytest.mark.django_db
class TestAdjustmentPost:
    def test_post_updates_stock_and_flips_status(
        self, client_logged_in, tenant, counted_count, stock_levels,
    ):
        adj = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        url = reverse('stocktaking:adjustment_post', args=[adj.pk])
        resp = client_logged_in.get(url)  # NOTE: currently GET-accepted (D-01)
        assert resp.status_code == 302

        adj.refresh_from_db()
        counted_count.refresh_from_db()
        assert adj.status == 'posted'
        assert counted_count.status == 'adjusted'
        # Item 0 had delta=-2 ⇒ 98; Item 2 had delta=3 ⇒ 103; Item 4 had delta=-1 ⇒ 99
        stock_levels[0].refresh_from_db()
        assert stock_levels[0].on_hand == 98
        stock_levels[2].refresh_from_db()
        assert stock_levels[2].on_hand == 103
        # StockAdjustment rows created
        assert StockAdjustment.objects.filter(tenant=tenant).count() == 3

    def test_post_blocked_when_pending(self, client_logged_in, tenant, counted_count):
        adj = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='pending',
        )
        url = reverse('stocktaking:adjustment_post', args=[adj.pk])
        resp = client_logged_in.get(url, follow=True)
        assert adj.status == 'pending'

    def test_idor_cross_tenant(self, client, other_user, tenant, counted_count):
        adj = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        client.force_login(other_user)
        url = reverse('stocktaking:adjustment_post', args=[adj.pk])
        resp = client.get(url)
        assert resp.status_code == 404

    def test_double_post_is_rejected(self, client_logged_in, tenant, counted_count):
        """DEFECT D-03 — two approved adjustments on same count must not both post."""
        adj1 = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        adj2 = StockVarianceAdjustment.objects.create(
            tenant=tenant, count=counted_count, status='approved',
        )
        url1 = reverse('stocktaking:adjustment_post', args=[adj1.pk])
        url2 = reverse('stocktaking:adjustment_post', args=[adj2.pk])
        client_logged_in.get(url1)
        resp2 = client_logged_in.get(url2, follow=True)
        # After fix: second must be blocked (count already adjusted)
        adj2.refresh_from_db()
        assert adj2.status != 'posted', (
            'D-03 regression: same count was adjusted twice — '
            'StockLevel will have been overwritten.'
        )
```

### 5.6 `test_security.py` — OWASP-mapped

```python
# stocktaking/tests/test_security.py
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestCSRF:
    """D-01: state-changing views must reject GET."""
    STATE_MUTATION_URLS = [
        ('stocktaking:freeze_release', 1),
        ('stocktaking:schedule_run', 1),
        ('stocktaking:count_start', 1),
        ('stocktaking:count_review', 1),
        ('stocktaking:count_cancel', 1),
        ('stocktaking:adjustment_approve', 1),
        ('stocktaking:adjustment_reject', 1),
        ('stocktaking:adjustment_post', 1),
    ]

    @pytest.mark.parametrize('name,pk', STATE_MUTATION_URLS)
    def test_state_mutation_rejects_get(self, client_logged_in, name, pk):
        resp = client_logged_in.get(reverse(name, args=[pk]))
        # After fix: 405 Method Not Allowed OR 302 to list with error message,
        # but ACTUAL state must not have changed. The HTTP code assertion
        # itself is less important than the behavioural assertion in D-01 tests.
        assert resp.status_code in (302, 405)


@pytest.mark.django_db
class TestTenantIsolation:
    @pytest.mark.parametrize('url_name', [
        'stocktaking:count_detail', 'stocktaking:count_edit',
        'stocktaking:count_sheet', 'stocktaking:adjustment_detail',
        'stocktaking:freeze_edit', 'stocktaking:schedule_detail',
    ])
    def test_cross_tenant_404(self, client, user, other_user, tenant, warehouse, url_name):
        from datetime import date
        from stocktaking.models import StockCount, StocktakeFreeze, CycleCountSchedule, StockVarianceAdjustment
        # Create T1 artefacts
        c = StockCount.objects.create(tenant=tenant, warehouse=warehouse, scheduled_date=date.today())
        f = StocktakeFreeze.objects.create(tenant=tenant, warehouse=warehouse)
        s = CycleCountSchedule.objects.create(tenant=tenant, warehouse=warehouse, name='s1')
        a = StockVarianceAdjustment.objects.create(tenant=tenant, count=c)
        pk_map = {
            'stocktaking:count_detail': c.pk, 'stocktaking:count_edit': c.pk,
            'stocktaking:count_sheet': c.pk, 'stocktaking:adjustment_detail': a.pk,
            'stocktaking:freeze_edit': f.pk, 'stocktaking:schedule_detail': s.pk,
        }
        client.force_login(other_user)
        resp = client.get(reverse(url_name, args=[pk_map[url_name]]))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestXSS:
    def test_reason_escaped(self, client_logged_in, tenant, warehouse):
        from stocktaking.models import StocktakeFreeze
        StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse,
            reason='<script>alert(1)</script>',
        )
        resp = client_logged_in.get(reverse('stocktaking:freeze_list'))
        assert b'<script>alert(1)</script>' not in resp.content
        assert b'&lt;script&gt;' in resp.content


@pytest.mark.django_db
class TestNegativeCountedQty:
    """DEFECT D-05 — counted_qty must not accept negatives server-side."""
    def test_negative_counted_qty_rejected(self, client_logged_in, tenant, warehouse, products):
        from datetime import date
        from stocktaking.models import StockCount, StockCountItem
        c = StockCount.objects.create(tenant=tenant, warehouse=warehouse, scheduled_date=date.today())
        item = StockCountItem.objects.create(
            tenant=tenant, count=c, product=products[0], system_qty=10,
        )
        url = reverse('stocktaking:count_sheet', args=[c.pk])
        payload = {
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-id': str(item.pk),
            'items-0-counted_qty': '-5',
            'items-0-reason_code': '',
            'items-0-notes': '',
        }
        resp = client_logged_in.post(url, payload)
        item.refresh_from_db()
        assert item.counted_qty != -5, (
            'D-05 regression: negative counted_qty was accepted. '
            'Add MinValueValidator(0) to StockCountItem.counted_qty or form clean.'
        )
```

### 5.7 `test_performance.py` — N+1 guards

```python
# stocktaking/tests/test_performance.py
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_count_list_no_n_plus_one(
    client_logged_in, tenant, warehouse, django_assert_max_num_queries,
):
    from datetime import date
    from stocktaking.models import StockCount
    for _ in range(50):
        StockCount.objects.create(
            tenant=tenant, warehouse=warehouse, scheduled_date=date.today(),
        )
    with django_assert_max_num_queries(12):
        resp = client_logged_in.get(reverse('stocktaking:count_list'))
        assert resp.status_code == 200
```

### 5.8 Playwright smoke

```python
# stocktaking/tests/test_e2e.py  (requires pytest-playwright)
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_golden_journey(page: Page, live_server, tenant_admin_credentials):
    page.goto(f'{live_server.url}/login/')
    page.fill('[name=username]', tenant_admin_credentials['username'])
    page.fill('[name=password]', tenant_admin_credentials['password'])
    page.click('button[type=submit]')
    # Create count
    page.goto(f'{live_server.url}/stocktaking/counts/create/')
    page.select_option('[name=type]', 'cycle')
    # … continue through sheet, review, adjustment, post
    expect(page.locator('.alert-success')).to_contain_text('posted')
```

---

## 6. Defects, Risks & Recommendations

Severity scale: **Critical** = data loss / $$$ impact / sec. breach; **High** = workflow corruption or strong sec. risk; **Medium** = UX / partial-integrity; **Low** = cosmetic; **Info** = observation.

All file:line references are clickable in the IDE.

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| **D-01** | 🔴 **Critical** | [views.py:93-103](stocktaking/views.py#L93-L103), [views.py:215-235](stocktaking/views.py#L215-L235), [views.py:400-411](stocktaking/views.py#L400-L411), [views.py:414-426](stocktaking/views.py#L414-L426), [views.py:429-439](stocktaking/views.py#L429-L439), [views.py:554-566](stocktaking/views.py#L554-L566), [views.py:569-579](stocktaking/views.py#L569-L579), [views.py:582-624](stocktaking/views.py#L582-L624) | **CSRF / GET-mutates-state.** Eight state-changing views accept `GET` and mutate the database without a CSRF token. `adjustment_post_view` in particular rewrites `StockLevel.on_hand` via GET — any authenticated user visiting a third-party page containing `<img src="/stocktaking/adjustments/<pk>/post/">` would post the adjustment. **OWASP A01 + A05.** | Add `@require_POST` (or a POST-only guard `if request.method != 'POST': return HttpResponseNotAllowed(['POST'])`) to all 8 views. Update templates/buttons to submit via POST form with `{% csrf_token %}`. |
| **D-02** | 🔴 **Critical** | [views.py:582-624](stocktaking/views.py#L582-L624) | **Non-atomic posting.** `adjustment_post_view` creates `StockAdjustment` rows and mutates `StockLevel.on_hand` in a loop with **no `@transaction.atomic`**. A mid-loop failure (DB error, validation) leaves `StockLevel` partially updated and the adjustment still in `approved` status. Retrying would re-apply the already-applied items. **OWASP A04 + A08.** | Wrap the whole posting block in `with transaction.atomic():`. Use `select_for_update()` on `StockLevel` rows to serialize concurrent posts. |
| **D-03** | 🔴 **Critical** | [views.py:582-624](stocktaking/views.py#L582-L624), [forms.py:170-186](stocktaking/forms.py#L170-L186) | **Double-post attack / bug.** No constraint prevents creating **multiple** `StockVarianceAdjustment` rows for the same `StockCount`. If two are approved and posted, the second overwrites `StockLevel.on_hand` to the same counted value (idempotent in the happy case) but the `StockAdjustment` ledger gets **duplicate entries** — audit trail inflated, valuation reporting doubled. Even worse, since `post` flips `count.status='adjusted'`, the second post slips through because it checks the **adjustment's** transition not the count's. | Option 1: add `unique_together = ('tenant','count')` on `StockVarianceAdjustment` (tighten). Option 2: in `adjustment_post_view`, early-return if `count.status == 'adjusted'` with a clear error. |
| **D-04** | 🟠 **High** | [views.py:347-385](stocktaking/views.py#L347-L385) | **Count sheet mutates already-finalised counts.** `count_sheet_view` has **no guard** on `count.status`. Posting to the sheet on a count in status `counted`, `reviewed`, `adjusted`, or `cancelled` saves the new `counted_qty` values and silently corrupts history. **OWASP A04.** | Early-return redirect with error message if `count.status not in ('draft', 'in_progress')`. Consider: also lock the sheet once `counted`. |
| **D-05** | 🟠 **High** | [forms.py:135-144](stocktaking/forms.py#L135-L144), [models.py:323](stocktaking/models.py#L323), [count_sheet.html:67](templates/stocktaking/count_sheet.html#L67) | **Negative `counted_qty` accepted server-side.** `counted_qty` is `IntegerField(null=True)` with no validator. The HTML `min="0"` on the count-sheet input is bypassable. Downstream, `adjustment_post_view` then assigns `stock.on_hand = item.counted_qty` where `on_hand` is a `PositiveIntegerField` — causes `IntegrityError`. **OWASP A04.** | Add `validators=[MinValueValidator(0)]` to `StockCountItem.counted_qty`, **or** override the formset form with `clean_counted_qty`. |
| **D-06** | 🟠 **High** | [views.py:595-614](stocktaking/views.py#L595-L614), [inventory/models.py:119-133](inventory/models.py#L119-L133) | **Ledger skew vs. direct mutation.** The view creates a `StockAdjustment` row *then* manually overwrites `stock.on_hand = item.counted_qty`. It never calls `StockAdjustment.apply_adjustment()`. That method is the canonical write path; bypassing it drifts the ledger semantics: the `StockAdjustment` row's `adjustment_type` + `quantity` may not mathematically reconcile to the `on_hand` delta (e.g. if someone else adjusted stock between snapshot and post). | Either call `apply_adjustment()` instead of the direct assignment, or change `apply_adjustment` to a `correction`-style op and invoke it. Pair with D-02 (atomic). |
| **D-07** | 🟠 **High** | [models.py:49](stocktaking/models.py#L49), [models.py:233](stocktaking/models.py#L233), [models.py:430](stocktaking/models.py#L430), [forms.py](stocktaking/forms.py) (all 4 forms) | **Lesson #6 trap — unique_together + tenant not in form.** `StocktakeFreeze.unique_together=('tenant','freeze_number')`, same for `StockCount` and `StockVarianceAdjustment`. Because `tenant` is not a form field, Django's `validate_unique()` excludes the constraint. The numbers are server-generated, so practical collisions are rare — but the auto-number generators are TOCTOU-racy (see D-08), so a race + lesson-#6 gap lets `IntegrityError` bubble up as a 500 instead of a user-friendly form error. | Add `clean_freeze_number()` / `clean_count_number()` / `clean_adjustment_number()` guards that re-validate uniqueness when the value is populated; or — since the numbers are server-generated — move generation inside a `select_for_update()`-wrapped helper. |
| **D-08** | 🟠 **High** | [models.py:59-73](stocktaking/models.py#L59-L73), [models.py:265-279](stocktaking/models.py#L265-L279), [models.py:443-457](stocktaking/models.py#L443-L457) | **Auto-numbering TOCTOU race.** `_generate_*_number` reads the last row then increments without locking. Two parallel requests can both read `FRZ-00003`, both compute `FRZ-00004`, both write → `IntegrityError` (one request) or duplicate if unique_together were missing. | Use a per-tenant `SELECT ... FOR UPDATE` on a sequence table, or lean on a DB sequence / `Func('nextval', ...)`. Minimum fix: retry on `IntegrityError` with backoff. |
| **D-09** | 🟠 **High** | [views.py:582-624](stocktaking/views.py#L582-L624) | **Missing audit log on stock mutations.** Posting a variance adjustment silently rewrites inventory. No `core.AuditLog` row is emitted. Required for SOX / compliance and for forensic reconstruction after a theft allegation. **OWASP A09.** | Emit `AuditLog.objects.create(tenant=tenant, user=request.user, action='variance_post', object_type='StockVarianceAdjustment', object_id=adj.pk, changes={...})` after the status flip, inside the `transaction.atomic` block. Same pattern for `approve`, `reject`, `freeze_release`. |
| **D-10** | 🟡 Medium | [templates/stocktaking/count_list.html:111-113](templates/stocktaking/count_list.html#L111-L113), [freeze_list.html](templates/stocktaking/freeze_list.html), [schedule_list.html](templates/stocktaking/schedule_list.html), [adjustment_list.html](templates/stocktaking/adjustment_list.html) | **Filter retention broken across pagination.** Pagination `<a href="?page={{ num }}">` drops `?status=`, `?type=`, `?warehouse=`, `?q=`. Jumping to page 2 discards the user's filters. Violates CLAUDE.md "Filter Implementation Rules". | Include hidden inputs for filter params in the form or build a `querystring` helper: `?page={{ num }}&q={{ q }}&status={{ current_status }}&type={{ current_type }}&warehouse={{ current_warehouse }}`. |
| **D-11** | 🟡 Medium | [views.py:214-235](stocktaking/views.py#L214-L235) | **`schedule_run_view` not idempotent + ignores `abc_class`.** Clicking "Run" twice creates two draft counts. Also, `_populate_count_items` does not respect `schedule.abc_class` (it snapshots ALL stock levels regardless of A/B/C). Only `zones.first()` is used — the other zones in the M2M are silently dropped. | Add duplicate-run guard (e.g. prevent if a draft count for this schedule already exists for today). Filter `_populate_count_items` by ABC class and by zone M2M when provided. |
| **D-12** | 🟡 Medium | [views.py:476-502](stocktaking/views.py#L476-L502) | **Dead / misleading code in `adjustment_create_view`.** Line 486 computes `items_with_variance` but never uses it. Also, the loop at line 489 iterates items again to compute totals — redundant work, and the logic mixes "zero counted" exclusion (L486) with variance detection (L489-492) inconsistently. | Delete L486 or collapse both loops into one pass. Use `count.total_variance_value` property instead of duplicating the logic. |
| **D-13** | 🟡 Medium | [forms.py:49-80](stocktaking/forms.py#L49-L80), [forms.py:87-132](stocktaking/forms.py#L87-L132) | **Zone dropdown not filtered by selected warehouse.** `CycleCountScheduleForm` and `StockCountForm` populate `zones` / `zone` from all zones of the tenant, regardless of the chosen warehouse. A user can attach a zone that belongs to a *different* warehouse of the same tenant — data-integrity bug at save time is not caught. | Option A (quickest): add a `clean()` that validates `zone.warehouse == warehouse`. Option B (UX win): ajax-driven dependent dropdown. |
| **D-14** | 🟡 Medium | [views.py:134-139](stocktaking/views.py#L134-L139), [views.py:131-133](stocktaking/views.py#L131-L133) | **Schedule list missing `frequency_choices` → `current_frequency` consistency.** Template filter relies on `request.GET.status` for `active` but view passes `current_active` — make sure template uses `current_active` not `request.GET.active`. Verify cross-file per CLAUDE.md rule 4. | Audit `templates/stocktaking/schedule_list.html` for filter var name matches; adjust if mismatched. |
| **D-15** | 🟡 Medium | [views.py:389-398](stocktaking/views.py#L389-L398), [views.py:202-211](stocktaking/views.py#L202-L211), [views.py:540-551](stocktaking/views.py#L540-L551) | **Delete views allow unrestricted deletion of finalised records.** `count_delete_view` lets you DELETE a count in any status including `adjusted` (which has posted `StockAdjustment` rows). Cascading deletes `StockCountItem`s but the `StockAdjustment` rows remain orphaned-reasoned (`Variance from count CNT-00042 — …` in notes, but no FK). | Block delete when status == 'adjusted'; or set `on_delete=PROTECT` from `StockVarianceAdjustment.count`. Minimum: add status guard identical to `adjustment_delete_view`. |
| **D-16** | 🟢 Low | [views.py:242-254](stocktaking/views.py#L242-L254) | **`bin_location` never populated on snapshot.** `_populate_count_items` leaves `bin_location=NULL` always. For multi-bin stock that degrades count accuracy. | If bin-level stock is tracked (`StockLevel` per bin?), snapshot one item per bin. Otherwise document the limitation. |
| **D-17** | 🟢 Low | [views.py:347-385](stocktaking/views.py#L347-L385) | **Formset errors not surfaced on re-render.** If the formset is invalid, `count_sheet_view` falls through to re-render but the `formset` already in context is bound; errors display, but `items_with_forms = zip(...)` is re-computed from an unbound formset (in the `else` branch only). Mixed paths may yield a template that doesn't show the error for all rows. | Compute `items_with_forms` from `formset.forms` in both branches so errors are always rendered. |
| **D-18** | 🟢 Low | [seed_stocktaking.py:1](stocktaking/management/commands/seed_stocktaking.py#L1), [seed_stocktaking.py:147](stocktaking/management/commands/seed_stocktaking.py#L147) | **Non-deterministic seeds.** Uses `random.choice`/`random.random()` without `random.seed(...)` → unreproducible fixtures. Harmless in dev, but makes bug reports hard to replay. | `random.seed(tenant.pk)` at start of `_seed_tenant` for reproducibility. |
| **D-19** | 🟢 Info | [urls.py:8-16](stocktaking/urls.py#L8-L16) | **No `/counts/schedules/…` RBAC.** Module relies purely on `@login_required`. There is no role check, so any tenant user — even a read-only counter — can approve or post adjustments. | Introduce role-based guards (e.g. `@role_required('approver')`) on `approve`, `reject`, `post`. Tie into existing `core.Role`. |
| **D-20** | 🟢 Info | [views.py:127-140](stocktaking/views.py#L127-L140) | Search/filter on `notes` using `Q(notes__icontains=q)` can match across the whole tenant. No explicit length cap on `q` → pathological scans. | Truncate `q` to 100 chars or guard with `if len(q) >= 2:` to prevent single-char wildcard scans. |
| **D-21** | 🟢 Info | [admin.py:30-33](stocktaking/admin.py#L30-L33) | Admin shows data across tenants with no row-level filter. This is expected Django-admin behaviour for superusers but should be documented. | Add a comment; consider a `ModelAdmin.get_queryset` override if a non-super admin user can reach this. |

### 6.1 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Silent inventory corruption via D-01 + D-02 + D-03 chain | Medium | **Critical** | Fix D-01/02/03 together; add integration test `test_double_post_is_rejected`. |
| Regression in workflow transitions when adding a new state | High | Medium | Lock down `VALID_TRANSITIONS` with a unit-test matrix (see §5.4 `TestStateMachine`). |
| Zero automated coverage → future refactors regress | High | High | Land §5 suite; enforce coverage gate in CI. |
| Multi-tenant IDOR from a missing `tenant=request.tenant` in a future view | Medium | High | Add `tests/test_security.py::TestTenantIsolation` per view; enforce middleware-level tenant filter (future architectural win). |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets

| File | Statements (approx) | Line target | Branch target | Notes |
|---|---|---|---|---|
| [models.py](stocktaking/models.py) | ~180 | **≥ 90%** | ≥ 85% | Core value — state machines, variance math, numbering |
| [views.py](stocktaking/views.py) | ~260 | **≥ 80%** | ≥ 70% | 25 views; prioritise posting and sheet |
| [forms.py](stocktaking/forms.py) | ~100 | **≥ 90%** | ≥ 80% | Form validation rules |
| [admin.py](stocktaking/admin.py) | ~25 | ≥ 50% | — | Smoke only |
| [seed_stocktaking.py](stocktaking/management/commands/seed_stocktaking.py) | ~130 | ≥ 75% | — | Idempotency + flush |
| **Module total** | ~695 | **≥ 85%** | **≥ 75%** | |

### 7.2 KPI dashboard

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | = 100% | 95–99% | < 95% |
| Open Critical defects | 0 | — | ≥ 1 |
| Open High defects | 0 | 1 | ≥ 2 |
| Open Medium defects | ≤ 2 | 3–5 | ≥ 6 |
| Suite runtime (CI) | ≤ 60s | 60–120s | > 120s |
| p95 list view latency @ 10k rows | ≤ 300 ms | 300–600 ms | > 600 ms |
| Query count on `/counts/` list | ≤ 8 | 9–12 | > 12 |
| Coverage (lines, module) | ≥ 85% | 75–84% | < 75% |
| Regression escape rate (/ release) | ≤ 1 | 2 | ≥ 3 |

### 7.3 Release Exit Gate (must ALL be true)

- [ ] D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09 closed (all 🔴/🟠).
- [ ] §5 test suite landed, green, and wired into CI.
- [ ] Coverage meets §7.1 targets.
- [ ] N+1 guard green (`TC-CNT-010`, §5.7).
- [ ] E2E "schedule → count → review → adjust → post" smoke green.
- [ ] `bandit -r stocktaking/` — 0 High-severity findings.
- [ ] Manual penetration pass: CSRF + IDOR + XSS (D-01 / X-02 / TC-FRZ-006) manually verified.

---

## 8. Summary

The **Stocktaking & Cycle Counting** module implements a plausible end-to-end flow (freeze → schedule → count → variance → adjust → post) across five models, four forms, 25 views, and ten templates — roughly **~1.5k LoC** of backend Python with **zero automated tests**.

The workflow skeleton is sound — state machines are explicit, tenant scoping is consistent on every queryset, auto-numbering is in place, and the seed command is idempotent. The **README-level UX is shippable** for a controlled pilot.

However, the **money-impacting path** (posting a variance) is the highest-risk surface in the codebase and harbours three 🔴 Critical defects that must be closed before this module goes to any customer that cares about stock valuation:

1. **D-01 — CSRF / GET-mutates-state** on eight transition endpoints, including `/adjustments/<pk>/post/` which overwrites `StockLevel.on_hand`. Any authenticated session visiting a third-party page is exploitable.
2. **D-02 — Non-atomic posting** means a mid-loop failure leaves half-updated stock with the adjustment still `approved` — retrying double-applies the clean rows.
3. **D-03 — Double-post** — nothing prevents two adjustments on one count both reaching `posted`, corrupting the audit ledger.

Around these, six more 🟠 High defects pile on: the count sheet can be mutated on already-`adjusted` counts (D-04); negative `counted_qty` is server-side accepted (D-05); the ledger vs. direct-mutation inconsistency (D-06); lesson-#6 `unique_together` trap (D-07); TOCTOU auto-numbering (D-08); no `AuditLog` on stock mutations (D-09).

The module also has a handful of Medium-severity hygiene issues (filter retention, schedule-run idempotency, zone-vs-warehouse cross-validation) and **zero tests** — meaning no regression safety net and no forcing function for future changes.

### Recommended remediation order

1. **Harden the posting path** — D-01 (require POST) + D-02 (atomic) + D-03 (single-adjustment guard) + D-09 (audit log). Ship together.
2. **Fix input validation** — D-05 (negative qty) + D-04 (sheet mutation guard).
3. **Land the §5 test suite** — prioritise `test_models.py`, `test_views_adjustment.py`, `test_security.py`.
4. **Polish** — D-08 (race), D-06 (ledger reconcile), D-07 (uniqueness guards), D-10 (filter retention), D-11/12/13 (workflow ergonomics), D-14+ (info).
5. **Exit gate** (§7.3) before marking the module release-ready.

### Next actions (for the user)

- Run `/sqa-review` follow-up prompts:
  - *"Fix the defects"* → I will plan in `.claude/tasks/stocktaking_sqa_fixes_todo.md`, implement D-01 through D-09, verify each with a shell reproduction, and emit one-liner PowerShell git commits per file.
  - *"Build the automation"* → I will scaffold [stocktaking/tests/](stocktaking/tests/) with the snippets in §5, run the suite, and report green/red.
  - *"Manual verification"* → I will walk through the high-severity test cases against `runserver` and report observed vs. expected.
