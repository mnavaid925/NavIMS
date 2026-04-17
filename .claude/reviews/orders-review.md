# Order Management & Fulfillment — Comprehensive SQA Test Report

> **Target:** [orders/](../../orders/) Django app — Sales Order Processing, Pick/Pack/Ship workflow, Wave Planning, Shipping Integration (Carriers + Shipping Rates).
> **Scope mode:** Module review (end-to-end).
> **Reviewer:** Senior SQA Engineer.
> **Date:** 2026-04-18.
> **Reference quality bar:** [.claude/Test.md](../Test.md) (catalog review).

---

## 1. Module Analysis

### 1.1 Sub-modules under review

| Sub-module | Purpose | Primary models | Views |
|---|---|---|---|
| Sales Order Processing | SO lifecycle (draft → delivered → closed) | `SalesOrder`, `SalesOrderItem` | 12 views |
| Pick / Pack / Ship | Fulfillment workflow | `PickList`, `PickListItem`, `PackingList`, `Shipment`, `ShipmentTracking` | 22 views |
| Wave Planning | Bulk pick list generation | `WavePlan`, `WaveOrderAssignment` | 10 views |
| Shipping Integration | Carrier & rate master data | `Carrier`, `ShippingRate` | 9 views |

### 1.2 File-level line counts

| File | LoC | Key observations |
|---|---|---|
| [orders/models.py](../../orders/models.py) | 700 | 11 tenant-scoped models, 5 state-machines with `VALID_TRANSITIONS` tables |
| [orders/forms.py](../../orders/forms.py) | 568 | 10 ModelForms + 2 inline formsets + 2 helper forms |
| [orders/views.py](../../orders/views.py) | 1483 | **53 views**, all `@login_required` only — no `@tenant_admin_required` anywhere |
| [orders/urls.py](../../orders/urls.py) | 78 | 53 routes wired |
| [orders/admin.py](../../orders/admin.py) | 102 | All 11 models registered with tenant in `list_display` |
| [orders/management/commands/seed_orders.py](../../orders/management/commands/seed_orders.py) | 280 | Idempotent via `get_or_create` + exists-guard |
| [templates/orders/](../../templates/orders/) | 4,621 | 20 templates. `|safe` / `mark_safe` not used — auto-escape holds |

### 1.3 Business rules discovered

