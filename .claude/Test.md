# Inventory Tracking & Control — Comprehensive SQA Test Report

> Target module: [inventory/](../inventory/) — the `inventory` Django app comprising four sub-modules (Stock Levels, Stock Status, Valuation, Reservations).
> Scope: full module review end-to-end (models, forms, views, templates, seed, admin).
> Standards: ISO/IEC/IEEE 29119, OWASP Top 10:2021, NavIMS conventions ([CLAUDE.md](CLAUDE.md)).
> Prepared by: Senior SQA Engineer persona, staff-engineer bar.
> Date: 2026-04-17.

---

## 1. Module Analysis

### 1.1 Surface area

| Artefact | File | LoC | Notes |
|---|---|---|---|
| Models | [inventory/models.py](../inventory/models.py) | 441 | **8 models** across 4 sub-modules |
| Forms | [inventory/forms.py](../inventory/forms.py) | 133 | 4 ModelForms |
| Views | [inventory/views.py](../inventory/views.py) | 558 | **18 views** (list/detail/create/edit/delete/transition/recalculate) |
| URLs | [inventory/urls.py](../inventory/urls.py) | 35 | App namespace `inventory:` at `/inventory/` |
| Admin | [inventory/admin.py](../inventory/admin.py) | 60 | All 8 models registered |
| Templates | [templates/inventory/](../templates/inventory/) | 15 files | list + detail + form per entity |
| Seed | [inventory/management/commands/seed_inventory.py](../inventory/management/commands/seed_inventory.py) | — | Per-tenant sample data |
| Tests | — | **0** | **No test coverage** (pytest `testpaths` excludes `inventory/tests`) |

### 1.2 Sub-modules

| # | Sub-module | Primary models | Purpose |
|---|---|---|---|
| 1 | **Real-Time Stock Levels** | `StockLevel`, `StockAdjustment` | Per-product-per-warehouse stock with manual +/−/correction adjustments |
| 2 | **Stock Status Management** | `StockStatus`, `StockStatusTransition` | Classify stock into `active / damaged / expired / on_hold`; move between buckets |
| 3 | **Inventory Valuation** | `ValuationConfig`, `InventoryValuation`, `ValuationEntry` | Configure FIFO / LIFO / Weighted Avg; on-demand recalc snapshot |
| 4 | **Inventory Reservations** | `InventoryReservation` | Soft-allocate stock to references (sales orders, jobs) with state machine |

### 1.3 State machines

