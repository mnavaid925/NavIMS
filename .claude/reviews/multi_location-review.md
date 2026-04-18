# Multi-Location Management — Comprehensive SQA Test Report

**Target:** [multi_location/](multi_location/) Django app — 4 models, 21 views, 4 `ModelForm`s, 11 templates, 1 seed command.
**Scope mode:** Module review (end-to-end).
**Codebase reference commit:** `45ad075` (branch `main`).
**Verification:** All High/Critical defects reproduced via Django shell against [config/settings_test.py](config/settings_test.py) SQLite in-memory.

---

## 1. Module Analysis

### 1.1 Surface inventory

| Component | File | Public entities |
|---|---|---|
| Models | [multi_location/models.py](multi_location/models.py) | `Location` (with self-FK hierarchy), `LocationPricingRule`, `LocationTransferRule`, `LocationSafetyStockRule` |
| Forms | [multi_location/forms.py](multi_location/forms.py) | `LocationForm`, `LocationPricingRuleForm`, `LocationTransferRuleForm`, `LocationSafetyStockRuleForm` |
| Views | [multi_location/views.py](multi_location/views.py) | 21 function-based views: Location CRUD (5) + stock-visibility (1) + PricingRule CRUD (5) + TransferRule CRUD (5) + SafetyStockRule CRUD (5) |
| URLs | [multi_location/urls.py](multi_location/urls.py) | `app_name='multi_location'`, 21 routes |
| Admin | [multi_location/admin.py](multi_location/admin.py) | 4 `ModelAdmin` registrations |
| Seed | [multi_location/management/commands/seed_multi_location.py](multi_location/management/commands/seed_multi_location.py) | `seed_multi_location --flush` |
| Templates | [templates/multi_location/](templates/multi_location/) | 11 templates (list/detail/form per entity + stock_visibility) |
| Migrations | [multi_location/migrations/0001_initial.py](multi_location/migrations/0001_initial.py) | Initial only |

### 1.2 Cross-module dependencies