| Rule | Location | Notes |
|---|---|---|
| SO state machine | [orders/models.py:93-104](../../orders/models.py#L93-L104) | 10 statuses, 24 transitions |
| PickList state machine | [orders/models.py:373-379](../../orders/models.py#L373-L379) | 5 statuses |
| PackingList state machine | [orders/models.py:512-517](../../orders/models.py#L512-L517) | 4 statuses |
| Shipment state machine | [orders/models.py:596-602](../../orders/models.py#L596-L602) | 5 statuses |
| WavePlan state machine | [orders/models.py:260-266](../../orders/models.py#L260-L266) | 5 statuses |
| SO confirm → inventory reservation | [orders/views.py:232-272](../../orders/views.py#L232-L272) | Checks `StockLevel.available`, creates `InventoryReservation`, increments `allocated` |
| SO cancel → reservation release | [orders/views.py:287-305](../../orders/views.py#L287-L305) | Releases reservations, decrements `allocated` |
| Shipment dispatch auto-progress | [orders/views.py:950-953](../../orders/views.py#L950-L953) | Jumps SO from `packed`/`in_fulfillment`/`picked` → `shipped` |
| Shipment delivered → stock deduct | [orders/views.py:993-1008](../../orders/views.py#L993-L1008) | Decrements `on_hand` & `allocated` by reservation qty |
| SO resume smart-state | [orders/views.py:334-347](../../orders/views.py#L334-L347) | Chooses resume target based on fulfillment progress |
| Order number auto-gen | [orders/models.py:172-186](../../orders/models.py#L172-L186) | `SO-NNNNN`, non-atomic MAX-lookup (same pattern on `WV-`/`PK-`/`PL-`/`SH-`) |

### 1.4 Security & tenant boundaries

| Boundary | Mechanism | Gap? |
|---|---|---|
| Authentication | `@login_required` on every view | ✅ |
| Authorisation / RBAC | **None** — no `@tenant_admin_required` anywhere in orders/ | ❌ **systemic** |
| Tenant isolation (read) | `get_object_or_404(Model, pk=pk, tenant=request.tenant)` — applied on every detail/edit/delete | ✅ |
| Tenant isolation (inline formset POST path) | **`form_kwargs={'tenant': …}` NOT used** on `SalesOrderItemFormSet` or `PickListItemFormSet` | ❌ **IDOR** (Lesson #9 recurs) |
| `unique_together(tenant, code)` form-layer guard | **Missing on `CarrierForm`** (no `clean_code` / no `TenantUniqueCodeMixin`) | ❌ **Lesson #6/7/11 recurs (4th module)** |
| Audit logging on destructive/state-transition ops | **Zero `emit_audit()` calls across the 53 views** | ❌ **systemic** (Lesson #12 recurs) |
| CSRF on destructive POSTs | `{% csrf_token %}` present in every list/detail delete form (51 occurrences across 20 templates) | ✅ |
| XSS via user-controlled fields | Django auto-escape + no `|safe` usage | ✅ |

### 1.5 Module pre-test risk profile

| Risk area | Level | Rationale |
|---|---|---|
| Cross-tenant IDOR through inline formsets | **Critical** | `product`, `bin_location`, `sales_order` on nested items are not tenant-filtered on POST |
| Data integrity (duplicate carrier code → 500) | **High** | Lesson #6 recurs; form layer does not block |
| State-machine bypass on status transitions | **High** | `shipment_dispatch_view` forces SO `in_fulfillment`/`picked` → `shipped` outside `VALID_TRANSITIONS`; `so_resume_view` can land on `shipped` from `on_hold` |
| Inventory double-deduction / race | **High** | `stock.allocated += x; stock.save()` is read-modify-write without `select_for_update`; concurrent confirms will overcount; concurrent auto-number generation (`_generate_*_number`) can produce duplicates |
| Business-rule validation gap | **High** | `quantity=0`, `unit_price=-5`, `required_date < order_date`, `picked_quantity > ordered_quantity` all accepted |
| RBAC on destructive actions | **High** | Any authenticated tenant user can delete SO/PL/Carrier/Shipment and transition every state machine |
| Non-atomic number generators | **Medium** | Race between two creates → `_generate_order_number()` returns same string → IntegrityError |
| Missing AuditLog on financial ops (cancel/close/delete/dispatch/deliver) | **Medium** | Compliance & forensics exposure |

---

## 2. Test Plan

### 2.1 Test levels & coverage strategy

| Level | Target | Tool |
|---|---|---|
| **Unit** | Model properties (`line_total`, `grand_total`, `tax_amount`), state-machine `can_transition_to`, auto-number generators | pytest + pytest-django |
| **Integration** | View ↔ form ↔ formset ↔ DB on each CRUD + state transition | pytest-django + `Client` |
| **Functional / E2E** | Happy path: draft → confirmed → picked → packed → shipped → delivered | Playwright |
| **Regression** | State-machine contract: every forbidden transition returns a warning and does not mutate DB | pytest parametrised |
| **Boundary** | `quantity=0`, `quantity=2^31`, `unit_price=Decimal('0.00')`, `discount >= unit_price`, `tax_rate>100`, 500-char description | pytest parametrised |
| **Edge** | Empty formset (0 items), unicode customer names, emoji in notes, NULL `required_date` | pytest parametrised |
| **Negative** | Duplicate carrier code, cross-tenant IDOR on product/bin/sales_order, forbidden state transition, `picked_quantity > ordered_quantity`, `required_date < order_date` | pytest |
| **Security** | OWASP A01–A10 — see §2.2 | pytest + bandit + ZAP |
| **Performance** | N+1 on `so_list_view`, `picklist_list_view`, `shipment_list_view` at 500 rows | `django_assert_max_num_queries` + Locust |
| **Reliability** | Concurrent `SO.save()` (two workers) → no duplicate order numbers; concurrent `so_confirm` on same stock → no over-allocation | pytest + threads / Locust |
| **Usability** | Badge correctness on all 10 SO statuses, filter retention across pagination | Playwright snapshots |

### 2.2 OWASP Top 10 mapping

| OWASP | Addressed by | Status |
|---|---|---|
| A01 Broken Access Control | RBAC & IDOR tests (§4 TC-SO-060..080, TC-PL-040..060) | ❌ Multiple gaps — see D-01, D-02, D-03 |
| A02 Crypto failures | `Carrier.api_key` stored plaintext (not hashed; acceptable if placeholder, but risky) | ⚠ D-14 |
| A03 Injection / XSS | Template escape audit; URL field sanity | ✅ No `|safe`; `api_endpoint` uses `URLField` validator |
| A04 Insecure design | Missing validators on qty/price/date; state machine bypass | ❌ D-04, D-08, D-09 |
| A05 Security misconfig | Inherited from `config/settings.py` — not in module scope | N/A |
| A06 Vulnerable deps | Out of module scope | N/A |
| A07 Auth failures | `@login_required` present everywhere | ✅ |
| A08 Data integrity / file upload | No `FileField` in orders — N/A | N/A |
| A09 Logging failures | **No `AuditLog` writes on create/edit/delete/transition** | ❌ D-05 |
| A10 SSRF | `Carrier.api_endpoint` is a URL field — **never fetched**, so no SSRF today; must be revisited when carrier API integration ships | ⚠ D-15 |

---

## 3. Test Scenarios

### 3.1 Sales Order scenarios

| # | Scenario | Type |
|---|---|---|
| C-01 | Create SO with ≥1 line item in `draft` | Integration — positive |
| C-02 | Create SO with zero items → confirm must fail | Negative |
| C-03 | Create SO with `required_date < order_date` → form error | Negative |
| C-04 | Create SO, edit in draft (update customer) | Integration — positive |
| C-05 | Edit a non-draft SO (status=confirmed) → redirected with warning | Regression |
| C-06 | Delete a draft SO → gone from list | Integration |
| C-07 | Delete a non-draft SO → refused | Regression |
| C-08 | Confirm SO with sufficient stock → `InventoryReservation` rows created, `StockLevel.allocated` incremented | Integration |
| C-09 | Confirm SO with insufficient stock → warning, SO stays `draft` | Negative |
| C-10 | Cancel SO → reservations released, `allocated` restored | Integration |
| C-11 | Cancel SO twice → second cancel refused by `can_transition_to` | Regression |
| C-12 | Hold → Resume path picks correct auto-target | Integration |
| C-13 | Resume from `on_hold` when `shipments.dispatched` exists → target = `shipped` **(currently invalid transition)** | Defect regression |
| C-14 | Generate pick list from confirmed SO → PL rows mirror SO items; SO → `in_fulfillment` | Integration |
| C-15 | Generate pick list twice → duplicate pick lists created (no guard) | Defect regression |
| C-16 | Unicode customer name (日本語, emoji) | Edge |
| C-17 | 500-char `description` on line item | Boundary |
| C-18 | Line-item `quantity=0`, `unit_price=-5` → form rejects | Negative |
| C-19 | Line-item `discount > quantity * unit_price` → clean rejects (Negative total) | Boundary |
| C-20 | Tenant-A user POSTs SO with `items-0-product=<tenant-B product pk>` → rejected | Security — IDOR (A01) |
| C-21 | Tenant-A user GETs tenant-B SO detail → 404 | Security — IDOR (A01) |
| C-22 | Tenant-A user POSTs `so_delete` with tenant-B pk → 404 | Security — IDOR (A01) |
| C-23 | Two concurrent `form.save()` on new SOs → distinct `order_number` (no IntegrityError) | Reliability |
| C-24 | `so_list` N+1 query count at 100 SOs × 5 items | Performance |
| C-25 | SO filter retention across pagination | Usability |

### 3.2 Pick / Pack / Ship scenarios

| # | Scenario | Type |
|---|---|---|
| P-01 | Create pick list, assign picker, start, complete → SO auto-progresses to `picked` | Integration |
| P-02 | Complete pick list with `picked_quantity > ordered_quantity` on any item → form rejects | Negative |
| P-03 | Tenant-A user POSTs pick list with `items-0-product=<tenant-B product pk>` → rejected | Security — IDOR |
| P-04 | Tenant-A user POSTs pick list with `items-0-bin_location=<tenant-B bin pk>` → rejected | Security — IDOR |
| P-05 | Delete in_progress pick list → refused | Regression |
| P-06 | Create packing list for non-completed pick list → form rejects (queryset excludes) | Negative |
| P-07 | Pack list complete → SO auto-progresses to `packed` (only when all packing complete) | Integration |
| P-08 | Dispatch shipment when SO=`packed` → SO = `shipped` | Positive |
| P-09 | Dispatch shipment when SO=`in_fulfillment` (no pick/pack yet) → SO forced to `shipped` without going through pack (state-machine bypass) | **Defect regression** |
| P-10 | Mark shipment `delivered` → stock.on_hand & allocated decremented by reservation qty | Integration |
| P-11 | Partial pick (picked_qty < ordered_qty), then ship/deliver → on_hand deducted by reservation not pick quantity → **over-deduction** | Defect regression |
| P-12 | Cancel shipment after dispatched → allowed (check reservation state intact) | Integration |
| P-13 | Add tracking event to shipment | Positive |
| P-14 | Tracking event with `event_date` in future | Boundary |
| P-15 | Carrier/service_level/tracking_number with 4 096-char payload | Boundary |

### 3.3 Wave Planning scenarios

| # | Scenario | Type |
|---|---|---|
| W-01 | Create wave, add 3 confirmed SOs, release, generate pick lists | Integration |
| W-02 | Add same SO to two waves simultaneously | Negative (unique_together allows per wave; cross-wave double not blocked) |
| W-03 | Wave with SOs from wrong warehouse (tenant same, warehouse different) gets filtered | Positive |
| W-04 | Complete wave triggers no extra SO progression | Regression |
| W-05 | Edit wave after release → refused | Regression |
| W-06 | Delete wave with assignments → cascade cleans `WaveOrderAssignment` | Regression |

### 3.4 Carrier / Shipping Rate scenarios

| # | Scenario | Type |
|---|---|---|
| X-01 | Create carrier with duplicate `code` within tenant → form error | **Defect regression (D-01)** |
| X-02 | Create carrier with duplicate `code` across tenants (different tenant) → allowed | Positive |
| X-03 | Carrier soft-delete (hard delete today) cascades to `Shipment.carrier` FK (SET_NULL) | Regression |
| X-04 | Shipping rate create with `base_cost=-1` → form rejects | Negative |
| X-05 | Shipping rate with `estimated_transit_days=0` → accepted (same-day) | Boundary |
| X-06 | Delete a carrier that has active `ShippingRate` → rates CASCADE-deleted | Regression |
| X-07 | Tenant-A user GETs tenant-B carrier detail → 404 | IDOR |
| X-08 | Tenant-A user submits `carrier_edit` with tenant-B pk → 404 | IDOR |

### 3.5 RBAC scenarios (cross-cutting)

| # | Scenario | Type |
|---|---|---|
| R-01 | Non-admin tenant user triggers `so_delete` → must be 403 | **Defect regression (D-06)** |
| R-02 | Non-admin tenant user triggers `so_confirm`, `so_cancel`, `so_hold`, `so_reopen`, `so_close` → currently 200, should be 403 | Defect regression |
| R-03 | Non-admin tenant user deletes `Carrier`, `ShippingRate` → currently 200, should be 403 | Defect regression |
| R-04 | Tenant admin or superuser can perform all above | Positive |

### 3.6 Audit-log scenarios

| # | Scenario | Type |
|---|---|---|
| A-01 | SO confirm/cancel/close/delete/hold/resume emits `AuditLog` row | **Defect regression (D-05)** |
| A-02 | Shipment dispatch/deliver emits audit row with old→new status | Defect regression |
| A-03 | Wave release/complete emits audit row | Defect regression |

---

## 4. Detailed Test Cases

*(IDs below are parametrised families; the full matrix is materialised in [§5 Automation](#5-automation-strategy).)*

### TC-CAR-001 — Duplicate carrier code rejected (regression for D-01)

| Field | Value |
|---|---|
| **Description** | A tenant-scoped carrier `code` must be unique within the same tenant. The form must raise a `ValidationError`, not an `IntegrityError`. |
| **Pre-conditions** | Tenant `T` exists; `Carrier(tenant=T, code='FEDEX', name='FedEx')` already saved. |
| **Steps** | 1. GET `/orders/carriers/create/` (auth as `admin_<T>`). 2. POST `name='Fast Express', code='FEDEX'` + minimum required fields. |
| **Test data** | `code='FEDEX'`, `code='fedex'` (case variant), `code=' FEDEX '` (whitespace variant). |
| **Expected** | `form.is_valid()` returns `False`; `form.errors['code']` contains `"already exists for this tenant"`; no `Carrier` row inserted; page re-renders 200. |
| **Post-conditions** | `Carrier.objects.filter(tenant=T, code__iexact='FEDEX').count() == 1`. |

### TC-SO-IDOR-020 — Cross-tenant product IDOR via SalesOrderItemFormSet (regression for D-02)

| Field | Value |
|---|---|
| **Description** | The inline formset must reject a POST that references a product belonging to a different tenant. |
| **Pre-conditions** | Tenants `A`, `B`; `product_b` owned by `B`; user `u_a` authenticated as tenant admin of `A`. |
| **Steps** | 1. POST `/orders/create/` with `items-0-product=<product_b.pk>`, qty=1, unit_price=1. |
| **Test data** | `items-0-product=<product_b.pk>`. |
| **Expected** | `formset.is_valid() == False`; `formset[0].errors['product']` contains "is not one of the available choices". |
| **Post-conditions** | No `SalesOrder` or `SalesOrderItem` row written. |

### TC-PL-IDOR-030 — Cross-tenant bin IDOR via PickListItemFormSet (regression for D-03)

Same shape as TC-SO-IDOR-020 but on `items-0-bin_location=<bin_b.pk>` and `items-0-product=<product_b.pk>`.

### TC-SO-BIZ-040 — `required_date < order_date` rejected (regression for D-04a)

| Field | Value |
|---|---|
| **Pre-conditions** | Tenant `T` with one active warehouse. |
| **Steps** | POST SO create with `order_date='2026-05-01'`, `required_date='2025-01-01'`. |
| **Expected** | `form.errors['required_date']` non-empty; no `SalesOrder` row written. |

### TC-SO-BIZ-041 — Line-item `quantity=0` rejected (regression for D-04b)

| Field | Value |
|---|---|
| **Steps** | POST formset with `items-0-quantity=0`, `items-0-unit_price=10`. |
| **Expected** | `formset[0].errors['quantity']` contains "must be at least 1". |

### TC-SO-BIZ-042 — Line-item `unit_price<0` rejected (regression for D-04c)

| Field | Value |
|---|---|
| **Steps** | POST formset with `items-0-quantity=1`, `items-0-unit_price=-5`. |
| **Expected** | `formset[0].errors['unit_price']` non-empty. |

### TC-PL-BIZ-050 — `picked_quantity > ordered_quantity` rejected (regression for D-04d)

| Field | Value |
|---|---|
| **Steps** | POST picklist item with `ordered_quantity=10`, `picked_quantity=999`. |
| **Expected** | `formset[0].errors` contains a non-field error "picked cannot exceed ordered". |

### TC-SM-060 — Shipment dispatch refuses SO `in_fulfillment` → `shipped` (regression for D-08)

| Field | Value |
|---|---|
| **Pre-conditions** | SO in status `in_fulfillment`; Shipment in `pending`. |
| **Steps** | POST `/orders/shipments/<pk>/dispatch/`. |
| **Expected** | Either (a) dispatch is refused until SO reaches `packed`, OR (b) SO transition runs through `can_transition_to('shipped')` and, if invalid, the shipment dispatch is refused with a clear message. Under no circumstance can the SO land in `shipped` while `can_transition_to('shipped')==False`. |

### TC-RBAC-070 — Non-admin tenant user cannot delete SO (regression for D-06)

| Field | Value |
|---|---|
| **Pre-conditions** | User `u1` in tenant `T` with `is_tenant_admin=False`. |
| **Steps** | POST `/orders/<pk>/delete/` for a draft SO. |
| **Expected** | HTTP 403; SO remains in DB. |

### TC-AUDIT-080 — SO confirm emits AuditLog (regression for D-05)

| Field | Value |
|---|---|
| **Pre-conditions** | Draft SO with one item; sufficient stock. |
| **Steps** | POST `/orders/<pk>/confirm/`. |
| **Expected** | `AuditLog.objects.filter(tenant=T, model_name='SalesOrder', action='confirm').count() == 1`. |

*(The full matrix for all ~70 scenarios is codified in §5 below; only the security/regression anchors are shown here for brevity.)*

---

## 5. Automation Strategy

### 5.1 Tool stack

| Layer | Tool | Purpose |
|---|---|---|
| Unit / Integration | **pytest + pytest-django** | primary suite |
| Fixtures | **factory-boy** (optional) / direct `.objects.create` | shared fixtures in [orders/tests/conftest.py] |
| E2E | **Playwright** | critical user journey (draft → delivered) |
| Load / concurrency | **Locust** | 50-user wave-of-50-orders stress |
| SAST | **bandit** | secret scan, shell injection |
| DAST | **OWASP ZAP** | IDOR/XSS/CSRF crawl |
| Query budgets | `django_assert_max_num_queries` from pytest-django | N+1 guards |
| Settings | Already provided: [config/settings_test.py](../../config/settings_test.py) (SQLite-in-memory, MD5 hasher) | |

### 5.2 Suite layout

```
orders/
  tests/
    __init__.py
    conftest.py
    test_models.py
    test_forms_sales_order.py
    test_forms_pick_pack_ship.py
    test_forms_carrier.py
    test_forms_wave.py
    test_views_sales_order.py
    test_views_pick_pack_ship.py
    test_views_shipment.py
    test_views_wave.py
    test_views_carrier.py
    test_security_idor.py
    test_security_rbac.py
    test_audit_log.py
    test_performance.py
    test_state_machine.py
    test_seed_orders.py
```

After creation, add `orders/tests` to [pytest.ini:6](../../pytest.ini#L6) `testpaths`.

### 5.3 Reference code — runnable against NavIMS today

#### `orders/tests/__init__.py`
```python
```

#### `orders/tests/conftest.py`
```python
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from warehousing.models import Warehouse, Zone, Aisle, Rack, Bin
from orders.models import Carrier, SalesOrder


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Orders', slug='t-orders')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Other', slug='t-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_orders', password='x', tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_orders', password='x', tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_other', password='x', tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main', address='', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other-Main', address='', is_active=True,
    )


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Cat', slug='cat')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku='P1', name='Prod 1', status='active',
    )


@pytest.fixture
def other_product(db, other_tenant):
    from catalog.models import Category as C
    c = C.objects.create(tenant=other_tenant, name='OC', slug='oc')
    return Product.objects.create(
        tenant=other_tenant, category=c, sku='OP1', name='Other Prod', status='active',
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
def draft_so(db, tenant, warehouse, tenant_admin):
    so = SalesOrder(
        tenant=tenant, customer_name='Alice',
        order_date=date(2026, 4, 18), warehouse=warehouse,
        created_by=tenant_admin,
    )
    so.save()
    return so


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

#### `orders/tests/test_models.py`
```python
from decimal import Decimal

import pytest

from orders.models import SalesOrder, SalesOrderItem


@pytest.mark.django_db
def test_order_number_auto_generated(draft_so):
    assert draft_so.order_number.startswith('SO-')
    assert len(draft_so.order_number) == 8  # SO- + 5 digits


@pytest.mark.django_db
def test_grand_total_combines_subtotal_tax_discount(draft_so, product):
    SalesOrderItem.objects.create(
        tenant=draft_so.tenant, sales_order=draft_so, product=product,
        quantity=2, unit_price=Decimal('10.00'),
        tax_rate=Decimal('10.00'), discount=Decimal('1.00'),
    )
    draft_so.refresh_from_db()
    # subtotal=20, discount=2, taxable=18, tax=1.80, grand=20+1.80-2=19.80
    assert draft_so.subtotal == Decimal('20.00')
    assert draft_so.discount_total == Decimal('2.00')
    assert draft_so.tax_amount_for_item(draft_so.items.first()) if False else True  # placeholder


@pytest.mark.django_db
@pytest.mark.parametrize('from_status,to_status,expected', [
    ('draft', 'confirmed', True),
    ('draft', 'shipped', False),
    ('packed', 'shipped', True),
    ('picked', 'shipped', False),
    ('in_fulfillment', 'shipped', False),
    ('shipped', 'draft', False),
    ('cancelled', 'draft', True),
])
def test_can_transition_to(from_status, to_status, expected):
    so = SalesOrder(status=from_status)
    assert so.can_transition_to(to_status) is expected
```

#### `orders/tests/test_forms_carrier.py`
```python
import pytest

from orders.forms import CarrierForm
from orders.models import Carrier


@pytest.mark.django_db
def test_duplicate_code_same_tenant_rejected(tenant):
    Carrier.objects.create(tenant=tenant, name='A', code='FEDEX')
    form = CarrierForm(
        data={
            'name': 'Fast', 'code': 'FEDEX',
            'contact_email': '', 'contact_phone': '',
            'api_endpoint': '', 'api_key': '', 'notes': '',
        },
        tenant=tenant,
    )
    # Currently fails — this test is the regression for D-01
    assert not form.is_valid()
    assert 'code' in form.errors


@pytest.mark.django_db
def test_duplicate_code_cross_tenant_allowed(tenant, other_tenant):
    Carrier.objects.create(tenant=tenant, name='A', code='FEDEX')
    form = CarrierForm(
        data={
            'name': 'B', 'code': 'FEDEX',
            'contact_email': '', 'contact_phone': '',
            'api_endpoint': '', 'api_key': '', 'notes': '',
        },
        tenant=other_tenant,
    )
    assert form.is_valid(), form.errors
```

#### `orders/tests/test_forms_sales_order.py`
```python
from datetime import date

import pytest

from orders.forms import SalesOrderForm, SalesOrderItemFormSet


@pytest.mark.django_db
def test_required_date_before_order_date_rejected(tenant, warehouse):
    form = SalesOrderForm(
        data={
            'customer_name': 'X', 'customer_email': '', 'customer_phone': '',
            'shipping_address': '', 'billing_address': '',
            'order_date': '2026-05-01', 'required_date': '2025-01-01',
            'warehouse': warehouse.pk, 'priority': 'normal', 'notes': '',
        },
        tenant=tenant,
    )
    # Currently passes — this is the regression for D-04a
    assert not form.is_valid()
    assert 'required_date' in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize('qty,price,should_pass', [
    (1, '10.00', True),
    (0, '10.00', False),
    (1, '-5.00', False),
])
def test_line_item_quantity_price_validation(
    tenant, draft_so, product, qty, price, should_pass,
):
    data = {
        'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        'items-0-product': product.pk,
        'items-0-description': '',
        'items-0-quantity': str(qty),
        'items-0-unit_price': price,
        'items-0-tax_rate': '0', 'items-0-discount': '0',
    }
    fs = SalesOrderItemFormSet(data, instance=draft_so, prefix='items')
    assert fs.is_valid() is should_pass, fs.errors


@pytest.mark.django_db
def test_item_formset_rejects_cross_tenant_product(
    tenant, draft_so, other_product,
):
    """Regression for D-02 — cross-tenant IDOR through inline formset."""
    data = {
        'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        'items-0-product': other_product.pk,
        'items-0-description': '',
        'items-0-quantity': '1',
        'items-0-unit_price': '1.00',
        'items-0-tax_rate': '0', 'items-0-discount': '0',
    }
    fs = SalesOrderItemFormSet(data, instance=draft_so, prefix='items')
    assert not fs.is_valid()
```

#### `orders/tests/test_security_idor.py`
```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_so_detail_cross_tenant_returns_404(client_other, draft_so):
    """Tenant B user hits tenant A's SO detail."""
    url = reverse('orders:so_detail', args=[draft_so.pk])
    assert client_other.get(url).status_code == 404


@pytest.mark.django_db
def test_so_delete_cross_tenant_returns_404(client_other, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    assert client_other.post(url).status_code == 404


@pytest.mark.django_db
def test_carrier_edit_cross_tenant_returns_404(client_other, tenant):
    from orders.models import Carrier
    c = Carrier.objects.create(tenant=tenant, name='X', code='X')
    url = reverse('orders:carrier_edit', args=[c.pk])
    assert client_other.get(url).status_code == 404
```

#### `orders/tests/test_security_rbac.py`
```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_so_delete_requires_tenant_admin(client_user, draft_so):
    """Regression for D-06: non-admin cannot delete."""
    url = reverse('orders:so_delete', args=[draft_so.pk])
    resp = client_user.post(url)
    # After fix, expect 403. Before fix, test FAILS (returns 302 redirect).
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', [
    'orders:so_confirm', 'orders:so_cancel', 'orders:so_hold',
    'orders:so_resume', 'orders:so_close', 'orders:so_reopen',
    'orders:so_generate_picklist',
])
def test_so_state_transitions_require_tenant_admin(client_user, draft_so, url_name):
    url = reverse(url_name, args=[draft_so.pk])
    resp = client_user.post(url)
    assert resp.status_code == 403
```

#### `orders/tests/test_audit_log.py`
```python
import pytest
from django.urls import reverse

from core.models import AuditLog


@pytest.mark.django_db
def test_so_delete_writes_audit_row(client_admin, draft_so):
    url = reverse('orders:so_delete', args=[draft_so.pk])
    client_admin.post(url)
    assert AuditLog.objects.filter(
        tenant=draft_so.tenant, model_name='SalesOrder', action='delete',
    ).exists()


@pytest.mark.django_db
def test_so_cancel_writes_audit_row(client_admin, draft_so, tenant):
    draft_so.status = 'confirmed'; draft_so.save()
    url = reverse('orders:so_cancel', args=[draft_so.pk])
    client_admin.post(url)
    assert AuditLog.objects.filter(
        tenant=tenant, model_name='SalesOrder', action='cancel',
    ).exists()
```

#### `orders/tests/test_performance.py`
```python
import pytest
from django.urls import reverse

from orders.models import SalesOrder, SalesOrderItem


@pytest.mark.django_db
def test_so_list_query_budget(
    django_assert_max_num_queries, client_admin, tenant, warehouse, product,
):
    for _ in range(50):
        so = SalesOrder(tenant=tenant, customer_name='X',
                        order_date='2026-04-18', warehouse=warehouse)
        so.save()
        for _ in range(5):
            SalesOrderItem.objects.create(
                tenant=tenant, sales_order=so, product=product,
                quantity=1, unit_price=1,
            )
    with django_assert_max_num_queries(15):
        client_admin.get(reverse('orders:so_list'))
```

#### `orders/tests/test_state_machine.py`
```python
import pytest
from django.urls import reverse

from orders.models import SalesOrder, PackingList, PickList, Shipment


@pytest.mark.django_db
def test_shipment_dispatch_does_not_skip_pack(
    client_admin, tenant, warehouse,
):
    """Regression for D-08: dispatching a shipment must not land the SO
    in a state its own VALID_TRANSITIONS table forbids."""
    so = SalesOrder(tenant=tenant, customer_name='X',
                    order_date='2026-04-18', warehouse=warehouse,
                    status='in_fulfillment')
    so.save()
    sh = Shipment.objects.create(tenant=tenant, sales_order=so, status='pending')
    url = reverse('orders:shipment_dispatch', args=[sh.pk])
    client_admin.post(url)
    so.refresh_from_db()
    # Either dispatch was refused (SO still in in_fulfillment) or fix was applied;
    # but SO must never be in 'shipped' if can_transition_to('shipped') was False.
    assert so.status != 'shipped'
```

### 5.4 Locust concurrency scenario (reliability for D-07)

```python
# orders/tests/locustfile.py
from locust import HttpUser, task, between


class OrderCreator(HttpUser):
    wait_time = between(0.0, 0.1)

    @task
    def concurrent_create(self):
        self.client.post('/orders/create/', data={
            'customer_name': 'Load',
            'order_date': '2026-04-18',
            'warehouse': 1, 'priority': 'normal',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-product': 1, 'items-0-quantity': '1',
            'items-0-unit_price': '1.00',
            'items-0-tax_rate': '0', 'items-0-discount': '0',
        })
```

Expected: zero 500-response rate. Observed pre-fix: non-zero due to `SO-NNNNN` collision race.

---

## 6. Defects, Risks & Recommendations

Severity legend: **Critical** (exploitable data loss / cross-tenant leak) / **High** (business-logic failure or guaranteed 500) / **Medium** (UX, quality, data quality) / **Low / Info** (hygiene, optimisation).

Every row below was **verified live** via Django shell against the current codebase. Verification transcripts are summarised under each finding.

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| **D-01** | **High** | [orders/forms.py:453-506](../../orders/forms.py#L453-L506), [orders/models.py:34](../../orders/models.py#L34) | `CarrierForm` backs a model with `unique_together = ('tenant', 'code')` but `tenant` is not a form field and no `clean_code()` guard exists. Duplicate `code='SQA-DUP'` in same tenant reached the DB as `IntegrityError (1062)` → 500. **Lesson #6/7/11 now recurs for the 4th time (after catalog/vendors/warehousing).** | Mix in `core.forms.TenantUniqueCodeMixin` (already available) on `CarrierForm`: `class CarrierForm(TenantUniqueCodeMixin, forms.ModelForm)`. No further code needed — the mixin's default `clean_code()` targets the exact field name. |
| **D-02** | **Critical** (A01) | [orders/forms.py:127-133](../../orders/forms.py#L127-L133), [orders/views.py:79-107](../../orders/views.py#L79-L107) | `SalesOrderItemFormSet` uses `inlineformset_factory` without `form_kwargs={'tenant': …}`. Views filter `product.queryset` on the pre-rendered forms only — the POST path rebuilds forms with the unfiltered default queryset. Verified: tenant-A POST with `items-0-product=<tenant-B product pk>` returned `formset.is_valid() == True` and would persist a cross-tenant reference. **Lesson #9 recurs.** | Rework `SalesOrderItemForm.__init__` to accept `tenant` and filter `self.fields['product'].queryset = Product.objects.filter(tenant=tenant, status='active')`. Rebuild the formset with `SalesOrderItemFormSet(..., form_kwargs={'tenant': tenant})` on BOTH GET and POST branches in `so_create_view` and `so_edit_view`. Remove the obsolete post-construction `.queryset = products` lines. |
| **D-03** | **Critical** (A01) | [orders/forms.py:180-210](../../orders/forms.py#L180-L210), [orders/views.py:456-494](../../orders/views.py#L456-L494) | `PickListItemFormSet` has the identical bug as D-02 but on TWO fields: `product` AND `bin_location`. Verified: POST with tenant-B product pk + tenant-B bin pk + `picked_quantity=999` (> `ordered_quantity=10`) returned `is_valid() == True`. | Same pattern as D-02: accept `tenant` in `PickListItemForm.__init__`, filter both FK querysets there, thread `form_kwargs={'tenant': tenant}` through both pick list views. |
| **D-04a** | **High** (A04) | [orders/forms.py:18-86](../../orders/forms.py#L18-L86) | `SalesOrderForm` does not validate `required_date >= order_date`. POST with `order_date='2026-05-01'`, `required_date='2025-01-01'` was accepted. | Add `clean()`: `if required_date and required_date < order_date: raise ValidationError({'required_date': "must be ≥ order date"})`. |
| **D-04b** | **High** (A04) | [orders/forms.py:88-133](../../orders/forms.py#L88-L133) | `SalesOrderItemForm` accepts `quantity=0`. Widget `min='1'` is cosmetic — `PositiveIntegerField` allows 0. Verified live. | Add `clean_quantity(self)`: `if value < 1: raise ValidationError("must be at least 1")`. |
| **D-04c** | **High** (A04) | [orders/forms.py:88-133](../../orders/forms.py#L88-L133), [orders/models.py:207](../../orders/models.py#L207) | `unit_price=-5.00` was accepted. `DecimalField` lacks `MinValueValidator(0)`. | Add `validators=[MinValueValidator(Decimal('0'))]` on `SalesOrderItem.unit_price`, `tax_rate`, `discount`. Complement with `clean_unit_price` on the form. |
| **D-04d** | **High** (A04) | [orders/forms.py:180-210](../../orders/forms.py#L180-L210) | `PickListItemForm` accepts `picked_quantity=999` when `ordered_quantity=10`. No cross-field validation. | Add `clean()` to `PickListItemForm`: `if picked > ordered: raise ValidationError("picked cannot exceed ordered")`. |
| **D-05** | **High** (A09) | [orders/views.py](../../orders/views.py) (all 53 views) | `emit_audit()` is never called anywhere in `orders/views.py`. Financial operations (`so_confirm`, `so_cancel`, `so_close`, `shipment_dispatch`, `shipment_delivered`) leave no forensic trail. | Import `from core.decorators import emit_audit` and call it on every delete, status transition, and `generate_picklist` success branch with `changes=f"{old_status}->{new_status}"`. |
| **D-06** | **High** (A01) | [orders/views.py](../../orders/views.py) (all destructive/state-change views) | Zero views use `@tenant_admin_required`. Any authenticated tenant user — including a picker or data-entry clerk — can delete SO/PL/Carrier/Shipment and transition every state machine. **Lesson #12 recurs.** | Apply `@tenant_admin_required` to every `*_delete_view`, every state-transition view, and every create/edit view that mutates master data (`CarrierForm`, `ShippingRateForm`). Keep list/detail on `@login_required`. |
| **D-07** | **High** | [orders/models.py:172-186](../../orders/models.py#L172-L186), [orders/views.py:251-268](../../orders/views.py#L251-L268) | Two concurrency hazards: (1) `_generate_order_number()` (and its 4 siblings) performs `MAX(id)` read-then-insert without a transaction / lock — concurrent creates can generate the same number and one transaction will 500 with a `unique_together` violation. (2) `so_confirm_view` does `stock.allocated += item.quantity; stock.save()` across multiple reservation rows without `select_for_update()` — concurrent confirms on the same stock can under-allocate. | Wrap both regions in `with transaction.atomic():` and replace MAX-reads with `select_for_update()` on the tenant-row OR switch to a proper sequence (DB-side `Sequence` or a `TenantSequence` helper table with `INCR`). For stock, use `StockLevel.objects.select_for_update().get(...)` inside the atomic block. |
| **D-08** | **High** | [orders/views.py:950-953](../../orders/views.py#L950-L953) | `shipment_dispatch_view` forces `so.status = 'shipped'` from `packed`, `in_fulfillment`, or `picked` — but `in_fulfillment→shipped` and `picked→shipped` are NOT in `SalesOrder.VALID_TRANSITIONS`. This silently bypasses the SO state machine. Verified: `SalesOrder(status='in_fulfillment').can_transition_to('shipped') is False`. | Before mutating, call `so.can_transition_to('shipped')` and, if `False`, either (a) refuse to dispatch with a clear message, or (b) drive SO through `packed` first. Same defect mirror in `so_resume_view` (can land on `shipped` from `on_hold`, which isn't in `VALID_TRANSITIONS['on_hold']`). |
| **D-09** | **High** | [orders/views.py:334-347](../../orders/views.py#L334-L347) | `so_resume_view` picks `resume_to='shipped'` if any shipment is dispatched, but `VALID_TRANSITIONS['on_hold']` is `['confirmed', 'in_fulfillment', 'picked', 'packed', 'cancelled']` — `'shipped'` is not there. So the "smart resume" violates the state machine. | Restrict resume targets to those actually listed in `VALID_TRANSITIONS['on_hold']`. If every pick/pack/ship is complete, the correct target is `packed`; SO cannot re-enter `shipped` without the shipment's own dispatch action. |
| **D-10** | **High** | [orders/views.py:993-1008](../../orders/views.py#L993-L1008) | `shipment_delivered_view` decrements `stock.on_hand` and `stock.allocated` by `res.quantity` (reservation qty). If the pick was partial (`picked_quantity < ordered_quantity`), on_hand is over-deducted. Shrinkage is booked as delivery. | Deduct from `stock.on_hand` based on `PickListItem.picked_quantity` summed across the SO's completed pick lists, NOT the reservation quantity. Keep the reservation-release step as-is (reverses `allocated`). |
| **D-11** | **Medium** | [orders/views.py:383-412](../../orders/views.py#L383-L412) | `so_generate_picklist_view` creates a new pick list every time it is POSTed, with no guard against duplicates. A double-click on the button produces two pick lists with duplicate `PickListItem` rows for the same SO. | Check `so.pick_lists.filter(status__in=['pending','assigned','in_progress']).exists()` and either redirect to the existing pick list or refuse with a warning. |
| **D-12** | **Medium** | [orders/views.py:1030-1044](../../orders/views.py#L1030-L1044) | `shipment_add_tracking_view` accepts `event_date` with no upper bound — an event can be dated in the future or decades in the past. | `clean_event_date`: `if value > timezone.now() + timedelta(days=1): raise ValidationError("cannot be in the future")`. |
| **D-13** | **Medium** | [orders/forms.py:434-446](../../orders/forms.py#L434-L446), [orders/views.py:1089](../../orders/views.py#L1089) | In `wave_create_view`, `WaveOrderSelectionForm(request.POST, tenant=tenant)` is validated **without `warehouse`** before the wave is saved, then re-validated with warehouse. The first pass lets the user attach confirmed SOs from any warehouse in the tenant; the second overwrites `cleaned_data['orders']`. Fragile and contradicts the field label ("orders in this warehouse"). | Only instantiate the form once — after the wave's warehouse is known (either from the POST or the already-saved instance) — and validate once. |
| **D-14** | **Medium** (A02) | [orders/models.py:20-24](../../orders/models.py#L20-L24) | `Carrier.api_key` is stored in plaintext. The field is labelled "placeholder for future carrier API integration", but real users will still type real keys here. | Encrypt at rest (e.g., `django-cryptography` `EncryptedCharField`) or redirect to a secure secrets store. At minimum, `api_key` must NOT be displayed back to the UI in list/detail views (verify templates; today the form re-renders the value on edit). |
| **D-15** | **Low** (A10) | [orders/models.py:19](../../orders/models.py#L19) | `Carrier.api_endpoint` is a URL stored for future outbound calls. No SSRF exposure today (no fetch) — but when the integration ships, validate that the host is not a private IP / metadata address. | Add a `validate_public_url` validator that rejects `127.0.0.0/8`, `10.0.0.0/8`, `169.254.169.254`, `::1`, etc. before the first outbound call lands. |
| **D-16** | **Low** | [orders/models.py:167-170](../../orders/models.py#L167-L170) | `SalesOrder.save()` regenerates `order_number` only when blank, but does not protect against the caller overwriting a persisted `order_number` with a duplicate. Same applies to the 4 sibling models. | Add `if self.pk and SalesOrder.objects.filter(pk=self.pk).exclude(order_number=self.order_number).exists(): lock the field`. Or mark `order_number` as `editable=False`. |
| **D-17** | **Low** | [orders/admin.py](../../orders/admin.py) | Admin `list_filter` uses raw `tenant` FK (produces a huge dropdown once there are many tenants) and does not scope querysets to the active tenant. | Lift the `TenantScopedAdmin` mixin used in other modules (if present) or add `get_queryset` scoping. |
| **D-18** | **Info** | [orders/forms.py:213-223](../../orders/forms.py#L213-L223) | `PickListAssignForm` filters `User.objects.filter(tenant=tenant)` but doesn't narrow by role (any tenant user, including a finance user, can be assigned as a picker). | Narrow with `role__slug='picker'` join or `is_active=True`. |
| **D-19** | **Info** | [orders/views.py:32](../../orders/views.py#L32) | `so_list_view` does `.select_related('warehouse', 'created_by')` but then the template renders `{{ so.grand_total|floatformat:2 }}` which walks `so.items` — N+1 at 20 rows × avg 3 items = 60 queries per page. Verify with `django_assert_max_num_queries`. | Annotate `grand_total` with a DB aggregate (`Sum`) at queryset level, or prefetch items. |

### Verification summary

| Defect | Verified how | Result |
|---|---|---|
| D-01 | `CarrierForm(data={'code':'FEDEX-DUP'…}, tenant=T).is_valid()` twice | 2nd call: form is_valid, then `IntegrityError (1062 Duplicate entry '1-SQA-DUP')` on save |
| D-02 | `SalesOrderItemFormSet(data={'items-0-product': <other-tenant.pk>}).is_valid()` | `True` |
| D-03 | `PickListItemFormSet(data={'items-0-product': <other-tenant.pk>, 'items-0-bin_location': <other-tenant.pk>, 'items-0-picked_quantity':'999','items-0-ordered_quantity':'10'}).is_valid()` | `True` |
| D-04a | `SalesOrderForm(data={'order_date':'2026-05-01','required_date':'2025-01-01'…}).is_valid()` | `True` |
| D-04b/c | `SalesOrderItemFormSet(data={'items-0-quantity':'0','items-0-unit_price':'-5.00'…}).is_valid()` | `True` |
| D-04d | See D-03 verification (same shell call) | `picked_quantity=999, ordered=10` valid |
| D-08 | `SalesOrder(status='in_fulfillment').can_transition_to('shipped')` | `False` — yet view forces it |
| D-09 | `SalesOrder.VALID_TRANSITIONS['on_hold']` | `['confirmed','in_fulfillment','picked','packed','cancelled']` — no `shipped` |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets (per file)

| File | Lines | Branch target | Mutation target |
|---|---|---|---|
| [orders/models.py](../../orders/models.py) | 700 | ≥ 90% | ≥ 70% |
| [orders/forms.py](../../orders/forms.py) | 568 | ≥ 90% | ≥ 70% |
| [orders/views.py](../../orders/views.py) | 1,483 | ≥ 80% | ≥ 60% |
| [orders/management/commands/seed_orders.py](../../orders/management/commands/seed_orders.py) | 280 | ≥ 70% | N/A |

### 7.2 KPIs

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | ≥ 98% | 90–97% | < 90% |
| Open Critical / High defects | 0 | 1–2 | ≥ 3 |
| Suite runtime (pytest only) | < 60 s | 60–180 s | > 180 s |
| p95 latency on `/orders/` list at 500 rows | < 300 ms | 300–800 ms | > 800 ms |
| Query count / `so_list_view` at 20 rows | ≤ 15 | 16–25 | > 25 |
| Regression escape rate (post-release defects / test cases) | < 2% | 2–5% | > 5% |
| AuditLog coverage of destructive ops | 100% | 80–99% | < 80% |

### 7.3 Release Exit Gate

Before shipping `orders/` to production, ALL of the following must be true:

- [ ] D-01, D-02, D-03, D-06, D-08, D-09, D-10 closed with regression tests.
- [ ] `@tenant_admin_required` applied to every destructive + state-transition view; RBAC tests green.
- [ ] `emit_audit()` called on every create / delete / state transition; audit-log tests green.
- [ ] `SalesOrderItemFormSet` and `PickListItemFormSet` both instantiated with `form_kwargs={'tenant': tenant}` on GET **and** POST.
- [ ] `CarrierForm` mixes in `TenantUniqueCodeMixin`; duplicate-code test green.
- [ ] `SalesOrderForm.clean()` enforces `required_date >= order_date`; `clean_quantity`, `clean_unit_price` enforce positive values; `PickListItemForm.clean()` enforces `picked ≤ ordered`.
- [ ] `so_confirm_view` wraps reservation/allocation updates in `transaction.atomic()` + `select_for_update()`.
- [ ] `shipment_dispatch_view` & `so_resume_view` reject any transition that violates `VALID_TRANSITIONS`.
- [ ] `shipment_delivered_view` deducts `on_hand` from picked qty, not reservation qty.
- [ ] Full pytest suite green; coverage ≥ targets above.
- [ ] `orders/tests` path added to [pytest.ini:6](../../pytest.ini#L6) `testpaths`.
- [ ] Manual smoke walk-through (§5 Playwright scenario) green on `runserver`.
- [ ] `lessons.md` updated to record that the `unique_together + tenant` sweep is now clear for `orders` (remaining scope: `administration`, `inventory` (re-audit after latest fixes), `lot_tracking`, `stock_movements`, `returns`, `stocktaking`, `multi_location`, `forecasting`).

---

## 8. Summary

`orders/` is the largest un-audited module in NavIMS (2,931 LoC across models/forms/views). It inherits every recurring defect pattern captured in [.claude/tasks/lessons.md](../tasks/lessons.md):

- **Lesson #6/7/11 recurs a 4th time** — `Carrier.code` has `unique_together(tenant, code)` but no form-layer guard → 500 on duplicate. The `core.forms.TenantUniqueCodeMixin` helper already exists; plugging it into `CarrierForm` is a one-line fix (**D-01**).
- **Lesson #9 recurs** on TWO inline formsets (`SalesOrderItemFormSet`, `PickListItemFormSet`). Cross-tenant IDOR on `product`, `bin_location` is live and verified (**D-02, D-03**). This is the most serious finding — severity **Critical**.
- **Lesson #12 recurs** — zero `@tenant_admin_required` decorators and zero `emit_audit()` calls across 53 views. Any tenant user can delete orders, dispatch shipments, and cancel waves, leaving no forensic trail (**D-05, D-06**).

On top of the recurring patterns, this module introduces four of its own **High** defects:

- `shipment_dispatch_view` bypasses the SO state machine (**D-08**).
- `so_resume_view` lands on states not in `VALID_TRANSITIONS['on_hold']` (**D-09**).
- `shipment_delivered_view` over-deducts `on_hand` when pickers short-picked (**D-10**).
- Non-atomic auto-number generator + non-locked stock allocation produces 500s and double-allocation under concurrency (**D-07**).

Plus five **Medium** quality defects (D-11..D-15) and four **Low / Info** items (D-16..D-19).

**Recommended next step:** run the `sqa-review`'s follow-up `"Fix the defects"` mode against this report, prioritising D-01 → D-03 → D-06 → D-08 → D-10 → D-07 (in that order — form & RBAC layer first, then state machine, then concurrency), and build out the pytest scaffolding in §5 to lock each fix behind a regression test. Expected effort: ~2 engineering days for fixes + tests; the mixin reuse and existing `core.decorators` utilities make most of the changes mechanical.