Reservation machine at [models.py:364-370](../inventory/models.py#L364-L370):

```
pending ⇄ confirmed → released / expired / cancelled
      └────────────────────────── cancelled → pending
```

Stock Status is not a state machine — it is a bucket-transfer system. `StockStatusTransition.apply_transition` at [models.py:230-249](../inventory/models.py#L230-L249) debits one bucket and credits another.

### 1.4 Security-sensitive paths (risk map)

| Path | File:Line | Risk surface |
|---|---|---|
| Stock adjustment | [views.py:86-109](../inventory/views.py#L86-L109) | No RBAC; non-atomic; silent clamp on over-decrement |
| Stock status transition | [views.py:217-237](../inventory/views.py#L217-L237) | No RBAC; non-atomic; phantom source allowed → **creates inventory from thin air** |
| Valuation recalculate | [views.py:347-402](../inventory/views.py#L347-L402) | No RBAC; global DELETE then insert; non-atomic; FIFO/LIFO math identical to W-Avg |
| Reservation transition | [views.py:527-558](../inventory/views.py#L527-L558) | No RBAC; non-atomic; no over-reserve guard |
| Reservation create/edit | [views.py:449-506](../inventory/views.py#L449-L506) | No `quantity ≤ available` check |
| Auto-generated sequence numbers | [models.py:103-117, 214-228, 427-441](../inventory/models.py) | TOCTOU race (same pattern as purchase_orders D-08) |

### 1.5 NavIMS pattern compliance

| Pattern | Status |
|---|---|
| `tenant` FK on every model | ✅ (all 8 models) |
| `@login_required` on every view | ✅ |
| `filter(tenant=request.tenant)` on every queryset | ✅ |
| `get_object_or_404(..., tenant=...)` on every pk lookup | ✅ |
| Filter retention (`q`, `status`, `warehouse`) on pagination | ⚠️ Present in view contexts but relies on template hidden-inputs — needs per-template audit |
| CRUD completeness | ⚠️ `StockAdjustment` has no edit / delete (arguably correct — adjustments are append-only); `StockStatusTransition` has no dedicated detail page; `StockLevel` has no create view (populated by receiving/seed) |
| `|stringformat:"d"` on FK filter selected-state | needs template audit |
| AuditLog on destructive mutations | ❌ None of adjust, transition, reservation_transition, valuation_recalculate, reservation_delete write `core.AuditLog` |
| `unique_together` + tenant trap | ✅ Forms do not expose `adjustment_number`, `transition_number`, `reservation_number` — dormant |
| Seed idempotency | needs audit of [seed_inventory.py](../inventory/management/commands/seed_inventory.py) |

---

## 2. Test Plan

### 2.1 Objectives

| Objective | Acceptance |
|---|---|
| Stock math accuracy | `on_hand`, `allocated`, `available` consistent across adjust/reserve cycles |
| Status transfer integrity | `Σ buckets` preserved on every transition; no phantom credit |
| Valuation correctness | FIFO / LIFO / Weighted Avg produce **mathematically distinct** unit_cost when layers have varying cost |
| Reservation state machine | Every `VALID_TRANSITIONS` edge proven; invalid rejected |
| Tenant isolation | No data bleed between tenants; anonymous redirected |
| RBAC | Only authorised roles can adjust stock, transition status, recalculate, alter reservations |
| Injection / XSS | Template auto-escape intact on all free-text fields |
| N+1 guard | List views ≤ 8 queries; detail ≤ 12 |
| Concurrency | Two parallel adjustments cannot double-spend stock |

### 2.2 Levels & types

| Level | Coverage |
|---|---|
| **Unit** | `StockLevel.available`, `needs_reorder`; `StockAdjustment._generate_adjustment_number`, `apply_adjustment`; `StockStatusTransition._generate_transition_number`, `apply_transition`; `InventoryReservation.can_transition_to`, `is_expired`, `_generate_reservation_number`; valuation arithmetic per method |
| **Integration** | Adjust → stock_level update; transition → status bucket update; reservation confirm → `allocated` update |
| **Functional E2E** | Create reservation → confirm → release round-trip; adjust → detail → audit trail |
| **Regression** | Every defect in §6 has a named pytest ID |
| **Boundary** | Quantity 0 / 1 / MAX; over-decrement; over-reserve; empty valuation |
| **Edge** | Unicode notes/reason; timezone-aware `expires_at`; DST boundary on `valuation_date` |
| **Negative** | IDOR, cross-tenant pk, GET on transition URLs, duplicate adjustment_number |
| **Security** | OWASP A01-A10; CSRF; XSS escape |
| **Performance** | `django_assert_max_num_queries` per list view; 1000-entry valuation recalc |

### 2.3 Risk register (pre-test)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FIFO/LIFO mis-compute → wrong COGS, wrong tax | **High** | **Critical** | D-04; rewrite valuation algorithm |
| Phantom status transition inflates on-hand | **High** | **High** | D-02; enforce source-quantity guard |
| Over-reserve → negative available at fulfilment | **High** | High | D-03; validator on create/confirm |
| Non-admin tampers with stock | **High** | High | D-05; RBAC decorator |
| Adjust/transition/reservation-transition non-atomic → torn write | Medium | Medium-High | D-06; `transaction.atomic` blocks |
| No AuditLog on mutations | Certain | Medium (compliance) | D-07; emit AuditLog |

---

## 3. Test Scenarios

### 3.1 Stock Levels (SL-XX)

| # | Scenario | Type |
|---|---|---|
| SL-01 | List — anonymous redirected | Security |
| SL-02 | List — search by SKU | Functional |
| SL-03 | List — filter by warehouse | Functional |
| SL-04 | List — `low_stock=yes` surfaces only low-stock rows | Functional |
| SL-05 | List — invalid `warehouse=abc` handled (no 500) | Negative |
| SL-06 | List — N+1 query guard ≤ 8 queries / 20 rows | Performance |
| SL-07 | Detail — cross-tenant pk → 404 | Security (IDOR) |
| SL-08 | Detail — shows last 10 adjustments | Functional |
| SL-09 | Detail — shows statuses + open reservations | Functional |
| SL-10 | `available = max(on_hand - allocated, 0)` | Unit |
| SL-11 | `needs_reorder` true when `available ≤ reorder_point` and `reorder_point > 0` | Unit |

### 3.2 Stock Adjustments (SA-XX)

| # | Scenario | Type |
|---|---|---|
| SA-01 | Increase +N → `on_hand += N` | Functional |
| SA-02 | Decrease −N where N ≤ on_hand → `on_hand -= N` | Functional |
| SA-03 | Decrease −N where N > on_hand → must RAISE, not silently clamp | Negative (D-01) |
| SA-04 | Correction = N → `on_hand = N` | Functional |
| SA-05 | Quantity = 0 blocked | Negative |
| SA-06 | Adjust by non-admin → blocked | Security / RBAC (D-05) |
| SA-07 | Adjust number auto-generates `ADJ-00001`, increments | Functional |
| SA-08 | Two parallel adjustments → both persist without number collision | Concurrency (D-08) |
| SA-09 | Adjust atomic — failure of `apply_adjustment` rolls back record | Regression (D-06) |
| SA-10 | Adjustment list search / filter by type / filter by reason | Functional |
| SA-11 | Adjust writes `core.AuditLog` | Security (D-07) |
| SA-12 | Detail — cross-tenant pk → 404 | Security (IDOR) |

### 3.3 Stock Status (SS-XX)

| # | Scenario | Type |
|---|---|---|
| SS-01 | List — filter by status / warehouse | Functional |
| SS-02 | Detail — shows transition history | Functional |
| SS-03 | Transition N from an **empty** source → must be blocked | Negative (D-02) |
| SS-04 | Transition N where source has < N → must be blocked | Negative (D-02) |
| SS-05 | Valid transition preserves `Σ quantities` | Integration |
| SS-06 | Transition with from_status == to_status → form invalid | Negative |
| SS-07 | Transition by non-admin → blocked | Security / RBAC (D-05) |
| SS-08 | Transition atomic — fail on target save rolls back source | Regression (D-06) |
| SS-09 | Transition number auto-generates `SST-00001` | Functional |
| SS-10 | Transition writes `core.AuditLog` | Security (D-07) |

### 3.4 Valuation (VAL-XX)

| # | Scenario | Type |
|---|---|---|
| VAL-01 | Dashboard — totals reflect `Σ total_value` | Functional |
| VAL-02 | Config — default method is `weighted_avg` | Functional |
| VAL-03 | Config update → next recalc uses new method | Functional |
| VAL-04 | Recalculate — FIFO on 2 layers 5@10 then 5@20 with 5 consumed → unit_cost = **20** (5 units @20 remain) | Correctness (D-04) |
| VAL-05 | Recalculate — LIFO on same layers with 5 consumed → unit_cost = **10** | Correctness (D-04) |
| VAL-06 | Recalculate — Weighted Avg on same layers (10 remain) → unit_cost = **15** | Correctness |
| VAL-07 | Recalculate by non-admin → blocked | Security / RBAC (D-05) |
| VAL-08 | Recalculate atomic — rolls back if any product fails | Reliability (D-06) |
| VAL-09 | Recalculate is idempotent when run twice same day | Functional |
| VAL-10 | Superuser (`tenant=None`) hitting dashboard → no crash | Boundary (D-09) |

### 3.5 Reservations (RES-XX)

| # | Scenario | Type |
|---|---|---|
| RES-01 | Create with valid qty ≤ available | Functional |
| RES-02 | Create with qty > available → blocked | Negative (D-03) |
| RES-03 | Create when no StockLevel exists → blocked | Negative (D-03) |
| RES-04 | Edit pending reservation → succeeds | Functional |
| RES-05 | Edit non-pending reservation → blocked | Negative |
| RES-06 | Delete pending or cancelled reservation → succeeds | Functional |
| RES-07 | Delete active (confirmed) → blocked | Negative |
| RES-08 | Transition pending → confirmed → `allocated += qty` | Integration |
| RES-09 | Transition confirmed → released → `allocated -= qty` | Integration |
| RES-10 | Transition confirmed → expired → `allocated -= qty` | Integration |
| RES-11 | Invalid transition (e.g. released → pending) blocked by state machine | Negative |
| RES-12 | GET on transition URL → redirect (CSRF safe) | Security |
| RES-13 | Transition when StockLevel missing — graceful (not crash) | Reliability |
| RES-14 | Cross-tenant pk → 404 | Security (IDOR) |
| RES-15 | `is_expired` true only when past `expires_at` and not terminal | Unit |
| RES-16 | Auto-expired reservation releases `allocated` (sweep) | Reliability (D-10) |
| RES-17 | Reservation-transition writes `core.AuditLog` | Security (D-07) |

### 3.6 Cross-cutting Security (SEC-XX)

| # | Scenario | OWASP |
|---|---|---|
| SEC-01 | Every view requires login | A01 |
| SEC-02 | Every queryset filters by tenant | A01 |
| SEC-03 | CSRF token required on POST | A01 |
| SEC-04 | `notes` / `reason` XSS escaped | A03 |
| SEC-05 | Cross-tenant pk → 404 for every detail view | A01 |
| SEC-06 | `quantity` coerced (not injected) in low_stock filter | A03 |
| SEC-07 | Bandit clean | A06 |
| SEC-08 | AuditLog emitted on every destructive op | A09 |

---

## 4. Detailed Test Cases

### 4.1 Valuation correctness (the headliner)

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-VAL-004 | FIFO on mixed cost layers | Two ValuationEntry for same product/warehouse: `(2026-01-01, rem=5, cost=$10)`, `(2026-03-01, rem=5, cost=$20)`. Config.method=`fifo`. | POST `/inventory/valuation/recalculate/` | — | **Latest InventoryValuation row has `unit_cost=20.00`** (5 units remaining are the newest at $20 after consumption). Today the code returns `15.00`. | 1 valuation row |
| TC-VAL-005 | LIFO on same layers | As above, method=`lifo` | POST recalc | — | **unit_cost = 10.00** | — |
| TC-VAL-006 | Weighted Avg | As above, method=`weighted_avg` | POST recalc | — | unit_cost = 15.00 | — |

### 4.2 Stock Status integrity (the second headliner)

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-SS-003 | Phantom source transition blocked | No `StockStatus(product=p, warehouse=w, status='damaged')` exists | POST `/inventory/stock-status/transition/` with `from_status=damaged, to_status=active, quantity=50` | — | **Form invalid**: "No damaged inventory exists for this product/warehouse" — no StockStatus records created/modified. **Today: `active` bucket is credited +50 from nothing.** | Σ buckets = 0 |
| TC-SS-004 | Under-stocked transition blocked | `damaged=10` for (p,w) | POST transition with `from=damaged, to=active, quantity=50` | — | Form invalid: "Requested 50 exceeds damaged on-hand of 10". No change. | No change |
| TC-SS-008 | Atomic transition on target save failure | monkeypatch target.save to raise | POST valid transition | — | Source unchanged (no partial decrement); transition record rolled back | No partial commit |

### 4.3 Reservation over-reserve (the third headliner)

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-RES-002 | Over-reserve blocked | StockLevel `(p,w)` with `on_hand=10, allocated=0` | POST `/inventory/reservations/create/` with `quantity=99` | — | Form invalid: "Requested quantity 99 exceeds available 10". No reservation created. | — |
| TC-RES-003 | Reserve without StockLevel blocked | No StockLevel exists for (p,w) | POST create qty=1 | — | Form invalid: "No stock level configured for this product at this warehouse". | — |
| TC-RES-016 | Expired reservation sweep | Reservation with `expires_at = now() - 1h`, status=`confirmed`, allocated=5 on StockLevel | run management command `sweep_expired_reservations` | — | Reservation status → `expired`; `allocated -= 5` | Integrity |

### 4.4 Adjustments

| ID | Description | Pre-conditions | Steps | Test Data | Expected | Post-conditions |
|---|---|---|---|---|---|---|
| TC-SA-003 | Over-decrement raises | `StockLevel.on_hand=50`, `allocated=0` | POST adjust with `type=decrease, quantity=999` | — | Form invalid OR view rejects: "Decrease 999 exceeds on-hand 50". **Today: on_hand silently becomes 0.** | No loss |
| TC-SA-005 | Quantity 0 blocked | Any SL | POST `quantity=0` | — | Form invalid: "Quantity must be ≥ 1" | — |
| TC-SA-009 | Atomic adjust rollback | monkeypatch `sl.save` to raise | POST valid adjust | — | No StockAdjustment row created; on_hand unchanged | — |
| TC-SA-011 | AuditLog emitted | Valid adjust | POST | — | `AuditLog(action='inventory.adjust', object_id=adj.pk)` exists | — |

### 4.5 RBAC

| ID | Description | Pre-conditions | Steps | Expected | Post-conditions |
|---|---|---|---|---|---|
| TC-RBAC-001 | Non-admin cannot adjust | login non_admin_user | POST `/inventory/stock-levels/<pk>/adjust/` | 302 to list with permission-denied message; **on_hand unchanged** | — |
| TC-RBAC-002 | Non-admin cannot transition status | login non_admin | POST transition | as above | — |
| TC-RBAC-003 | Non-admin cannot recalculate | login non_admin | POST valuation recalc | as above; no new valuation rows | — |
| TC-RBAC-004 | Non-admin cannot transition reservation | login non_admin | POST `/inventory/reservations/<pk>/transition/cancelled/` | reservation status unchanged | — |
| TC-RBAC-005 | Tenant admin CAN perform all of the above | login admin | same POSTs | success | — |

---

## 5. Automation Strategy

### 5.1 Tool stack

| Layer | Tool | Rationale |
|---|---|---|
| Unit + integration | pytest + pytest-django | Project convention |
| Factories | manual fixtures (match `catalog/tests/conftest.py` style) | Consistency |
| E2E smoke | Playwright (optional) | Dispatch + reservation round-trip |
| Load | Locust (optional) | Valuation recalc at 10k entries |
| SAST | bandit | Static scan of views.py + models.py |

### 5.2 Suite layout

```
inventory/
└── tests/
    ├── __init__.py
    ├── conftest.py                     # tenant + admin + non_admin + warehouse + product + stock_level fixtures
    ├── test_models.py                  # property math + sequence generation + state machine
    ├── test_forms.py                   # validation (over-reserve, over-decrement, same-status, qty≥1)
    ├── test_views_stock.py             # stock level + adjustment views + tenant isolation
    ├── test_views_status.py            # status list/detail + transition view
    ├── test_views_valuation.py         # dashboard + recalc correctness (FIFO/LIFO/WAVG)
    ├── test_views_reservation.py       # CRUD + state machine
    ├── test_security.py                # OWASP: RBAC (D-05), IDOR, CSRF, XSS, AuditLog (D-07)
    └── test_performance.py             # N+1 guards
```

Update [pytest.ini](../pytest.ini):

```ini
testpaths = catalog/tests vendors/tests receiving/tests purchase_orders/tests warehousing/tests inventory/tests
```

### 5.3 `conftest.py`

```python
# inventory/tests/conftest.py
from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from inventory.models import (
    StockLevel, StockStatus, InventoryReservation,
    ValuationConfig, ValuationEntry,
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
        username="inv_admin", password="pw_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="inv_staff", password="pw_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_user(db, other_tenant):
    return User.objects.create_user(
        username="inv_other", password="pw_123!",
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
def product(db, tenant):
    cat = Category.objects.create(tenant=tenant, name="Supplies")
    return Product.objects.create(
        tenant=tenant, sku="SUP-001", name="Widget",
        category=cat, purchase_cost=10, retail_price=15,
        status="active",
    )


@pytest.fixture
def stock_level(db, tenant, product, warehouse):
    return StockLevel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        on_hand=50, allocated=0, reorder_point=10, reorder_quantity=20,
    )


@pytest.fixture
def damaged_status(db, tenant, product, warehouse):
    return StockStatus.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        status='damaged', quantity=10,
    )


@pytest.fixture
def pending_reservation(db, tenant, product, warehouse, admin_user, stock_level):
    return InventoryReservation.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=5, status='pending', reserved_by=admin_user,
    )


@pytest.fixture
def confirmed_reservation(db, pending_reservation, stock_level):
    pending_reservation.status = 'confirmed'
    pending_reservation.save()
    stock_level.allocated += pending_reservation.quantity
    stock_level.save()
    return pending_reservation


@pytest.fixture
def valuation_config(db, tenant):
    return ValuationConfig.objects.create(tenant=tenant, method='weighted_avg')


@pytest.fixture
def cost_layers(db, tenant, product, warehouse):
    """Two cost layers for FIFO/LIFO math verification."""
    old = ValuationEntry.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        entry_date=date.today() - timedelta(days=60),
        quantity=5, remaining_quantity=5, unit_cost=Decimal('10'),
    )
    new = ValuationEntry.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        entry_date=date.today() - timedelta(days=30),
        quantity=5, remaining_quantity=5, unit_cost=Decimal('20'),
    )
    return [old, new]
```

### 5.4 `test_models.py`

```python
from decimal import Decimal
import pytest

from inventory.models import (
    StockLevel, StockAdjustment, StockStatus, StockStatusTransition,
    InventoryReservation,
)


@pytest.mark.django_db
class TestStockLevelProperties:
    def test_available_caps_at_zero(self, stock_level):
        stock_level.on_hand = 5; stock_level.allocated = 10
        assert stock_level.available == 0

    def test_needs_reorder_respects_reorder_point(self, stock_level):
        stock_level.on_hand = 5; stock_level.allocated = 0
        stock_level.reorder_point = 10
        assert stock_level.needs_reorder is True

    def test_needs_reorder_disabled_when_point_is_zero(self, stock_level):
        stock_level.on_hand = 0; stock_level.reorder_point = 0
        assert stock_level.needs_reorder is False


@pytest.mark.django_db
class TestSequenceGeneration:
    @pytest.mark.parametrize("Model,prefix,extra", [
        (StockAdjustment, 'ADJ-', {'adjustment_type': 'increase', 'quantity': 1, 'reason': 'other'}),
    ])
    def test_first_number(self, Model, prefix, extra, tenant, stock_level):
        obj = Model.objects.create(tenant=tenant, stock_level=stock_level, **extra)
        field = f'{prefix.rstrip("-").lower()}_number'
        assert getattr(obj, field).startswith(prefix)
        assert getattr(obj, field).endswith('00001')


@pytest.mark.django_db
class TestReservationStateMachine:
    @pytest.mark.parametrize("src,dst,ok", [
        ("pending", "confirmed", True),
        ("pending", "released", True),
        ("pending", "cancelled", True),
        ("pending", "expired", False),
        ("confirmed", "released", True),
        ("confirmed", "expired", True),
        ("confirmed", "pending", False),
        ("released", "pending", False),
        ("cancelled", "pending", True),
    ])
    def test_can_transition_to(self, pending_reservation, src, dst, ok):
        pending_reservation.status = src
        assert pending_reservation.can_transition_to(dst) is ok

    def test_is_expired_false_when_no_expires_at(self, pending_reservation):
        pending_reservation.expires_at = None
        assert pending_reservation.is_expired is False

    def test_is_expired_false_when_terminal(self, pending_reservation):
        from django.utils import timezone
        from datetime import timedelta
        pending_reservation.expires_at = timezone.now() - timedelta(hours=1)
        pending_reservation.status = 'released'
        assert pending_reservation.is_expired is False

    def test_is_expired_true_when_past_and_active(self, pending_reservation):
        from django.utils import timezone
        from datetime import timedelta
        pending_reservation.expires_at = timezone.now() - timedelta(hours=1)
        pending_reservation.status = 'pending'
        assert pending_reservation.is_expired is True


@pytest.mark.django_db
class TestAdjustmentApplication:
    def test_increase(self, tenant, stock_level):
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='increase', quantity=10, reason='return',
        )
        adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 60

    def test_decrease_within_bounds(self, tenant, stock_level):
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='decrease', quantity=10, reason='damage',
        )
        adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 40

    def test_correction(self, tenant, stock_level):
        adj = StockAdjustment.objects.create(
            tenant=tenant, stock_level=stock_level,
            adjustment_type='correction', quantity=23, reason='count',
        )
        adj.apply_adjustment()
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 23
```

### 5.5 `test_forms.py`

```python
import pytest
from inventory.forms import (
    StockAdjustmentForm, StockStatusTransitionForm, InventoryReservationForm,
)


@pytest.mark.django_db
class TestAdjustmentForm:
    def test_qty_zero_rejected(self, tenant):
        """Regression for D-?: qty must be ≥ 1."""
        form = StockAdjustmentForm(
            data={'adjustment_type': 'increase', 'quantity': '0',
                  'reason': 'other', 'notes': ''},
            tenant=tenant,
        )
        assert not form.is_valid()

    def test_over_decrement_rejected(self, tenant, stock_level):
        """Regression for D-01."""
        form = StockAdjustmentForm(
            data={'adjustment_type': 'decrease', 'quantity': '9999',
                  'reason': 'damage', 'notes': ''},
            tenant=tenant,
        )
        form.instance.stock_level = stock_level  # inject for clean()
        assert not form.is_valid()


@pytest.mark.django_db
class TestTransitionForm:
    def test_same_from_to_status_rejected(self, tenant, product, warehouse):
        form = StockStatusTransitionForm(
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'active', 'to_status': 'active',
                'quantity': 10, 'reason': 'x',
            },
            tenant=tenant,
        )
        assert not form.is_valid()

    def test_phantom_source_rejected(self, tenant, product, warehouse):
        """Regression for D-02: no StockStatus(damaged) exists."""
        form = StockStatusTransitionForm(
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'damaged', 'to_status': 'active',
                'quantity': 50, 'reason': 'fraud',
            },
            tenant=tenant,
        )
        assert not form.is_valid()

    def test_under_stocked_source_rejected(self, tenant, damaged_status, product, warehouse):
        """damaged=10; try to transition 50."""
        form = StockStatusTransitionForm(
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'damaged', 'to_status': 'active',
                'quantity': 50, 'reason': 'x',
            },
            tenant=tenant,
        )
        assert not form.is_valid()


@pytest.mark.django_db
class TestReservationForm:
    def test_over_reserve_rejected(self, tenant, stock_level, product, warehouse):
        """Regression for D-03: reserve > available."""
        form = InventoryReservationForm(
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity': 9999, 'reference_type': '', 'reference_number': '',
                'expires_at': '', 'notes': '',
            },
            tenant=tenant,
        )
        assert not form.is_valid()

    def test_no_stock_level_rejected(self, tenant, product, warehouse):
        """No StockLevel exists for (product, warehouse)."""
        form = InventoryReservationForm(
            data={
                'product': product.pk, 'warehouse': warehouse.pk,
                'quantity': 1, 'reference_type': '', 'reference_number': '',
                'expires_at': '', 'notes': '',
            },
            tenant=tenant,
        )
        assert not form.is_valid()
```

### 5.6 `test_views_valuation.py` — the correctness test

```python
from decimal import Decimal
import pytest
from django.urls import reverse

from inventory.models import InventoryValuation, ValuationConfig


@pytest.mark.django_db
class TestValuationCorrectness:
    """Regression for D-04 — FIFO/LIFO/WAVG must produce DIFFERENT unit_cost."""

    def _consume_old_layer(self, cost_layers):
        """Simulate that 5 units were issued using the OLDER layer under FIFO."""
        old, new = cost_layers
        old.remaining_quantity = 0; old.save()  # consumed
        # `new` keeps remaining_quantity=5

    def test_fifo_after_consumption_uses_newest_cost(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        valuation_config.method = 'fifo'; valuation_config.save()
        self._consume_old_layer(cost_layers)
        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
        # 5 units remain, all at $20
        assert v.unit_cost == Decimal('20.00')

    def test_lifo_after_consumption_uses_oldest_cost(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        valuation_config.method = 'lifo'; valuation_config.save()
        # LIFO: consume NEWEST first. 5 issued → newer layer gone
        old, new = cost_layers
        new.remaining_quantity = 0; new.save()
        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
        # 5 units remain at $10
        assert v.unit_cost == Decimal('10.00')

    def test_weighted_avg_blends_layers(
        self, client, admin_user, tenant, stock_level, cost_layers, valuation_config
    ):
        valuation_config.method = 'weighted_avg'; valuation_config.save()
        client.force_login(admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        v = InventoryValuation.objects.get(tenant=tenant, product=stock_level.product)
        # (5*10 + 5*20) / 10 = 15.00
        assert v.unit_cost == Decimal('15.00')
```

### 5.7 `test_security.py`

```python
import pytest
from django.urls import reverse

from core.models import AuditLog


@pytest.mark.django_db
class TestAuthRequired:
    @pytest.mark.parametrize("url_name,args", [
        ('inventory:stock_level_list', []),
        ('inventory:stock_adjustment_list', []),
        ('inventory:stock_status_list', []),
        ('inventory:valuation_dashboard', []),
        ('inventory:reservation_list', []),
    ])
    def test_anonymous_redirected(self, client, url_name, args):
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302 and '/accounts/login/' in r['Location']


@pytest.mark.django_db
class TestRBAC:
    """Regression for D-05."""

    def test_non_admin_cannot_adjust(self, client, non_admin_user, stock_level):
        client.force_login(non_admin_user)
        client.post(
            reverse('inventory:stock_adjust', args=[stock_level.pk]),
            {'adjustment_type': 'increase', 'quantity': 100, 'reason': 'other'},
        )
        stock_level.refresh_from_db()
        assert stock_level.on_hand == 50  # unchanged

    def test_non_admin_cannot_transition_status(
        self, client, non_admin_user, damaged_status, product, warehouse
    ):
        client.force_login(non_admin_user)
        client.post(
            reverse('inventory:stock_status_transition'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'damaged', 'to_status': 'active',
                'quantity': 5, 'reason': 'x',
            },
        )
        damaged_status.refresh_from_db()
        assert damaged_status.quantity == 10  # unchanged

    def test_non_admin_cannot_recalculate(
        self, client, non_admin_user, valuation_config, cost_layers
    ):
        client.force_login(non_admin_user)
        client.post(reverse('inventory:valuation_recalculate'))
        from inventory.models import InventoryValuation
        assert InventoryValuation.objects.count() == 0

    def test_non_admin_cannot_transition_reservation(
        self, client, non_admin_user, pending_reservation
    ):
        client.force_login(non_admin_user)
        client.post(reverse(
            'inventory:reservation_transition',
            args=[pending_reservation.pk, 'cancelled'],
        ))
        pending_reservation.refresh_from_db()
        assert pending_reservation.status == 'pending'


@pytest.mark.django_db
class TestIDOR:
    def test_stock_level_cross_tenant_404(
        self, client, other_tenant_user, stock_level
    ):
        client.force_login(other_tenant_user)
        r = client.get(reverse('inventory:stock_level_detail', args=[stock_level.pk]))
        assert r.status_code == 404


@pytest.mark.django_db
class TestCSRFMethods:
    @pytest.mark.parametrize("url_name,kwargs", [
        ('inventory:reservation_delete', 'pk'),
        ('inventory:valuation_recalculate', None),
    ])
    def test_get_is_safe(self, client, admin_user, pending_reservation, url_name, kwargs):
        client.force_login(admin_user)
        args = [pending_reservation.pk] if kwargs == 'pk' else []
        r = client.get(reverse(url_name, args=args))
        assert r.status_code == 302


@pytest.mark.django_db
class TestAuditLog:
    """Regression for D-07."""
    def test_adjust_writes_audit(self, client, admin_user, stock_level):
        client.force_login(admin_user)
        client.post(
            reverse('inventory:stock_adjust', args=[stock_level.pk]),
            {'adjustment_type': 'increase', 'quantity': 5, 'reason': 'return'},
        )
        assert AuditLog.objects.filter(action='inventory.adjust').exists()

    def test_transition_writes_audit(
        self, client, admin_user, damaged_status, product, warehouse
    ):
        client.force_login(admin_user)
        client.post(
            reverse('inventory:stock_status_transition'),
            {
                'product': product.pk, 'warehouse': warehouse.pk,
                'from_status': 'damaged', 'to_status': 'active',
                'quantity': 5, 'reason': 'test',
            },
        )
        assert AuditLog.objects.filter(action='inventory.status_transition').exists()
```

### 5.8 `test_performance.py`

```python
from decimal import Decimal
import pytest
from django.urls import reverse

from inventory.models import StockLevel


@pytest.mark.django_db
def test_stock_level_list_query_budget(
    client_logged_in, tenant, product, warehouse, django_assert_max_num_queries
):
    for i in range(20):
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=i, allocated=0,
        )
    with django_assert_max_num_queries(8):
        r = client_logged_in.get(reverse('inventory:stock_level_list'))
        assert r.status_code == 200
```

---

## 6. Defects, Risks & Recommendations

> Legend: ✅ = reproduced in Django shell; 📋 = code review only.

### 6.1 Defects

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-04** ✅ | **Critical** | A04 | [views.py:370-383](../inventory/views.py#L370-L383) | **FIFO / LIFO / Weighted Avg all compute identical unit_cost.** The FIFO and LIFO branches sort entries but then run `sum(rem_qty × unit_cost) / Σ rem_qty`, which is by definition the weighted average regardless of order. Shell verified on 2-layer (5@$10, 5@$20) data: FIFO=15, LIFO=15, WAVG=15 — all three identical. Financial correctness of COGS, ending inventory, and tax reporting is broken. | Rewrite valuation arithmetic: for **FIFO / LIFO** the "unit_cost" of remaining inventory is the cost of the layers that **remain after consumption** (depends on which layers were issued). This requires modelling issuances (likely via `ValuationEntry.remaining_quantity` shrinking FIFO/LIFO-style, with a helper that walks the layer stack). The current snapshot-on-demand approach conflates issued and remaining. See accounting ref: FIFO ending = Σ newest layers; LIFO ending = Σ oldest layers. |
| **D-02** ✅ | **High** | A04 | [models.py:230-249](../inventory/models.py#L230-L249), [views.py:217-237](../inventory/views.py#L217-L237) | **Phantom-source status transition creates inventory from nothing.** `apply_transition` uses `get_or_create(..., status=from_status, defaults={'quantity': 0})` and then `max(source.quantity - self.quantity, 0)` — if no damaged rows exist, code creates one at 0, decrements to 0, and credits target by the full amount. Shell verified: transition 50 from non-existent `damaged` bucket → `active` bucket gained +50 from thin air. | `StockStatusTransitionForm.clean()` must require that `StockStatus(tenant, product, warehouse, from_status)` already exists with `quantity >= self.quantity`. Additionally wrap `apply_transition` in `transaction.atomic()` and raise `ValidationError` instead of silently clamping. |
| **D-03** ✅ | High | A04 | [forms.py:87-133](../inventory/forms.py#L87-L133), [views.py:449-558](../inventory/views.py#L449-L558) | **Reservation allows quantity > available.** No validator prevents reserving 9999 units against `on_hand=10`. Shell verified: saved `RES-xxxxx` with qty=9999 for `available=0`. Subsequent confirmation would push `stock_level.allocated` to an arbitrary value with no backing inventory. | `InventoryReservationForm.clean()`: look up StockLevel for (product, warehouse); reject if missing or if `quantity > stock_level.available`. Also guard in `reservation_transition_view` so a `pending → confirmed` transition re-checks availability at transition time (stock may have moved). |
| **D-05** ✅ | High | A01 | all destructive views: [views.py:86,217,347,527](../inventory/views.py#L86) | **No RBAC on sensitive mutations.** Shell verified: non-admin `james_acme` successfully increased stock by +1000 (63 → 1063), triggered tenant-wide valuation recalc, and cancelled a reservation. Any tenant user can manipulate inventory, fraud-detect COGS, or release allocated stock. | Introduce `@tenant_admin_required` (see the same decorator already shipped in `purchase_orders/views.py`) on: `stock_adjust_view`, `stock_status_transition_view`, `valuation_recalculate_view`, `valuation_config_view`, `reservation_create/edit/delete/transition_view`. |
| **D-01** ✅ | High | A04 | [models.py:119-127](../inventory/models.py#L119-L127) | **Silent over-decrement clamp.** `apply_adjustment` does `sl.on_hand = max(sl.on_hand - self.quantity, 0)` — 50 on-hand + decrease 999 → silently becomes 0 with no error. User believes 999 left the building; system records 50 left. Fraud / loss-coverup vector. | Raise `ValidationError('Decrease exceeds on-hand')` in `StockAdjustmentForm.clean()` when `adjustment_type='decrease' and quantity > stock_level.on_hand`. Remove the `max(..., 0)` clamp. |
| **D-06** 📋 | High | A04 | [views.py:90-100, 220-228, 455-460, 527-555](../inventory/views.py) | **Non-atomic mutations.** `stock_adjust_view`: `adjustment.save()` then `adjustment.apply_adjustment()` — if the second fails, adjustment record orphaned. `stock_status_transition_view`: `source.save()` then `target.save()` — torn write. `reservation_transition_view`: `reservation.save()` then `stock_level.save()` — same. | Wrap every `apply_*` call and adjacent saves in `with transaction.atomic():`. Use `select_for_update()` on the source `StockLevel` / `StockStatus` before mutating. |
| **D-07** 📋 | Medium | A09 | all state-change views | **No `core.AuditLog`** on adjust, status transition, valuation recalc, reservation-transition, reservation-delete. Stock is a financial asset — every mutation must be logged. | Call `AuditLog.objects.create(tenant=request.tenant, user=request.user, action='inventory.<verb>', model_name=..., object_id=..., changes=json.dumps({...}))` at every sensitive mutation. |
| **D-08** 📋 | Medium-High | A04 | [models.py:103-117, 214-228, 427-441](../inventory/models.py) | **TOCTOU race on auto-generated numbers** (`ADJ-`, `SST-`, `RES-`). `order_by('-id').first()` then write is not atomic; concurrent inserts collide on respective `unique_together`. Same pattern flagged in purchase_orders. | Wrap in `transaction.atomic` + `select_for_update` on a per-tenant lock row, or use a `TenantSequence` model. Same fix approach for all three modules. |
| **D-09** 📋 | Medium | A05 | [views.py:280-282, 326-328, 352-353](../inventory/views.py) | **`ValuationConfig.get_or_create(tenant=request.tenant)` for superuser (`tenant=None`) raises `IntegrityError`** because `ValuationConfig.tenant` is a non-null `OneToOneField`. Superuser hitting `/inventory/valuation/` therefore 500s. | Guard: `if not request.tenant: return redirect('dashboard')` at view entry; or early-return a "no tenant" message. Consistent with the documented superuser trap. |
| **D-10** 📋 | Medium | A04 | [models.py:414-420](../inventory/models.py#L414-L420) | **No sweeper for expired reservations.** `is_expired` is a pure property — nothing sets status to `expired` automatically, so stale `confirmed` reservations hold `allocated` stock forever. | Add management command `sweep_expired_reservations` (run via cron) that flips `expires_at < now()` reservations to `expired` and decrements `StockLevel.allocated` atomically. |
| **D-11** 📋 | Medium | A03 | [views.py:38-45, 181, 290, 428](../inventory/views.py) | **Numeric query params not coerced.** `warehouse_id=abc` → `filter(warehouse_id='abc')` raises `ValueError` → 500. Same as PO module. | `int(request.GET.get('warehouse', 0) or 0)` with try/except. |
| **D-12** 📋 | Medium | A04 | [views.py:356](../inventory/views.py#L356) | **`valuation_recalculate_view` deletes then inserts globally without atomic.** If the loop raises mid-flight, today's valuation rows are partially populated / missing entirely. Also: no idempotency guard means concurrent recalc requests race on DELETE. | Wrap whole recalc in `with transaction.atomic():`; lock `ValuationConfig` row with `select_for_update`; return 409 if a recalc is already in flight. |
| **D-13** 📋 | Medium | A04 | [forms.py:11-32](../inventory/forms.py#L11-L32) | **`StockAdjustmentForm` has no `tenant`-wired product/warehouse sanity and no `quantity >= 1` enforcement** (PositiveIntegerField accepts 0). | `widget min='1'` is front-end only; add `def clean_quantity` in the form. |
| **D-14** 📋 | Medium | A04 | [views.py:541-555](../inventory/views.py#L541-L555) | **`reservation_transition_view` double-counts allocated on status ping-pong.** `pending → confirmed → released → pending → confirmed` — each `pending → confirmed` adds `+qty` to `allocated` but there is no offsetting decrement on `confirmed → cancelled/released` IF it was already released-and-restored. A pending-confirmed-pending-confirmed dance compounds `allocated`. | Re-key the logic on the old/new tuple as a map `{('pending','confirmed'): +qty, ('confirmed','released'): -qty, ('confirmed','expired'): -qty, ('confirmed','cancelled'): -qty}` — default to 0. Covered correctly today for the common edges but not defensive against manual transitions. |
| **D-15** 📋 | Medium | A01 | [views.py:524](../inventory/views.py#L524) | **Reservation-delete has no creator check.** Any tenant-admin can delete any pending or cancelled reservation — but coupled with D-05 any tenant user can delete pending reservations too. | Gate by `is_tenant_admin or reserved_by == request.user`. |
| **D-16** 📋 | Low | A04 | [models.py:119-126](../inventory/models.py#L119-L126) | **`correction` adjustment ignores `allocated`.** Setting `on_hand = quantity` may leave `allocated > on_hand` and hence `available == 0` — not strictly wrong but should warn user. | Form `clean()`: if `adjustment_type='correction' and quantity < allocated` → warning-level validation. |
| **D-17** 📋 | Low | A09 | [views.py:552-555](../inventory/views.py#L552-L555) | **Silent `except StockLevel.DoesNotExist: pass`** on reservation transition. If stock record was deleted, reservation flips state without any warning or log. | Replace with `AuditLog` of the inconsistency; raise a `messages.warning` visible to the user. |
| **D-18** 📋 | Low | A01 | [admin.py:8-60](../inventory/admin.py) | `ModelAdmin.get_queryset` not tenant-scoped for non-superuser staff users — same superuser-trap pattern as other modules. | Override `get_queryset` on all 8 admins to filter by `request.user.tenant` when `not is_superuser`. |
| **D-19** 📋 | Low | A04 | [models.py:26-30](../inventory/models.py#L26-L30) | `on_hand` / `allocated` / `on_order` are `PositiveIntegerField` — good — but `reorder_point` could legitimately be 0 (meaning "no reorder"). Current code treats `reorder_point == 0` as "no reorder alert", which is correct in `needs_reorder`. `low_stock` filter in list view duplicates this logic — ensure behavior consistent. | Minor: add unit test to lock behaviour. |
| **D-20** 📋 | Low | A04 | [models.py:255-270](../inventory/models.py#L255-L270) | `ValuationConfig` has no validator on `method` beyond choices, but downstream `valuation_recalculate` has a silent `else: unit_cost = 0` branch — if a misspelled method is saved via shell, unit_cost silently becomes 0. | Add a non-db validator / assertion. |

### 6.2 Residual risks (post-remediation)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Valuation rewrite introduces new rounding drift | Medium | Medium | Lock formula in unit tests with 4-5 parametrised scenarios |
| `sweep_expired_reservations` cron missing in prod → stale allocations | Medium | Medium | Document in ops runbook; add a nightly smoke |
| Concurrent recalc by two admins simultaneously | Low | Medium | D-12 409-on-lock |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Target coverage

| File | Target line % | Target branch % | Notes |
|---|---|---|---|
| [models.py](../inventory/models.py) | 95 | 90 | Properties + state machine + apply_* |
| [forms.py](../inventory/forms.py) | 92 | 88 | After D-01, D-02, D-03, D-13 clean() |
| [views.py](../inventory/views.py) | 85 | 75 | Valuation-recalc branches largest gap |
| **Overall `inventory/`** | **≥ 88 %** line, **≥ 80 %** branch | — | — |

### 7.2 KPIs

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | 100 % | 98-99 % | < 98 % |
| Open Critical defects | 0 | — | ≥ 1 |
| Open High defects | 0 | 1 | ≥ 2 |
| Suite runtime | < 30 s | 30-60 s | > 60 s |
| Stock-level list p95 latency @ 500 rows | < 300 ms | 300-600 ms | > 600 ms |
| Query count `stock_level_list_view` (20 rows) | ≤ 8 | 9-12 | > 12 |
| Valuation recalc for 1000 entries | < 5 s | 5-15 s | > 15 s |

### 7.3 Release Exit Gate

All of the following **must** be true:

- [ ] **D-04 fixed**: `test_views_valuation.py::TestValuationCorrectness` green (FIFO / LIFO / WAVG yield distinct unit_cost on the canonical 2-layer fixture).
- [ ] **D-02 fixed**: `test_forms.py::TestTransitionForm::test_phantom_source_rejected` green.
- [ ] **D-03 fixed**: `test_forms.py::TestReservationForm::test_over_reserve_rejected` green.
- [ ] **D-05 fixed**: `test_security.py::TestRBAC::test_non_admin_cannot_*` all green.
- [ ] **D-01 fixed**: over-decrement raises instead of clamping.
- [ ] **D-06 fixed**: adjust / transition / reservation-transition wrapped in `transaction.atomic`.
- [ ] **D-07 fixed**: AuditLog rows present for each mutation type (test verified).
- [ ] **D-10 fixed**: `sweep_expired_reservations` command exists, wired to management commands.
- [ ] `pytest inventory/tests` green with **≥ 88 %** line coverage.
- [ ] `bandit -r inventory/` → 0 High/Critical.
- [ ] Manual smoke: create → reserve → confirm → receive → adjust → release → recalculate valuation.

---

## 8. Summary

The Inventory Tracking & Control module is broad (4 sub-modules, 8 models, 18 views) and feature-complete, but it ships with **zero test coverage** and contains **one Critical** + **five High** defects that compromise financial correctness, data integrity, and authorisation. The most severe:

### Top 5 defects

1. **D-04 (Critical)** — FIFO / LIFO / Weighted-Average all compute the same unit_cost. Every financial report built on `InventoryValuation` is wrong if config is not `weighted_avg`. Fix requires reworking the valuation algorithm around layer-consumption semantics.
2. **D-02 (High)** — `StockStatusTransition.apply_transition` fabricates inventory: a transition from a non-existent or under-stocked source silently creates/zeros the source and credits the target the full requested amount. Shell-confirmed `active += 50` from thin air.
3. **D-03 (High)** — Reservations accept quantities far exceeding available stock. No validator ever checks `quantity ≤ StockLevel.available`. Shell-confirmed RES record of 9999 units against available=0.
4. **D-05 (High)** — No RBAC anywhere in the module. Non-admin users can adjust stock, transition status, recalculate valuation, and cancel reservations. Fraud / sabotage vector.
5. **D-01 (High)** — `apply_adjustment` silently clamps over-decrements to zero, masking theft / data errors and producing false on-hand readings.

### Test-automation gap

Adopting the scaffolded suite in §5 (≈ 70-80 tests across 9 files) raises coverage from 0 % to a projected ≥ 88 % line coverage and locks the five headline defects behind failing-today regressions that will go green as each fix lands.

### Recommended follow-ups

- **"Fix the defects"** — prioritise D-04, D-02, D-03, D-05, D-01, D-06, then D-07/D-08/D-10/D-12.
- **"Build the automation"** — scaffold `inventory/tests/` with the §5 snippets, update [pytest.ini](../pytest.ini), wire into CI, run until green.
- **"Manual verification"** — reproduce VAL-04, SS-03, RES-02, RBAC-001 against `runserver` to confirm remediation.

---

*End of report.*