| Upstream | Used for |
|---|---|
| [core/models.py](core/models.py) — `Tenant` | Multi-tenant FK on every model |
| [core/middleware.py:1-13](core/middleware.py#L1-L13) — `TenantMiddleware` | Sets `request.tenant` from user |
| [warehousing/models.py](warehousing/models.py) — `Warehouse` | Optional link for stock roll-up |
| [catalog/models.py](catalog/models.py) — `Product`, `Category` | Scope of pricing / safety-stock rules |
| [inventory/models.py](inventory/models.py) — `StockLevel` | Source of truth for stock-visibility aggregates |

### 1.3 Business rules (file:line)

| Rule | Enforced where | Status |
|---|---|---|
| Location code is unique per tenant | `unique_together = ('tenant', 'code')` — [multi_location/models.py:58](multi_location/models.py#L58) | DB-level only |
| Auto-generate code `LOC-NNNNN` when blank | [multi_location/models.py:89-108](multi_location/models.py#L89-L108) | **BROKEN — see D-02** |
| Parent FK nullable, `SET_NULL` on delete | [multi_location/models.py:25-30](multi_location/models.py#L25-L30) | OK |
| Prevent self-referential / descendant parent on edit | [multi_location/forms.py:44-48](multi_location/forms.py#L44-L48) | OK via queryset exclude — form-layer only |
| Pricing rule: product XOR category | [multi_location/forms.py:102-108](multi_location/forms.py#L102-L108) | OK |
| Transfer rule: source ≠ destination | [multi_location/forms.py:153-159](multi_location/forms.py#L153-L159) | OK |
| Transfer rule unique `(tenant, source, dest)` | [multi_location/models.py:201](multi_location/models.py#L201) | DB-level only — **form has no duplicate guard (see D-11)** |
| Safety-stock rule unique `(tenant, location, product)` | [multi_location/models.py:235](multi_location/models.py#L235) | DB-level only — **form has no duplicate guard (see D-11)** |
| Tenant scoping on every view | [multi_location/views.py](multi_location/views.py) — `filter(tenant=request.tenant)` on every queryset | OK |
| `requires_approval`, `max_transfer_qty`, `lead_time_days` enforcement | — | **Unconsumed (design gap — see D-14)** |

### 1.4 Pre-test risk profile

| Risk area | Level | Rationale |
|---|---|---|
| Input validation (non-numeric filter params) | **CRITICAL** | Five list views crash on `?<field>=abc` (reproduced) |
| Location-code generator | **HIGH** | Resets to `LOC-00001` whenever last-inserted record is non-LOC → `IntegrityError` (reproduced) |
| Cycle detection in hierarchy | **HIGH** | `get_descendant_ids` and `full_path` have no cycle guard — admin-direct edit hangs server |
| Business-rule validation | **HIGH** | Safety-stock bounds, pricing-rule `value` sign/range, effective-date ordering all unchecked |
| Tenant isolation | LOW | Form querysets correctly filter on tenant; superuser (tenant=None) path degrades safely |
| Permission / RBAC | MEDIUM | Only `@login_required` — no role check. Any authenticated tenant user can create/edit/delete any location or rule |
| Audit logging | MEDIUM | `core.AuditLog` is **not emitted** by any multi_location view |
| XSS / auto-escape | LOW | Verified — `<script>` in `location.name` escapes correctly |
| Filter retention across pagination | **HIGH** | Four of five list pages drop query params in pagination links — regression of CLAUDE.md §Filter Implementation Rules |
| Performance (descendant traversal, stock-visibility) | MEDIUM | `get_descendant_ids` uses per-iteration DB query; stock visibility runs 4 aggregates + count |

---

## 2. Test Plan

### 2.1 Test objectives

- Verify tenant isolation, CRUD completeness, business-rule enforcement, hierarchy integrity, and pricing/transfer/safety-stock rule correctness for the Multi-Location Management app.
- Confirm no open OWASP Top-10 findings (with module scope: A01, A03, A04, A05, A07, A09).
- Provide automated regression coverage so the defects captured in §6 cannot silently reappear.

### 2.2 Test types & coverage targets

| Type | Scope | Target |
|---|---|---|
| Unit | Model methods (`full_path`, `get_descendant_ids`, `_generate_code`, `scope_display`, `children_count`) | ≥ 90 % branch |
| Form | `clean()` rules, cross-field, cross-tenant rejection, unique-together guards | 100 % of `clean*` |
| Integration | View + form + DB for all 21 views | Each view hit positive + negative |
| Functional | End-to-end: create hierarchy → link warehouse → create rules → paginate → filter → delete | Playwright smoke |
| Regression | Filter retention, decimal edge cases, descendant cycle detection | 100 % of defects in §6 |
| Boundary | `max_length`, `PositiveIntegerField`, `DecimalField` precision, date range | Per-field |
| Edge | Empty tenant data, single tenant with 1000 locations, unicode names, emoji codes | Smoke only |
| Negative | Non-numeric filter param, cross-tenant pk, missing CSRF, GET-on-delete, `pk=999999` | Parametrised |
| Security | A01 IDOR, A03 injection / XSS, A04 insecure design, A05 misconfig, A07 auth, A09 logging | Dedicated suite |
| Performance | N+1 on `get_descendant_ids`, list views, stock-visibility aggregate count | `django_assert_max_num_queries` |
| Scalability | `stock_visibility_view` with 5 000 stock levels | Locust 100 RPS |

### 2.3 Entry criteria

- Branch builds locally (`python manage.py check` clean).
- Test DB migrates cleanly via [config/settings_test.py](config/settings_test.py).
- [multi_location/management/commands/seed_multi_location.py](multi_location/management/commands/seed_multi_location.py) runs idempotently.

### 2.4 Exit criteria (Release Gate)

All of the following must be true:

- 0 Critical and 0 High open defects.
- Test suite green with ≥ 85 % line / 75 % branch coverage on `multi_location/`.
- `bandit -r multi_location` reports no High/Medium.
- Every list view can be hit with `?<filter>=abc` without raising 5xx.
- Every pagination link on every list page preserves the active query-string filters.
- `pytest multi_location/tests -q -k security` green.

---

## 3. Test Scenarios

### 3.1 Location entity (`LOC-*`)

| #   | Scenario                                                                                     | Type          |
| --- | -------------------------------------------------------------------------------------------- | ------------- |
| L-01| Create location with auto-generated code (`LOC-00001`)                                       | Unit          |
| L-02| Auto-code collides when last-inserted location has non-LOC code prefix (**D-02**)            | Regression    |
| L-03| Auto-code collides when `LOC-99999` already exists and a new Location is inserted            | Boundary      |
| L-04| Create with explicit code — duplicate `(tenant, code)` rejected                              | Negative      |
| L-05| Create under a parent — parent stored, `full_path` renders breadcrumb                        | Unit          |
| L-06| Edit self-parent — rejected by form queryset                                                 | Negative      |
| L-07| Edit descendant-parent — rejected by form queryset                                           | Negative      |
| L-08| Admin/shell bypass sets `A.parent=B` while `B.parent=A` — `get_descendant_ids` infinite loop (**D-08**) | Security/DoS |
| L-09| `full_path` with cycle — should truncate, not recurse (**D-09**)                             | Regression    |
| L-10| Link to warehouse of same tenant — stock summary rolls up                                    | Integration   |
| L-11| Link to warehouse of another tenant — rejected by form queryset                              | Negative      |
| L-12| Soft-delete (is_active=False) excludes location from `pricing_rule` / `transfer_rule` form lists | Regression |
| L-13| Delete cascades to pricing / transfer / safety-stock rules; `SET_NULL` on children           | Integration   |
| L-14| List page `?type=retail_store` filter                                                        | Integration   |
| L-15| List page `?parent=<pk>` filter                                                              | Integration   |
| L-16| List page `?parent=abc` (non-numeric) — 500 (**D-01**)                                       | Negative      |
| L-17| List page pagination preserves `q`, `type`, `active`, `parent` (**D-10**)                    | Regression    |
| L-18| XSS — `name="<script>alert(1)</script>"` escapes on list / detail                            | Security (A03)|
| L-19| CSRF — POST `/locations/<pk>/delete/` without token → 403                                    | Security      |
| L-20| GET `/locations/<pk>/delete/` — no destructive action, redirect                              | Security      |
| L-21| Cross-tenant detail — `GET /locations/<other_tenant_pk>/` → 404                              | Security (A01)|
| L-22| Superuser (tenant=None) — list empty, no 500, no cross-tenant leak                           | Security      |
| L-23| `location_type` choice not in choices — rejected                                             | Negative      |
| L-24| Unicode / emoji in name                                                                      | Edge          |
| L-25| Manager email with invalid format — rejected                                                 | Negative      |

### 3.2 Pricing Rule (`P-*`)

| #   | Scenario                                                                            | Type        |
| --- | ----------------------------------------------------------------------------------- | ----------- |
| P-01| Create markup % rule with category scope                                            | Unit        |
| P-02| Create override-price rule with product scope                                       | Unit        |
| P-03| Reject when both product AND category selected                                      | Negative    |
| P-04| Accept when neither selected (applies to all products)                              | Unit        |
| P-05| `value < 0` on override_price — **currently accepted (D-06)**                       | Regression  |
| P-06| `value = 9999.99` on markup_pct — **currently accepted (D-07)**                     | Regression  |
| P-07| `effective_from > effective_to` — **currently accepted (D-05)**                     | Regression  |
| P-08| List `?location=abc` (non-numeric) — 500 (**D-01**)                                 | Negative    |
| P-09| List `?rule_type=invalid` filter silently ignored                                   | Edge        |
| P-10| Pagination retains `location`, `rule_type`, `active`, `q` (**D-10**)                | Regression  |
| P-11| Delete rule via POST — success; GET → redirect without delete                       | Security    |
| P-12| Cross-tenant pk in URL → 404                                                         | Security (A01)|
| P-13| Concurrent create of same `(location, product, rule_type, priority)` — both succeed (intentional? see D-14) | Design    |

### 3.3 Transfer Rule (`T-*`)

| #   | Scenario                                                                            | Type         |
| --- | ----------------------------------------------------------------------------------- | ------------ |
| T-01| Create rule source≠dest, allowed=True                                               | Unit         |
| T-02| Reject source == destination                                                        | Negative     |
| T-03| Duplicate `(tenant, source, destination)` — form currently fails with 500 IntegrityError (**D-11**) | Negative |
| T-04| `max_transfer_qty=0` — displayed as ∞                                               | Unit         |
| T-05| `requires_approval=True` — flag stored but **unconsumed** by downstream (D-14)      | Design       |
| T-06| List `?source=abc` / `?destination=abc` → 500 (**D-01**)                            | Negative     |
| T-07| Pagination retains `source`, `destination`, `allowed`, `q` (**D-10**)               | Regression   |
| T-08| Delete rule — POST 200; GET → redirect                                              | Security     |
| T-09| Cross-tenant source / destination selection — rejected by form queryset             | Security (A01)|
| T-10| Edit blocks source↔destination chain transitively — not enforced (design)           | Design       |

### 3.4 Safety Stock Rule (`S-*`)

| #   | Scenario                                                                            | Type         |
| --- | ----------------------------------------------------------------------------------- | ------------ |
| S-01| Create rule with `safety_stock_qty < reorder_point < max_stock_qty`                 | Unit         |
| S-02| `safety_stock_qty > reorder_point` — **currently accepted (D-04)**                  | Regression   |
| S-03| `max_stock_qty < reorder_point` (non-zero) — **currently accepted (D-04)**          | Regression   |
| S-04| Duplicate `(tenant, location, product)` — form returns 500 IntegrityError (**D-11**)| Negative     |
| S-05| List `?location=abc` / `?product=abc` → 500 (**D-01**)                              | Negative     |
| S-06| Pagination retains filters (**D-10**)                                               | Regression   |
| S-07| Detail — `stock_level` lookup uses location.warehouse; None warehouse safely handled | Edge        |
| S-08| Cross-tenant product pk — rejected by form queryset                                 | Security (A01)|

### 3.5 Stock Visibility (`V-*`)

| #   | Scenario                                                                            | Type        |
| --- | ----------------------------------------------------------------------------------- | ----------- |
| V-01| Default page — linked_locations count, stats.total_on_hand, total_value correct     | Integration |
| V-02| `?location=<pk>` filters by descendant warehouse ids                                | Integration |
| V-03| `?location=abc` → 500 (**D-01**)                                                    | Negative    |
| V-04| `?low_stock=1` filters by `on_hand<=reorder_point`                                   | Integration |
| V-05| `?q=SKU-123` filters by product SKU                                                 | Integration |
| V-06| Pagination retains `q`, `location`, `low_stock` (template uses explicit concat — OK)| Regression  |
| V-07| Cross-tenant location pk — `DoesNotExist` path silently ignores filter (poor UX)    | Edge        |
| V-08| Tenant with 5 000 stock levels — p95 < 500 ms                                       | Performance |
| V-09| Superuser (tenant=None) — `linked_locations` empty, no 500                          | Security    |

### 3.6 Seed / management command (`M-*`)

| #   | Scenario                                                                            | Type        |
| --- | ----------------------------------------------------------------------------------- | ----------- |
| M-01| Run `seed_multi_location` on empty DB — creates 7 locations, 4 pricing, 4 transfer, 10 safety-stock per tenant | Integration |
| M-02| Re-run without `--flush` — skipped, idempotent (prints "already exists")           | Integration |
| M-03| `--flush` — old data cleared before re-seed                                         | Integration |
| M-04| No active tenants — command exits with warning                                      | Edge        |
| M-05| Tenant with no warehouses — seeding skipped for that tenant                         | Edge        |

---

## 4. Detailed Test Cases

Representative subset — full suite (~80 cases) is scaffolded in §5.

### TC-LOC-001 · Auto-generated code

| Field | Value |
|---|---|
| ID | TC-LOC-001 |
| Description | Creating a Location with `code=''` generates `LOC-00001` on the first insert and increments sequentially. |
| Pre-conditions | Tenant with no Locations. |
| Steps | 1. `Location.objects.create(tenant=t, name='HQ')` 2. `Location.objects.create(tenant=t, name='DC')` |
| Test Data | `name='HQ'`, `name='DC'` |
| Expected Result | First instance → `code='LOC-00001'`; second → `LOC-00002`; no IntegrityError. |
| Post-conditions | 2 rows in `multi_location_location`. |

### TC-LOC-002 · Auto-code collision (regression for D-02)

| Field | Value |
|---|---|
| ID | TC-LOC-002 |
| Description | After a non-`LOC-` code is the most recent insert, the next auto-gen must not reset to `LOC-00001` if that code already exists. |
| Pre-conditions | Tenant has `LOC-00001` and a later-inserted row with code `STORE-01`. |
| Steps | `Location.objects.create(tenant=t, name='New')` |
| Test Data | `code=''` (auto) |
| Expected Result | Assigned the next unused `LOC-NNNNN` (e.g., `LOC-00002`) — **not** `LOC-00001`. No IntegrityError. |
| Post-conditions | Unique constraint holds. |

### TC-LOC-003 · Cycle DoS guard (regression for D-08)

| Field | Value |
|---|---|
| ID | TC-LOC-003 |
| Description | If `A.parent=B` and `B.parent=A` exist (admin or raw SQL bypass), `get_descendant_ids()` must terminate. |
| Pre-conditions | Two locations A, B. |
| Steps | 1. `a.parent=b; a.save()` 2. `b.parent=a; b.save()` 3. `a.get_descendant_ids()` |
| Test Data | — |
| Expected Result | Returns a finite list in < 1 s; no infinite loop / recursion / memory blow-up. |
| Post-conditions | — |

### TC-PRIC-001 · Pricing value bounds (regression for D-06/D-07)

| Field | Value |
|---|---|
| ID | TC-PRIC-001 |
| Description | `rule_type='override_price'` must reject negative values; `rule_type='markup_pct'` must reject values > 1000. |
| Pre-conditions | Tenant has ≥1 active Location. |
| Steps | POST to `pricing_rule_create` with `value=-10` (override) and `value=9999` (markup). |
| Test Data | See Description |
| Expected Result | Both rejected with field-level `forms.ValidationError`. |
| Post-conditions | No rows created. |

### TC-SAFE-001 · Safety-stock bounds (regression for D-04)

| Field | Value |
|---|---|
| ID | TC-SAFE-001 |
| Description | Rule must enforce `safety_stock_qty ≤ reorder_point ≤ max_stock_qty` (when `max_stock_qty>0`). |
| Pre-conditions | Tenant with location + product. |
| Steps | POST with `safety_stock_qty=100, reorder_point=10, max_stock_qty=5`. |
| Test Data | See Description |
| Expected Result | Form invalid with non-field error. |
| Post-conditions | No row created. |

### TC-SEC-001 · Non-numeric filter param (regression for D-01)

| Field | Value |
|---|---|
| ID | TC-SEC-001 |
| Description | Every list view must respond 200 (not 500) when its FK filter param is non-numeric. |
| Pre-conditions | Authenticated tenant admin. |
| Steps | Parametrised `GET` over: `/multi-location/?parent=abc`, `/pricing-rules/?location=abc`, `/transfer-rules/?source=abc`, `/safety-stock-rules/?product=abc`, `/stock-visibility/?location=abc`. |
| Test Data | `abc`, `1' OR '1'='1`, `9999999999999999999`, `../etc/passwd` |
| Expected Result | HTTP 200 with an empty-filter result set; no ValueError propagates. |
| Post-conditions | — |

### TC-SEC-002 · Pagination retains filters (regression for D-10)

| Field | Value |
|---|---|
| ID | TC-SEC-002 |
| Description | Pagination links on every list page must append existing query-string filters. |
| Pre-conditions | Tenant with ≥ 21 records in the target list (to force pagination). |
| Steps | `GET /multi-location/?q=Seattle&type=retail_store` → inspect `?page=2` links. |
| Test Data | filter combos per list |
| Expected Result | Generated `href` includes `q=Seattle&type=retail_store` alongside `page=2`. |
| Post-conditions | — |

### TC-SEC-003 · Cross-tenant IDOR on detail / edit / delete

| Field | Value |
|---|---|
| ID | TC-SEC-003 |
| Description | Detail/edit/delete views must 404 when the pk belongs to another tenant. |
| Pre-conditions | Tenants A and B; record R exists under B. |
| Steps | As A-admin: `GET /multi-location/locations/<R.pk>/`, same for rule detail/edit/delete URLs. |
| Test Data | 5 entity types × 3 verbs |
| Expected Result | HTTP 404 for all. No cross-tenant data in response. |
| Post-conditions | — |

### TC-PERF-001 · `get_descendant_ids` N+1

| Field | Value |
|---|---|
| ID | TC-PERF-001 |
| Description | For a 4-level hierarchy with 100 total locations, traversal must execute ≤ 5 queries. |
| Pre-conditions | Seeded 4-level tree. |
| Steps | `with django_assert_max_num_queries(5): root.get_descendant_ids(include_self=True)` |
| Test Data | 100-node tree |
| Expected Result | Passes. (Current implementation issues one query per depth level — would likely fail.) |
| Post-conditions | — |

---

## 5. Automation Strategy

### 5.1 Tool stack

| Layer | Tool |
|---|---|
| Unit / integration | pytest 8, pytest-django, factory-boy |
| Fixtures | pytest fixtures (reuse shape of [inventory/tests/conftest.py](inventory/tests/conftest.py)) |
| E2E smoke | Playwright (already used elsewhere) |
| Load | Locust |
| Security static | bandit, ruff-sec |
| Dynamic | OWASP ZAP baseline scan on a disposable container |

### 5.2 Suite layout

```
multi_location/
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_forms.py
    ├── test_views_location.py
    ├── test_views_pricing.py
    ├── test_views_transfer.py
    ├── test_views_safety_stock.py
    ├── test_views_stock_visibility.py
    ├── test_security.py
    ├── test_performance.py
    └── test_seed.py
```

Also add `multi_location/tests` to the `testpaths` of [pytest.ini](pytest.ini).

### 5.3 `conftest.py` — fixtures

```python
# multi_location/tests/conftest.py
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import StockLevel
from multi_location.models import (
    Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
)

User = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Test", slug="acme-test")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Globex Test", slug="globex-test")


@pytest.fixture
def admin_user(db, tenant):
    return User.objects.create_user(
        username="ml_admin", password="pw_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def other_tenant_user(db, other_tenant):
    return User.objects.create_user(
        username="ml_other", password="pw_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code="WH-01", name="Main", is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Supplies")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku="SUP-001", name="Widget",
        category=category, purchase_cost=Decimal("10"), retail_price=Decimal("15"),
        status="active",
    )


@pytest.fixture
def company(db, tenant):
    return Location.objects.create(tenant=tenant, name="HQ", location_type="company")


@pytest.fixture
def region(db, tenant, company):
    return Location.objects.create(tenant=tenant, name="North", location_type="regional_dc", parent=company)


@pytest.fixture
def dc(db, tenant, region, warehouse):
    return Location.objects.create(
        tenant=tenant, name="Seattle DC", location_type="distribution_center",
        parent=region, warehouse=warehouse,
    )


@pytest.fixture
def store(db, tenant, region):
    return Location.objects.create(
        tenant=tenant, name="Seattle Store", location_type="retail_store", parent=region,
    )


@pytest.fixture
def stock_level(db, tenant, product, warehouse):
    return StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=100, allocated=10, reorder_point=20, reorder_quantity=50,
    )
```

### 5.4 `test_models.py`

```python
from decimal import Decimal

import pytest

from multi_location.models import Location


@pytest.mark.django_db
class TestLocationCodeGenerator:
    def test_auto_code_first_insert(self, tenant):
        loc = Location.objects.create(tenant=tenant, name="HQ")
        assert loc.code == "LOC-00001"

    def test_auto_code_sequential(self, tenant):
        Location.objects.create(tenant=tenant, name="HQ")
        loc2 = Location.objects.create(tenant=tenant, name="DC")
        assert loc2.code == "LOC-00002"

    def test_auto_code_does_not_collide_after_non_loc_prefix(self, tenant):
        """Regression for D-02: last-insert non-LOC must not reset numbering."""
        Location.objects.create(tenant=tenant, name="A")            # LOC-00001
        Location.objects.create(tenant=tenant, name="X", code="STORE-01")
        loc3 = Location.objects.create(tenant=tenant, name="B")     # expected LOC-00002
        assert loc3.code != "LOC-00001"
        # Must be unique per tenant regardless
        assert Location.objects.filter(tenant=tenant, code=loc3.code).count() == 1


@pytest.mark.django_db
class TestLocationHierarchy:
    def test_full_path_3_levels(self, tenant, company, region, dc):
        assert dc.full_path == "HQ > North > Seattle DC"

    def test_full_path_cycle_guarded(self, tenant):
        """Regression for D-09: cycle must not render infinite path."""
        a = Location.objects.create(tenant=tenant, name="A")
        b = Location.objects.create(tenant=tenant, name="B", parent=a)
        a.parent = b
        a.save()
        path = a.full_path
        assert path.count(">") <= 10

    def test_get_descendant_ids_cycle_terminates(self, tenant):
        """Regression for D-08: must terminate in < 1s."""
        import time
        a = Location.objects.create(tenant=tenant, name="A")
        b = Location.objects.create(tenant=tenant, name="B", parent=a)
        a.parent = b
        a.save()
        t0 = time.time()
        ids = a.get_descendant_ids()
        assert time.time() - t0 < 1.0
        assert isinstance(ids, list)

    def test_children_count_property(self, tenant, company, region):
        assert company.children_count == 1
```

### 5.5 `test_forms.py`

```python
from datetime import date
from decimal import Decimal

import pytest

from multi_location.forms import (
    LocationForm, LocationPricingRuleForm,
    LocationTransferRuleForm, LocationSafetyStockRuleForm,
)
from multi_location.models import Location


@pytest.mark.django_db
class TestLocationForm:
    def test_rejects_cross_tenant_parent(self, tenant, other_tenant):
        foreign = Location.objects.create(tenant=other_tenant, name="Foreign")
        f = LocationForm(
            data={"name": "X", "location_type": "retail_store",
                  "parent": foreign.pk, "warehouse": "",
                  "is_active": "on"},
            tenant=tenant,
        )
        assert not f.is_valid()
        assert "parent" in f.errors

    def test_excludes_self_and_descendants_on_edit(self, tenant, company, region, dc):
        f = LocationForm(
            instance=company,
            data={"name": "HQ", "location_type": "company",
                  "parent": dc.pk, "warehouse": "",
                  "is_active": "on"},
            tenant=tenant,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestPricingRuleForm:
    def test_product_xor_category(self, tenant, store, product, category):
        f = LocationPricingRuleForm(
            data={"location": store.pk, "product": product.pk,
                  "category": category.pk, "rule_type": "markup_pct",
                  "value": "10", "priority": 1, "is_active": "on",
                  "effective_from": "", "effective_to": "", "notes": ""},
            tenant=tenant,
        )
        assert not f.is_valid()

    @pytest.mark.parametrize("rule_type,value", [
        ("override_price", "-10"),   # D-06
        ("markup_pct", "9999"),      # D-07
        ("markdown_pct", "150"),     # > 100% markdown nonsensical
    ])
    def test_value_bounds(self, tenant, store, rule_type, value):
        """Regression for D-05/D-06/D-07."""
        f = LocationPricingRuleForm(
            data={"location": store.pk, "product": "", "category": "",
                  "rule_type": rule_type, "value": value,
                  "priority": 1, "is_active": "on",
                  "effective_from": "", "effective_to": "", "notes": ""},
            tenant=tenant,
        )
        assert not f.is_valid()

    def test_effective_from_after_to_rejected(self, tenant, store):
        f = LocationPricingRuleForm(
            data={"location": store.pk, "product": "", "category": "",
                  "rule_type": "markup_pct", "value": "5",
                  "priority": 1, "is_active": "on",
                  "effective_from": "2026-12-31", "effective_to": "2026-01-01",
                  "notes": ""},
            tenant=tenant,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestTransferRuleForm:
    def test_source_equals_destination_rejected(self, tenant, dc):
        f = LocationTransferRuleForm(
            data={"source_location": dc.pk, "destination_location": dc.pk,
                  "allowed": "on", "max_transfer_qty": 100, "lead_time_days": 1,
                  "requires_approval": "", "priority": 1,
                  "is_active": "on", "notes": ""},
            tenant=tenant,
        )
        assert not f.is_valid()

    def test_duplicate_pair_rejected_friendly(self, tenant, dc, store):
        """Regression for D-11: unique_together trap — form must catch."""
        from multi_location.models import LocationTransferRule
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc, destination_location=store, allowed=True,
        )
        f = LocationTransferRuleForm(
            data={"source_location": dc.pk, "destination_location": store.pk,
                  "allowed": "on", "max_transfer_qty": 0, "lead_time_days": 0,
                  "requires_approval": "", "priority": 1,
                  "is_active": "on", "notes": ""},
            tenant=tenant,
        )
        assert not f.is_valid()
        assert any("already" in str(e).lower() for e in f.errors.values())


@pytest.mark.django_db
class TestSafetyStockRuleForm:
    def test_bounds_enforced(self, tenant, store, product):
        """Regression for D-04: safety ≤ reorder ≤ max."""
        f = LocationSafetyStockRuleForm(
            data={"location": store.pk, "product": product.pk,
                  "safety_stock_qty": 100, "reorder_point": 10, "max_stock_qty": 5,
                  "notes": ""},
            tenant=tenant,
        )
        assert not f.is_valid()
```

### 5.6 `test_views_location.py` (integration)

```python
import pytest
from django.urls import reverse

from multi_location.models import Location


@pytest.mark.django_db
class TestLocationViews:
    def test_list_200_for_admin(self, client_logged_in):
        r = client_logged_in.get(reverse("multi_location:location_list"))
        assert r.status_code == 200

    @pytest.mark.parametrize("param,value", [
        ("parent", "abc"), ("parent", "9" * 25),
        ("parent", "1' OR '1'='1"), ("parent", "../etc/passwd"),
    ])
    def test_non_numeric_filter_does_not_500(self, client_logged_in, param, value):
        """Regression for D-01."""
        r = client_logged_in.get(f"/multi-location/?{param}={value}")
        assert r.status_code == 200

    def test_pagination_preserves_filters(self, client_logged_in, tenant):
        """Regression for D-10."""
        for i in range(25):
            Location.objects.create(tenant=tenant, name=f"L{i}", city="Seattle")
        r = client_logged_in.get("/multi-location/?q=Seattle")
        assert b"q=Seattle" in r.content, "pagination links drop the q parameter"

    def test_detail_cross_tenant_404(self, client_logged_in, other_tenant):
        foreign = Location.objects.create(tenant=other_tenant, name="Foreign")
        r = client_logged_in.get(reverse("multi_location:location_detail", args=[foreign.pk]))
        assert r.status_code == 404

    def test_delete_requires_post(self, client_logged_in, tenant):
        loc = Location.objects.create(tenant=tenant, name="X")
        r = client_logged_in.get(reverse("multi_location:location_delete", args=[loc.pk]))
        assert r.status_code == 302  # redirect, no delete
        assert Location.objects.filter(pk=loc.pk).exists()

    def test_delete_cascades_rules(self, client_logged_in, tenant, dc, product):
        from multi_location.models import LocationPricingRule, LocationSafetyStockRule
        LocationPricingRule.objects.create(
            tenant=tenant, location=dc, product=product, rule_type="markup_pct", value=10,
        )
        LocationSafetyStockRule.objects.create(
            tenant=tenant, location=dc, product=product, safety_stock_qty=1, reorder_point=2,
        )
        client_logged_in.post(reverse("multi_location:location_delete", args=[dc.pk]))
        assert not LocationPricingRule.objects.filter(location_id=dc.pk).exists()
        assert not LocationSafetyStockRule.objects.filter(location_id=dc.pk).exists()
```

### 5.7 `test_security.py`

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestCSRF:
    def test_delete_without_csrf_token_rejected(self, admin_user, client, tenant):
        from multi_location.models import Location
        client.force_login(admin_user)
        loc = Location.objects.create(tenant=tenant, name="X")
        client.handler.enforce_csrf_checks = True
        r = client.post(reverse("multi_location:location_delete", args=[loc.pk]))
        assert r.status_code == 403


@pytest.mark.django_db
class TestXSSAutoescape:
    def test_location_name_script_tag_escaped(self, client_logged_in, tenant):
        from multi_location.models import Location
        Location.objects.create(tenant=tenant, name="<script>alert(1)</script>")
        r = client_logged_in.get(reverse("multi_location:location_list"))
        assert b"<script>alert(1)</script>" not in r.content
        assert b"&lt;script&gt;" in r.content


@pytest.mark.django_db
class TestIDOR:
    @pytest.mark.parametrize("route,factory_kw", [
        ("multi_location:location_detail", {}),
        ("multi_location:location_edit", {}),
        ("multi_location:pricing_rule_detail", {"pricing": True}),
        ("multi_location:transfer_rule_detail", {"transfer": True}),
        ("multi_location:safety_stock_rule_detail", {"safety": True}),
    ])
    def test_other_tenant_pk_returns_404(self, client_logged_in, other_tenant, product, route, factory_kw):
        from multi_location.models import (
            Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
        )
        other_loc = Location.objects.create(tenant=other_tenant, name="Foreign")
        if factory_kw.get("pricing"):
            obj = LocationPricingRule.objects.create(
                tenant=other_tenant, location=other_loc, rule_type="markup_pct", value=10,
            )
        elif factory_kw.get("transfer"):
            other2 = Location.objects.create(tenant=other_tenant, name="F2")
            obj = LocationTransferRule.objects.create(
                tenant=other_tenant, source_location=other_loc, destination_location=other2,
            )
        elif factory_kw.get("safety"):
            # Must share a product — create one in the other tenant
            from catalog.models import Category, Product
            c = Category.objects.create(tenant=other_tenant, name="C")
            p = Product.objects.create(tenant=other_tenant, sku="X", name="X", category=c,
                                       purchase_cost=1, retail_price=1, status="active")
            obj = LocationSafetyStockRule.objects.create(
                tenant=other_tenant, location=other_loc, product=p,
            )
        else:
            obj = other_loc
        r = client_logged_in.get(reverse(route, args=[obj.pk]))
        assert r.status_code == 404


@pytest.mark.django_db
class TestSuperuserTenantNone:
    def test_list_empty_no_500(self, client):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        su = User.objects.create_user("su", password="x", tenant=None, is_superuser=True)
        client.force_login(su)
        assert client.get(reverse("multi_location:location_list")).status_code == 200
        assert client.get(reverse("multi_location:stock_visibility")).status_code == 200
```

### 5.8 `test_performance.py`

```python
import pytest

from multi_location.models import Location


@pytest.mark.django_db
class TestPerformance:
    def test_descendant_traversal_bounded(self, django_assert_max_num_queries, tenant):
        """100-node tree — should finish in ≤ 5 queries, not 100."""
        root = Location.objects.create(tenant=tenant, name="root")
        prev = [root]
        for depth in range(4):
            new = []
            for parent in prev:
                for j in range(3):
                    child = Location.objects.create(
                        tenant=tenant, name=f"d{depth}-{parent.pk}-{j}", parent=parent,
                    )
                    new.append(child)
            prev = new
        with django_assert_max_num_queries(5):
            root.get_descendant_ids(include_self=True)

    def test_location_list_n_plus_1(self, client_logged_in, django_assert_max_num_queries, tenant):
        for i in range(20):
            Location.objects.create(tenant=tenant, name=f"L{i}")
        with django_assert_max_num_queries(10):
            client_logged_in.get("/multi-location/")

    def test_stock_visibility_n_plus_1(self, client_logged_in, django_assert_max_num_queries, tenant):
        with django_assert_max_num_queries(15):
            client_logged_in.get("/multi-location/stock-visibility/")
```

### 5.9 `test_seed.py`

```python
import pytest
from django.core.management import call_command
from io import StringIO

from multi_location.models import Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule


@pytest.mark.django_db
class TestSeed:
    def test_seed_creates_hierarchy(self, tenant, warehouse, product, category):
        from warehousing.models import Warehouse
        Warehouse.objects.create(tenant=tenant, code="WH-02", name="2nd", is_active=True)
        out = StringIO()
        call_command("seed_multi_location", stdout=out)
        assert Location.objects.filter(tenant=tenant).count() >= 7
        assert LocationTransferRule.objects.filter(tenant=tenant).count() >= 4

    def test_seed_idempotent_without_flush(self, tenant, warehouse, product, category):
        from warehousing.models import Warehouse
        Warehouse.objects.create(tenant=tenant, code="WH-02", name="2nd", is_active=True)
        call_command("seed_multi_location")
        before = Location.objects.count()
        call_command("seed_multi_location")
        assert Location.objects.count() == before
```

### 5.10 How to run

```
cd c:\xampp\htdocs\NavIMS
venv\Scripts\python -m pytest multi_location/tests -q
```

Add the new testpath:

```
# pytest.ini
testpaths = … multi_location/tests
```

---

## 6. Defects, Risks & Recommendations

All High/Critical defects below were **verified** against the current branch.

| ID | Sev | Location | Finding | OWASP | Recommendation |
|---|---|---|---|---|---|
| D-01 | **Critical** | [multi_location/views.py:48](multi_location/views.py#L48), [:256](multi_location/views.py#L256), [:360-364](multi_location/views.py#L360-L364), [:465-469](multi_location/views.py#L465-L469), [:168](multi_location/views.py#L168) | Non-numeric GET filter params (`?parent=abc`, `?location=abc`, `?source=abc`, `?destination=abc`, `?product=abc`) propagate straight into `.filter(…_id=value)` and trigger unhandled `ValueError` → HTTP 500. Reproduced for all 5 list views. | A03 / A05 | Coerce with `int(value)` inside a `try/except`, or use a `forms.IntegerField().clean(value)` gate; fall back to an empty-filter response. |
| D-02 | **High** | [multi_location/models.py:94-108](multi_location/models.py#L94-L108) | `_generate_code` sorts by `-id` and only parses a leading `LOC-` prefix. Any later insert whose code does not start with `LOC-` (e.g. imported `STORE-01`) resets the numbering to `LOC-00001`, which then collides with an existing row and raises `IntegrityError`. Reproduced. | A04 | Compute `max(code)` over rows matching `r"LOC-\d+"` (or keep a tenant-scoped `SequenceCounter` table). |
| D-03 | **High** | [multi_location/forms.py:43-54](multi_location/forms.py#L43-L54) | When `tenant=None` is passed (superuser path), the form does **not** scope `parent` / `warehouse` querysets, so a cross-tenant pk validates as a "valid choice". Save ultimately fails on the null-tenant insert, but the access-control boundary is leaky. | A01 | Always require a tenant and 403 / error out the view for `request.tenant is None`, or default all querysets to `.none()` when `tenant is None`. |
| D-04 | **High** | [multi_location/forms.py:174-202](multi_location/forms.py#L174-L202) | `LocationSafetyStockRuleForm` accepts `safety_stock_qty > reorder_point` or `max_stock_qty < reorder_point`, producing rules that can never trigger a reorder. Reproduced (ss=100, rop=10, max=5 → valid). | A04 | Add `clean()` enforcing `safety_stock_qty ≤ reorder_point ≤ max_stock_qty` (when `max_stock_qty > 0`). |
| D-05 | **High** | [multi_location/forms.py:69-116](multi_location/forms.py#L69-L116) | `effective_from > effective_to` is accepted, allowing a rule that is permanently inactive or contradicts its own window. | A04 | Add `clean()` check `if from and to and from > to: raise`. |
| D-06 | **High** | [multi_location/forms.py:69-116](multi_location/forms.py#L69-L116) | `rule_type='override_price'` accepts negative values (reproduced `-999.99 → valid`). A negative retail price downstream would break pricing rollups. | A04 | In `clean()`, when `rule_type in ('override_price', 'fixed_adjustment')` ensure `value >= 0` (override must also be > 0). |
| D-07 | **Medium** | [multi_location/forms.py:69-116](multi_location/forms.py#L69-L116) | `markup_pct` / `markdown_pct` unbounded. `9999.99 %` accepted. | A04 | Constrain percentage rule types to `0 ≤ value ≤ 1000` (or a business-defined cap). |
| D-08 | **High** | [multi_location/models.py:78-87](multi_location/models.py#L78-L87) | `get_descendant_ids` has no visited-set guard. If a parent cycle exists (admin / raw SQL), the function loops indefinitely and exhausts RAM. Cycle was reproduced via direct `.save`. | A04 / DoS | Track a `visited = set()`; break early. Also add `clean()` or `pre_save` signal that walks the parent chain and raises on cycle. |
| D-09 | **Medium** | [multi_location/models.py:67-76](multi_location/models.py#L67-L76) | `full_path` caps at 10 hops but does **not** detect cycles — output like `A > B > A > B > A > B > A > B > A > B > A`. User-facing confusion plus evidence of the deeper D-08 cycle. | A04 | Use visited-set; return `"<cycle detected: A↺B>"` when a node repeats. |
| D-10 | **High** | [templates/multi_location/location_list.html:99-107](templates/multi_location/location_list.html#L99-L107), [pricing_rule_list.html:99-107](templates/multi_location/pricing_rule_list.html#L99-L107), [transfer_rule_list.html:101-109](templates/multi_location/transfer_rule_list.html#L101-L109), [safety_stock_rule_list.html](templates/multi_location/safety_stock_rule_list.html) | Pagination `href`s are bare `?page=N`, dropping every active filter (`q`, `type`, `parent`, `active`, `location`, `rule_type`, `source`, `destination`, `allowed`, `product`). Breaks CLAUDE.md §Filter Implementation Rules. Only `stock_visibility.html` threads filters through correctly. | — | Thread filters into each pagination link (same pattern as [templates/multi_location/stock_visibility.html:93-100](templates/multi_location/stock_visibility.html#L93-L100)), or build a `query_params_without_page` helper and append. |
| D-11 | **High** | [multi_location/forms.py:123-167](multi_location/forms.py#L123-L167), [multi_location/forms.py:174-202](multi_location/forms.py#L174-L202) | `TransferRule` has `unique_together=(tenant, source, destination)` and `SafetyStockRule` has `unique_together=(tenant, location, product)`, but `tenant` is not a form field → Django's default `validate_unique` excludes the check, so duplicates escape to DB and surface as HTTP 500. Same class of bug as lesson #6 in [.claude/tasks/lessons.md](.claude/tasks/lessons.md). | A04 | In each form's `clean()` add a tenant-scoped existence check before save (template from lesson #6). |
| D-12 | **Medium** | [multi_location/views.py](multi_location/views.py) (all mutating views) | No `core.AuditLog` entries are emitted on create / edit / delete of Location, PricingRule, TransferRule, or SafetyStockRule. Destructive actions cannot be traced per-tenant. | A09 | Wrap each `form.save()` / `obj.delete()` in an `AuditLog.objects.create(...)` call with `action`, `model_name`, `object_id`, and changed fields. |
| D-13 | **Medium** | [multi_location/views.py](multi_location/views.py) (all views) | Only `@login_required`; no permission / role check. A tenant user with any role can create, edit, or delete all locations and rules. | A01 / A07 | Add a `@permission_required('multi_location.manage_locations')` decorator (or the project's existing `core.decorators` pattern) for create/edit/delete endpoints; reserve read-only for plain login. |
| D-14 | **Medium** | [multi_location/models.py:171-205](multi_location/models.py#L171-L205) | `LocationTransferRule.max_transfer_qty`, `lead_time_days`, `requires_approval` and `is_active` are stored but no downstream caller consumes them (no API, no UI enforcement, no warehouse-transfer integration). Design gap: rules are informational only. | — | Either wire the rule into a future transfer-order workflow or annotate the models/templates as "advisory only" to set user expectations. |
| D-15 | **Medium** | [multi_location/views.py:189-201](multi_location/views.py#L189-L201) | `stock_visibility_view` calls `.aggregate` four separate times plus `.count()` plus pagination `.count()` — five to six scan queries where a single `annotate + aggregate` (or a selectable queryset.values) would suffice. On a tenant with 50k stock levels, each load runs full-table scans. | — | Collapse into a single `.aggregate(on_hand=Sum(..), allocated=Sum(..), value=Sum(..), low=Count(Case(..)))`. |
| D-16 | **Low** | [multi_location/views.py:169-177](multi_location/views.py#L169-L177) | `stock_visibility_view` filter catches only `Location.DoesNotExist`, not `ValueError`. This is what D-01 exposes for this view; noted separately to ensure the fix is tailored (should be "coerce + try/except ValueError + silently ignore" to match the existing UX). | A03 | Combine int-coercion try/except with the existing `DoesNotExist` branch. |
| D-17 | **Low** | [multi_location/models.py:32](multi_location/models.py#L32) | `code` has `max_length=20` but the generator emits up to `LOC-100000` once `LOC-99999` is reached (see D-02 reproduction). That still fits (10 chars), but the code also allows arbitrary 20-char codes with no uniqueness-friendly validation. | — | Add `validators=[RegexValidator(r'^[A-Z0-9\-]+$')]` or constrain length of `LOC-` prefix in the generator. |
| D-18 | **Info** | [multi_location/management/commands/seed_multi_location.py:192-208](multi_location/management/commands/seed_multi_location.py#L192-L208) | Seed uses `random.choice` for safety-stock / reorder values without a fixed seed → non-deterministic demo data. Minor but harms test reproducibility if this fixture is reused in automation. | — | Use `random.Random(42).choice(...)` or fixed values. |

### 6.1 Residual risks (not defects, but surface to monitor)

| ID | Risk | Mitigation |
|---|---|---|
| R-1 | Long Location FK dropdowns in list-view filters (no pagination) on a 10k-location tenant. | Switch to a typeahead (Select2/htmx) for the `location` filter. |
| R-2 | `location.pricing_rules.all()[:10]` on detail page has no `tenant=` guard. Harmless today because the `save()` path always sets tenant, but a direct shell insert could create a mismatched rule and it would surface on the wrong tenant's detail page. | Filter the related queryset by `tenant=request.tenant`. |
| R-3 | Silent ignore of an unknown `?rule_type=foo`, `?type=foo`, `?allowed=foo` rather than returning a validation error. | Validate GET against choices; render a user-facing message. |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets

| File | Line | Branch | Mutation (mutmut) |
|---|---|---|---|
| [multi_location/models.py](multi_location/models.py) | ≥ 95 % | ≥ 90 % | ≥ 70 % |
| [multi_location/forms.py](multi_location/forms.py) | ≥ 95 % | ≥ 90 % | ≥ 75 % |
| [multi_location/views.py](multi_location/views.py) | ≥ 85 % | ≥ 75 % | ≥ 60 % |
| Templates (filter-retention assertions) | n/a | n/a | qualitative |

### 7.2 KPI table

| KPI | Green | Amber | Red | Target |
|---|---|---|---|---|
| Functional pass rate | 100 % | ≥ 95 % | < 95 % | Release gate |
| Open Critical defects | 0 | — | ≥ 1 | Release gate |
| Open High defects | 0 | 1-2 | ≥ 3 | Release gate |
| Suite runtime (local) | < 30 s | < 60 s | ≥ 60 s | Non-blocking |
| p95 list-view latency @ 10k rows | < 300 ms | < 800 ms | ≥ 800 ms | Post-fix |
| Queries per `stock_visibility_view` | ≤ 10 | ≤ 20 | > 20 | Post-D-15 fix |
| N+1 on `get_descendant_ids` (100 nodes) | ≤ 5 | ≤ 15 | > 15 | Post-fix |
| Regression-escape rate (new Highs vs prior release) | 0 | 1 | ≥ 2 | Non-blocking |

### 7.3 Release Exit Gate

Release must block until **all** of the following are true:

- [ ] D-01 fixed across all 5 list views + regression test TC-SEC-001 green
- [ ] D-02 fixed and regression test TC-LOC-002 green
- [ ] D-08 fixed and regression test TC-LOC-003 green (< 1 s)
- [ ] D-04, D-05, D-06, D-07 fixed with form-level `clean()` guards
- [ ] D-10 fixed — pagination links preserve filters on all 5 list pages
- [ ] D-11 fixed — unique-together caught with friendly form error (no 500)
- [ ] D-13 — RBAC decorator applied to create/edit/delete endpoints (or product sign-off that plain login is intended)
- [ ] `pytest multi_location/tests -q` green with ≥ 85 % line coverage
- [ ] `bandit -r multi_location` clean of Medium/High
- [ ] Manual smoke of full golden path with `seed_multi_location` data

---

## 8. Summary

The Multi-Location Management module ships a complete CRUD surface for 4 entities plus a global stock-visibility roll-up, correctly scoped by tenant at the view layer, with proper template auto-escaping and appropriate use of `get_object_or_404` for IDOR defence. Form-level business-rule enforcement is, however, **significantly under-invested**: safety-stock ordering, pricing-rule value bounds, effective-date ranges, unique-together duplicates, and parent-cycle detection are all missing.

**18 defects captured** (1 Critical, 7 High, 7 Medium, 2 Low, 1 Info), of which **all 8 Critical/High items were verified** via Django shell reproductions against `config.settings_test`. The module also repeats a known pattern already captured as lesson #6 ([`.claude/tasks/lessons.md`](.claude/tasks/lessons.md)) — `unique_together` without `tenant` in form fields, which bypasses `validate_unique` and surfaces as 500. The pagination-retention regression (D-10) is the same class of bug flagged in `CLAUDE.md`'s Filter Implementation Rules.

**Top-3 priorities:**

1. **D-01** — five crash-on-bad-filter endpoints. Trivial fix (coerce + try/except) blocks drive-by scans and untrained user fat-fingers alike.
2. **D-02 + D-08** — data-integrity / availability: the location code generator can hard-fail on insert, and the hierarchy walker can hang the server on a cycle. Both are reachable via admin UI in normal operation.
3. **D-04 / D-05 / D-06 / D-07 / D-11** — business-rule gaps. Each is a 5-line `clean()` addition that converts silent data corruption into an actionable form error.

Once D-01, D-02, D-04–D-08, D-10, D-11 are remediated and the suite in §5 is wired in, the module will meet release-gate criteria.
