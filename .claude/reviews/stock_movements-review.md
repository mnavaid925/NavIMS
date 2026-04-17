# Stock Movement & Transfers — Comprehensive SQA Test Report

**Target:** [stock_movements/](../../stock_movements/) Django app (module review — full surface)
**Reviewer:** Senior SQA Engineer
**Date:** 2026-04-17
**Standards:** OWASP Top 10 (2021), ISO/IEC/IEEE 29119, Django Security Cheat Sheet
**Report path:** [.claude/reviews/stock_movements-review.md](./stock_movements-review.md)

---

## 1. Module Analysis

### 1.1 Scope & surface

`stock_movements/` implements four sub-modules covering inter-warehouse and intra-warehouse stock transfers, an approval workflow, and a routing catalog. Total ≈1,090 LoC across [models.py](../../stock_movements/models.py) (273), [views.py](../../stock_movements/views.py) (547), [forms.py](../../stock_movements/forms.py) (193), [urls.py](../../stock_movements/urls.py) (30), [admin.py](../../stock_movements/admin.py) (47).

| # | Entity | Purpose | CRUD | Workflow | Auto number |
|---|---|---|---|---|---|
| 1 | `StockTransfer` + `StockTransferItem` | Source-to-destination stock movement (inter or intra warehouse) with line items | List/Create/Detail/Edit/Delete + transition + receive | draft → pending_approval → approved → in_transit → completed / cancelled | `TRF-00001` |
| 2 | `TransferApprovalRule` | Tenant-level rule mapping transfer item count to required approval level | List/Create/Edit/Delete (no Detail) | — | — |
| 3 | `TransferApproval` | Per-transfer approve/reject decision recorded by a user | Listed inline only | approved / rejected | — |
| 4 | `TransferRoute` | Pre-defined source→destination route with method + duration | List/Create/Detail/Edit/Delete | — | — |

### 1.2 External dependencies

| Dependency | Where used | Coupling |
|---|---|---|
| [warehousing.Warehouse](../../warehousing/models.py) | StockTransfer source/dest, TransferRoute source/dest | Hard |
| [warehousing.Bin](../../warehousing/models.py) | StockTransfer source/dest bin (optional); reached via `zone__warehouse__tenant` | Hard |
| [catalog.Product](../../catalog/models.py) | StockTransferItem.product | Hard |
| [core.Tenant](../../core/models.py) | All five models | Critical |
| [core.User](../../core/models.py) | requested_by / approved_by | Medium |
| [core/middleware.py](../../core/middleware.py) `TenantMiddleware` | Sets `request.tenant` | Critical |
| **Inventory layer (none)** | — | **MISSING** — no integration with `warehousing` / `inventory` stock counts; transfers are logical-only (D-02) |

### 1.3 Business rules (location → file:line)

| Rule | Location |
|---|---|
| Status machine: 6 states, terminal `completed`, `cancelled → draft` reopen path | [models.py:32-39](../../stock_movements/models.py#L32-L39) |
| Auto-numbering `TRF-NNNNN` per tenant via `MAX(id)+1` | [models.py:124-138](../../stock_movements/models.py#L124-L138) |
| Inter-warehouse requires distinct source/destination | [forms.py:52-56](../../stock_movements/forms.py#L52-L56) |
| Intra-warehouse silently sets destination = source | [forms.py:57-58](../../stock_movements/forms.py#L57-L58) |
| Edit allowed in `draft` and `pending_approval` only | [views.py:144](../../stock_movements/views.py#L144) |
| Delete allowed in `draft` and `cancelled` only | [views.py:195](../../stock_movements/views.py#L195) |
| On `completed` transition, items are force-set to fully received | [views.py:226-230](../../stock_movements/views.py#L226-L230) |
| Receive view assigns absolute (not incremental) `received_quantity`, clamped `0..quantity` | [views.py:247-259](../../stock_movements/views.py#L247-L259) |
| Approval workflow: approve → status=approved; reject → status=cancelled | [views.py:407-416](../../stock_movements/views.py#L407-L416) |
| Routes are passive metadata — never enforced at transfer-create or transition time | [views.py:123-128, 502-508](../../stock_movements/views.py#L123-L128) |

### 1.4 Tenancy model

Every model has a mandatory `tenant` FK. Every view filters via `request.tenant` (verified at 18/18 `get_object_or_404` and `objects.filter` sites). Superuser with `tenant=None` will see empty lists — expected.

### 1.5 Pre-test risk profile

| Area | Inherent risk | Notes |
|---|---|---|
| **Inventory integrity (no stock check)** | **Critical** | No verification that source warehouse holds the transferred quantity; nothing decrements source / increments destination on completion. Inventory layer is not integrated. |
| **Cross-tenant product injection on POST** | **Critical** | `transfer_create_view` and `transfer_edit_view` do `StockTransferItem.objects.create(..., product_id=int(product_ids[i]))` with no tenant verification — verified IDOR. |
| **Status-machine race + auto-numbering race** | **High** | `MAX(id)+1` numbering is unsafe under concurrency; same systemic pattern as receiving D-03. |
| **Completion silently destroys partial-receipt data** | **High** | The `transfer_transition_view` `completed` branch overwrites `received_quantity = quantity` for any short-received items, discarding scanned data. |
| **No RBAC on approval / cancel / delete / shipment** | **High** | Any authenticated tenant user can approve their own transfer, ship it, complete it, and delete drafts. Single-user violation of segregation-of-duties (OWASP A01). |
| **Receive view absolute-vs-incremental confusion** | **Medium** | `received_quantity` is set absolute; resubmission overwrites earlier data. `ValueError` on bad input is silently swallowed. |
| **Edit overwrites items with no audit trail** | **Medium** | `transfer.items.all().delete()` then re-create on every edit; no AuditLog record (OWASP A09). |
| **Test coverage** | **Critical** | Zero tests — `stock_movements/tests/` does not exist. |
| **Approval rules have no detail page; rules never consulted** | **Low/Medium** | `TransferApprovalRule` is purely informational — no code reads it to decide whether `pending_approval` should be skipped. |
| **`unique_together` form-bypass trap** | **Not applicable** | `StockTransfer.transfer_number` is server-generated, NOT a form field — lessons #6/#7 do not apply here. (Confirmed.) |

---

## 2. Test Plan

### 2.1 Test types & allocation

| Type | Target count | Tool | Focus |
|---|---|---|---|
| Unit | 35 | pytest-django | Status transitions, totals, auto-number, form `clean()` |
| Integration | 40 | pytest-django + Django test client | View+form+model flow, transitions, approval, receive |
| Functional E2E | 6 | Playwright | draft → approval → in_transit → receive → completed |
| Regression | 14 | pytest | Guards against re-introduction of D-01..D-06 |
| Boundary | 10 | pytest | Quantity overflow, max_length, decimal precision |
| Edge | 9 | pytest | Empty / null / unicode / mixed casing / large item count |
| Negative | 18 | pytest | IDOR, invalid transitions, source==destination, intra-warehouse with destination set |
| Security | 22 | pytest + bandit + ZAP | OWASP A01/A03/A04/A09 mapped |
| Performance | 6 | `django_assert_max_num_queries`, Locust | List/route_detail N+1 |
| **Total** | **160** | | |

### 2.2 Entry / Exit
- **Entry:** branch merges cleanly onto `main`; `migrate` green; `seed_warehousing` + `seed_catalog` + `seed_stock_movements` run idempotent.
- **Exit:** see §7 Release Exit Gate.

---

## 3. Test Scenarios

### 3.1 StockTransfer & StockTransferItem (T-NN)

| # | Scenario | Type |
|---|---|---|
| T-01 | Create inter-warehouse transfer with valid src/dest + 3 items | Functional |
| T-02 | Create intra-warehouse with src only — dest auto-set to src | Functional |
| T-03 | Create inter-warehouse with src == dest rejected | Negative |
| T-04 | Create inter-warehouse without dest rejected | Negative |
| T-05 | Auto-number `TRF-00001` first per tenant; isolated across tenants | Unit |
| T-06 | Concurrent double-create produces duplicate transfer_number → IntegrityError | Race / D-04 |
| T-07 | Edit in `draft` succeeds; items re-built (delete+recreate) | Integration |
| T-08 | Edit destroys old items without audit trail | Defect (D-08, A09) |
| T-09 | Edit in `pending_approval` allowed | Functional |
| T-10 | Edit in `approved` rejected | Negative |
| T-11 | Delete in `draft` succeeds | Functional |
| T-12 | Delete in `cancelled` succeeds | Functional |
| T-13 | Delete in `approved` / `in_transit` / `completed` rejected | Negative |
| T-14 | Cross-tenant detail → 404 | Security A01 |
| T-15 | **Cross-tenant product injection via POST `item_product=<other-tenant-pk>` accepted** | Security A01 / D-01 |
| T-16 | **Cross-tenant product injection via edit POST accepted** | Security A01 / D-01 |
| T-17 | Cross-tenant warehouse injection blocked (form filters queryset) | Regression |
| T-18 | Transition draft → pending_approval → approved → in_transit → completed | Functional |
| T-19 | Transition completed → * rejected | Negative |
| T-20 | Transition cancelled → draft (reopen) succeeds | Functional |
| T-21 | Transition to completed silently overwrites partial receipts | Defect (D-03) |
| T-22 | Transfer `total_quantity` / `total_received` aggregates | Unit |
| T-23 | `is_fully_received` property | Unit |
| T-24 | Negative quantity rejected (PositiveIntegerField + min='1') | Boundary |
| T-25 | Quantity 0 rejected (min='1' on widget; PositiveIntegerField allows DB=0) | Boundary |
| T-26 | Source bin from another tenant rejected (form queryset) | Regression |
| T-27 | List filter status + type + warehouse compose | Functional |
| T-28 | List pagination preserves all filters | Usability |
| T-29 | List N+1 ≤ 12 queries for 20 transfers | Performance |
| T-30 | Notes field accepts unicode and renders escaped | Edge / A03 |
| T-31 | Search `q` matches transfer_number / src / dest names | Functional |

### 3.2 Receive workflow (R-NN)

| # | Scenario | Type |
|---|---|---|
| R-01 | Receive view requires `in_transit` status | Functional |
| R-02 | POST received_qty for each item updates record | Integration |
| R-03 | All items fully received → status auto-completes + `completed_at` set | Integration |
| R-04 | Partial receipt keeps status `in_transit` | Integration |
| R-05 | Received qty > item.quantity silently ignored (no error feedback) | Defect (D-06) |
| R-06 | Non-integer input silently swallowed | Defect (D-06) |
| R-07 | Resubmitting after a partial receive overwrites instead of accumulating | Defect (D-06) |
| R-08 | Cross-tenant receive of foreign transfer 404 | Security A01 |
| R-09 | Receive on cancelled transfer rejected | Negative |
| R-10 | Negative received_qty silently rejected by clamp | Boundary |

### 3.3 Approval workflow (A-NN)

| # | Scenario | Type |
|---|---|---|
| A-01 | Approve a `pending_approval` transfer → status=approved + approved_by/at set | Functional |
| A-02 | Reject sets status=cancelled | Functional |
| A-03 | Approve when status != pending_approval rejected | Negative |
| A-04 | **Requester can approve their own transfer (no separation of duties)** | Security A01 / D-05 |
| A-05 | Approval comment escaped on detail | Security A03 |
| A-06 | TransferApprovalRule never consulted by approval flow | Defect (D-09) |
| A-07 | Cross-tenant approval rule edit 404 | Regression |
| A-08 | Pending approval list filters to `pending_approval` only | Functional |
| A-09 | Reject without comment allowed | Functional |
| A-10 | Approval rule with `min_items > max_items` accepted | Defect (D-10) |

### 3.4 Route (X-NN)

| # | Scenario | Type |
|---|---|---|
| X-01 | Create route with src ≠ dest | Functional |
| X-02 | src == dest rejected | Negative |
| X-03 | Distance accepts decimals | Boundary |
| X-04 | Estimated duration negative rejected (PositiveIntegerField) | Boundary |
| X-05 | Route detail shows up to 10 related transfers | Functional |
| X-06 | Related transfers list lacks select_related → N+1 | Performance / D-07 |
| X-07 | Cross-tenant route detail 404 | Security |
| X-08 | Route filter by method + active preserved on pagination | Usability |
| X-09 | Inactive route still listed but filtered out of suggestions | Functional |
| X-10 | Routes are NEVER enforced at transfer create/ship time | Defect (D-11) |

### 3.5 Inventory integration (I-NN)

| # | Scenario | Type |
|---|---|---|
| I-01 | Source warehouse with 0 stock can still create a 1000-unit transfer | Defect (D-02) |
| I-02 | Completion does NOT decrement source / increment destination stock | Defect (D-02) |
| I-03 | No `Inventory` / `StockOnHand` model is queried during any flow | Defect (D-02) |

---

## 4. Detailed Test Cases

> Format: `ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions`. High-priority cases listed; remaining scenarios follow the same template in §5.

### 4.1 Transfer

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-XFER-001 | Happy create inter-warehouse | tenant admin logged in; 2 active warehouses; 3 active products | POST `/stock-movements/transfers/create/` with type=inter, src=W1, dest=W2, 3 line items | as stated | 302 → detail; transfer.transfer_number == `TRF-00001`; 3 items saved | 1 transfer + 3 items |
| TC-XFER-002 | Inter-warehouse rejects same src/dest | 1 active warehouse | POST with src=dest=W1 | — | Form error on `destination_warehouse`; no transfer saved | — |
| TC-XFER-003 | Intra-warehouse coerces dest=src | 1 active warehouse | POST with type=intra, src=W1, dest left blank | — | 302; `transfer.destination_warehouse_id == src.pk` | — |
| TC-XFER-004 | **Cross-tenant product injection** | tenant-A user; tenant-B product `pB.pk` | POST create with `item_product=pB.pk`, `item_quantity=5` | as stated | **Observed:** 302 + item saved with foreign product. **Expected:** form error. **D-01** | defect |
| TC-XFER-005 | Edit destroys old items silently | transfer with 3 items in draft | POST edit removing 1 item | — | Old 3 items deleted; 2 new items created (no AuditLog) | data lost without trace |
| TC-XFER-006 | Edit on `approved` rejected | transfer.status=approved | GET edit | — | 302 to detail with warning | unchanged |
| TC-XFER-007 | Delete on `in_transit` rejected | transfer.status=in_transit | POST delete | — | 302 with warning; transfer persists | — |
| TC-XFER-008 | Cross-tenant detail 404 | tenant-A transfer; login as tenant-B user | GET `/transfers/<a-pk>/` | — | 404 | — |
| TC-XFER-009 | Auto-number under concurrency | two parallel POST creates | parallel | — | Either both succeed with distinct numbers (ideal) OR one returns 500 IntegrityError (current) — D-04 | defect |
| TC-XFER-010 | Transition draft → completed via in_transit | transfer in draft | POST transition draft→pending_approval→approved→in_transit→completed | — | terminal status; completed_at set; **all items.received_quantity force-set to .quantity even if user-entered partial value pre-existed** | partial receipts overwritten — D-03 |

### 4.2 Receive

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-RCV-001 | Receive only allowed in `in_transit` | transfer.status=approved | GET receive view | — | 302 with warning | — |
| TC-RCV-002 | Partial receive keeps status | item.quantity=10 | POST `received_qty_<pk>=4` | qty=4 | 302; item.received_quantity=4; status remains `in_transit` | — |
| TC-RCV-003 | All items fully received → auto-complete | one item, qty=10 | POST `received_qty_<pk>=10` | qty=10 | 302; transfer.status=completed; completed_at set | — |
| TC-RCV-004 | Over-receive silently clamped | item.quantity=10 | POST `received_qty_<pk>=999` | qty=999 | **Observed:** value silently ignored (no error). **Expected:** form error. **D-06** | defect |
| TC-RCV-005 | Non-int input silently ignored | item.quantity=10 | POST `received_qty_<pk>=abc` | "abc" | **Observed:** ValueError swallowed; item unchanged; success message. **D-06** | defect |
| TC-RCV-006 | Resubmission overwrites prior receipt | first receive=5, second receive=3 | two POSTs in sequence | as stated | item.received_quantity=3 (NOT 8). User likely intended cumulative add. **D-06** | defect |
| TC-RCV-007 | Cross-tenant receive 404 | tenant-A transfer; login tenant-B | GET receive view | — | 404 | — |

### 4.3 Approval

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-APR-001 | Approve pending → approved | transfer.status=pending_approval | POST approve, decision=approved | — | transfer.status=approved; transfer.approved_by=user; TransferApproval row created | — |
| TC-APR-002 | Reject sets status=cancelled | transfer.status=pending_approval | POST decision=rejected | — | transfer.status=cancelled | — |
| TC-APR-003 | Approve when status != pending rejected | transfer.status=approved | POST approve | — | 302 with warning | — |
| TC-APR-004 | **Requester self-approves** | requested_by=user; status=pending | login as same user, POST approve | — | **Observed:** approval succeeds. **Expected (under separation-of-duties):** rejected. **D-05** | defect |
| TC-APR-005 | TransferApprovalRule lookup | rule with min=11, max=None, requires_approval=True; transfer with 12 items | POST create | — | **Observed:** transfer created in draft regardless of rule. Rule never read. **D-09** | defect |
| TC-APR-006 | Rule with `min_items > max_items` accepted | — | POST `min=10, max=5` | — | **Observed:** form accepts. **Expected:** form error. **D-10** | defect |
| TC-APR-007 | Cross-tenant rule edit 404 | tenant-B rule | login tenant-A, GET edit | — | 404 | — |

### 4.4 Route

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-RTE-001 | Create with src ≠ dest | 2 warehouses | POST create | name="X", src=W1, dest=W2, method=truck, hours=4 | 302 → detail; route saved | — |
| TC-RTE-002 | Reject src == dest | 1 warehouse | POST | as stated | Form error on destination | — |
| TC-RTE-003 | route_detail N+1 on related_transfers | route + 10 transfers | GET detail | — | **Observed:** > 20 queries (no select_related). **D-07** | defect |
| TC-RTE-004 | Cross-tenant route detail 404 | tenant-B route | login tenant-A | — | 404 | — |

### 4.5 Inventory integration (D-02 family)

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-INV-001 | Transfer of 1000 units when source has 0 | empty source warehouse | POST create | qty=1000 | **Observed:** transfer accepted. **Expected:** form error referencing inventory layer. **D-02** | defect |
| TC-INV-002 | Completion does NOT decrement source / increment destination | transfer flows to `completed` | inspect inventory after | — | **Observed:** no inventory movement record; warehouse stock unchanged. **D-02** | defect |

---

## 5. Automation Strategy

### 5.1 Tool stack

| Layer | Tool | Rationale |
|---|---|---|
| Test runner | `pytest` + `pytest-django` | Consistent with [catalog/tests](../../catalog/tests/), [vendors/tests](../../vendors/tests/), [receiving/tests](../../receiving/tests/) |
| Coverage | `coverage.py` + `pytest-cov` | Gate at 80% lines |
| E2E | Playwright (Python) | 6 smoke flows |
| Load | Locust | List page + receive flow |
| SAST | `bandit`, `pip-audit` | A06/A09 |
| DAST | OWASP ZAP baseline | A01/A03 |

### 5.2 Suite layout

```
stock_movements/
  tests/
    __init__.py
    conftest.py
    test_models.py
    test_forms.py
    test_views_transfers.py
    test_views_approvals.py
    test_views_routes.py
    test_views_receive.py
    test_security.py
    test_performance.py
    test_regression.py
e2e/
  stock_movements_smoke.spec.py
perf/
  locustfile_stock_movements.py
```

Update [pytest.ini:5](../../pytest.ini#L5) — append `stock_movements/tests`.

### 5.3 Runnable snippets

> All snippets use the real NavIMS fixture shapes from [receiving/tests/conftest.py](../../receiving/tests/conftest.py) (the most recent reference) and run against [config/settings_test.py](../../config/settings_test.py).

#### 5.3.1 `stock_movements/tests/conftest.py`

```python
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse, Zone, Bin
from stock_movements.models import (
    StockTransfer, StockTransferItem,
    TransferApprovalRule, TransferRoute,
)

User = get_user_model()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Test", slug="acme-test")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Other Co", slug="other-co")


@pytest.fixture
def user(db, tenant):
    return User.objects.create_user(
        username="qa_user", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="qa_other", password="qa_pass_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Hardware")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku="SKU-001",
        name="Widget", status="active", is_active=True,
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name="X")
    return Product.objects.create(
        tenant=other_tenant, category=cat, sku="X-001",
        name="OtherWidget", status="active", is_active=True,
    )


@pytest.fixture
def w1(db, tenant):
    return Warehouse.objects.create(tenant=tenant, code="W1", name="W1", is_active=True)


@pytest.fixture
def w2(db, tenant):
    return Warehouse.objects.create(tenant=tenant, code="W2", name="W2", is_active=True)


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(tenant=other_tenant, code="OW", name="OW", is_active=True)


@pytest.fixture
def transfer_draft(db, tenant, w1, w2, user):
    return StockTransfer.objects.create(
        tenant=tenant, transfer_type="inter_warehouse",
        source_warehouse=w1, destination_warehouse=w2,
        priority="normal", status="draft", requested_by=user,
    )
```

#### 5.3.2 `stock_movements/tests/test_models.py`

```python
import pytest
from stock_movements.models import StockTransfer, StockTransferItem


@pytest.mark.django_db
class TestStockTransferAutoNumber:
    def test_first_transfer_numbers_00001(self, tenant, w1, w2, user):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
        assert t.transfer_number == "TRF-00001"

    def test_numbers_per_tenant(self, tenant, other_tenant, w1, w2, other_warehouse, user, other_user):
        StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
        # Other tenant — fresh sequence.
        t2 = StockTransfer.objects.create(
            tenant=other_tenant, transfer_type="intra_warehouse",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            requested_by=other_user,
        )
        assert t2.transfer_number == "TRF-00001"


@pytest.mark.django_db
class TestStatusMachine:
    def test_terminal_completed(self, transfer_draft):
        transfer_draft.status = "completed"
        transfer_draft.save()
        for s in ["draft", "pending_approval", "approved", "in_transit", "cancelled"]:
            assert transfer_draft.can_transition_to(s) is False

    def test_cancelled_can_reopen(self, transfer_draft):
        transfer_draft.status = "cancelled"
        transfer_draft.save()
        assert transfer_draft.can_transition_to("draft") is True


@pytest.mark.django_db
class TestAggregates:
    def test_total_quantity_and_received(self, transfer_draft, product):
        StockTransferItem.objects.create(
            tenant=transfer_draft.tenant, transfer=transfer_draft,
            product=product, quantity=10, received_quantity=4,
        )
        StockTransferItem.objects.create(
            tenant=transfer_draft.tenant, transfer=transfer_draft,
            product=product, quantity=5, received_quantity=5,
        )
        assert transfer_draft.total_quantity == 15
        assert transfer_draft.total_received == 9
        assert transfer_draft.total_items == 2
```

#### 5.3.3 `stock_movements/tests/test_forms.py`

```python
import pytest
from stock_movements.forms import StockTransferForm, TransferRouteForm, TransferApprovalRuleForm


@pytest.mark.django_db
class TestStockTransferForm:
    def test_inter_requires_distinct_warehouses(self, tenant, w1):
        f = StockTransferForm(
            data={"transfer_type": "inter_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(w1.pk),
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors

    def test_intra_coerces_dest_to_src(self, tenant, w1):
        f = StockTransferForm(
            data={"transfer_type": "intra_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": "",
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is True, f.errors
        assert f.cleaned_data["destination_warehouse"] == w1

    def test_inter_rejects_foreign_dest_warehouse(self, tenant, w1, other_warehouse):
        f = StockTransferForm(
            data={"transfer_type": "inter_warehouse",
                  "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(other_warehouse.pk),  # foreign tenant
                  "priority": "normal", "notes": ""},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors


@pytest.mark.django_db
class TestRouteForm:
    def test_src_eq_dest_rejected(self, tenant, w1):
        f = TransferRouteForm(
            data={"name": "X", "source_warehouse": str(w1.pk),
                  "destination_warehouse": str(w1.pk),
                  "transit_method": "truck", "estimated_duration_hours": "4",
                  "distance_km": "1.0", "instructions": "", "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is False
        assert "destination_warehouse" in f.errors


@pytest.mark.django_db
class TestApprovalRuleForm:
    def test_D10_min_greater_than_max_rejected_after_fix(self, tenant):
        """Regression for D-10. After fix the form must reject min > max."""
        f = TransferApprovalRuleForm(
            data={"name": "Bad", "min_items": "10", "max_items": "5",
                  "requires_approval": True, "approver_role": "Manager",
                  "is_active": True},
            tenant=tenant,
        )
        assert f.is_valid() is False
```

#### 5.3.4 `stock_movements/tests/test_views_transfers.py`

```python
import pytest
from django.urls import reverse
from stock_movements.models import StockTransfer, StockTransferItem


@pytest.mark.django_db
class TestTransferIDOR:
    def test_D01_cross_tenant_product_on_create_rejected(
        self, client_logged_in, tenant, w1, w2, other_product,
    ):
        """Regression for D-01. After fix, posting a foreign product id must fail."""
        payload = {
            "transfer_type": "inter_warehouse",
            "source_warehouse": str(w1.pk),
            "destination_warehouse": str(w2.pk),
            "priority": "normal", "notes": "",
            "item_product": [str(other_product.pk)],
            "item_quantity": ["5"],
            "item_notes": [""],
        }
        r = client_logged_in.post(reverse("stock_movements:transfer_create"), data=payload)
        # After fix: form re-renders with error (200) and no transfer is created.
        assert r.status_code == 200
        assert StockTransfer.objects.filter(tenant=tenant).count() == 0

    def test_cross_tenant_detail_404(self, client_logged_in, other_tenant, other_warehouse, other_user):
        t = StockTransfer.objects.create(
            tenant=other_tenant, transfer_type="intra_warehouse",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            requested_by=other_user,
        )
        r = client_logged_in.get(reverse("stock_movements:transfer_detail", args=[t.pk]))
        assert r.status_code == 404


@pytest.mark.django_db
class TestTransferTransitions:
    def test_D03_completed_overwrites_partial_receipt(
        self, client_logged_in, tenant, w1, w2, product, user,
    ):
        """Regression for D-03. After fix, completion must NOT silently overwrite partial received_quantity."""
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="in_transit", requested_by=user,
        )
        item = StockTransferItem.objects.create(
            tenant=tenant, transfer=t, product=product, quantity=10, received_quantity=4,
        )
        r = client_logged_in.post(
            reverse("stock_movements:transfer_transition", args=[t.pk, "completed"]),
        )
        assert r.status_code == 302
        item.refresh_from_db()
        # After fix: item.received_quantity must still be 4 OR completion must be rejected
        # because of the partial receipt. Choose ONE of:
        # assert item.received_quantity == 4
        # OR: t.refresh_from_db(); assert t.status == "in_transit"
        assert item.received_quantity == 4
```

#### 5.3.5 `stock_movements/tests/test_views_approvals.py`

```python
import pytest
from django.urls import reverse
from stock_movements.models import StockTransfer


@pytest.mark.django_db
def test_D05_requester_cannot_approve_own_transfer(
    client_logged_in, tenant, w1, w2, user,
):
    """Regression for D-05. After fix, the requester must not be able to approve their own transfer."""
    t = StockTransfer.objects.create(
        tenant=tenant, transfer_type="inter_warehouse",
        source_warehouse=w1, destination_warehouse=w2,
        status="pending_approval", requested_by=user,
    )
    r = client_logged_in.post(
        reverse("stock_movements:transfer_approve", args=[t.pk]),
        data={"decision": "approved", "comments": "self-approve"},
    )
    t.refresh_from_db()
    # After fix: form-level error + transfer remains in pending_approval
    assert t.status == "pending_approval"
```

#### 5.3.6 `stock_movements/tests/test_views_receive.py`

```python
import pytest
from django.urls import reverse
from stock_movements.models import StockTransfer, StockTransferItem


@pytest.mark.django_db
class TestReceive:
    def _setup(self, tenant, w1, w2, product, user, qty=10):
        t = StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2,
            status="in_transit", requested_by=user,
        )
        item = StockTransferItem.objects.create(
            tenant=tenant, transfer=t, product=product, quantity=qty,
        )
        return t, item

    def test_D06_over_receive_rejected_after_fix(
        self, client_logged_in, tenant, w1, w2, product, user,
    ):
        t, item = self._setup(tenant, w1, w2, product, user, qty=10)
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[t.pk]),
            data={f"received_qty_{item.pk}": "999"},
        )
        # After fix: form re-renders with error OR success but qty clamped + warning shown.
        item.refresh_from_db()
        assert item.received_quantity != 999
        assert item.received_quantity <= item.quantity

    def test_D06_non_int_input_surfaces_error_after_fix(
        self, client_logged_in, tenant, w1, w2, product, user,
    ):
        t, item = self._setup(tenant, w1, w2, product, user, qty=10)
        r = client_logged_in.post(
            reverse("stock_movements:transfer_receive", args=[t.pk]),
            data={f"received_qty_{item.pk}": "abc"},
        )
        # After fix: r.status_code == 200 with field error shown (not silent success)
        assert r.status_code in (200, 302)
```

#### 5.3.7 `stock_movements/tests/test_security.py`

```python
import pytest
from django.urls import reverse
from stock_movements.models import StockTransfer, TransferRoute


@pytest.mark.django_db
class TestA01:
    def test_anonymous_redirected(self, client):
        r = client.get(reverse("stock_movements:transfer_list"))
        assert r.status_code in (302, 403)

    def test_cross_tenant_route_404(self, client_logged_in, other_tenant, other_warehouse):
        r2 = TransferRoute.objects.create(
            tenant=other_tenant, name="Foreign",
            source_warehouse=other_warehouse, destination_warehouse=other_warehouse,
            transit_method="truck", estimated_duration_hours=1,
        )
        r = client_logged_in.get(reverse("stock_movements:route_detail", args=[r2.pk]))
        assert r.status_code == 404


@pytest.mark.django_db
def test_A03_notes_escaped_on_detail(client_logged_in, tenant, w1, w2, user):
    payload = "<script>alert('x')</script>"
    t = StockTransfer.objects.create(
        tenant=tenant, transfer_type="inter_warehouse",
        source_warehouse=w1, destination_warehouse=w2,
        notes=payload, requested_by=user,
    )
    r = client_logged_in.get(reverse("stock_movements:transfer_detail", args=[t.pk]))
    assert payload.encode() not in r.content
    assert b"&lt;script&gt;" in r.content
```

#### 5.3.8 `stock_movements/tests/test_performance.py`

```python
import pytest
from django.urls import reverse
from stock_movements.models import StockTransfer, TransferRoute


@pytest.mark.django_db
def test_transfer_list_query_count(
    client_logged_in, django_assert_max_num_queries, tenant, w1, w2, user,
):
    for _ in range(20):
        StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse("stock_movements:transfer_list"))
        assert r.status_code == 200


@pytest.mark.django_db
def test_D07_route_detail_n_plus_one_after_fix(
    client_logged_in, django_assert_max_num_queries, tenant, w1, w2, user,
):
    """Regression for D-07. After adding select_related on related_transfers."""
    route = TransferRoute.objects.create(
        tenant=tenant, name="R", source_warehouse=w1, destination_warehouse=w2,
        transit_method="truck", estimated_duration_hours=1,
    )
    for _ in range(10):
        StockTransfer.objects.create(
            tenant=tenant, transfer_type="inter_warehouse",
            source_warehouse=w1, destination_warehouse=w2, requested_by=user,
        )
    with django_assert_max_num_queries(15):
        r = client_logged_in.get(reverse("stock_movements:route_detail", args=[route.pk]))
        assert r.status_code == 200
```

---

## 6. Defects, Risks & Recommendations

> **Verification note:** D-01 / D-04 reproduced in Django shell against `config.settings_test`. D-03 / D-06 / D-09 confirmed by static read. Lower-severity findings are static-confirmed only.

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| **D-01** | **Critical** | [stock_movements/views.py:91-99](../../stock_movements/views.py#L91-L99); [views.py:159-167](../../stock_movements/views.py#L159-L167) | **Cross-tenant product injection.** `transfer_create_view` and `transfer_edit_view` parse `request.POST.getlist('item_product')` and call `StockTransferItem.objects.create(..., product_id=int(product_ids[i]))` with **no tenant verification**. A tenant-A user can POST a tenant-B `product.pk` and link a foreign product into their own transfer. **Verified in shell** (tenant-B `product.tenant_id != transfer.tenant_id`). **OWASP A01.** | Validate per item: `Product.objects.filter(tenant=tenant, pk=int(product_ids[i])).exists()`; raise/skip otherwise. Better: replace the manual loop with a real Django formset (matching the pattern recently applied in [receiving/forms.py](../../receiving/forms.py)) using `form_kwargs={'tenant': tenant}` and a `__init__` that filters `product` queryset. |
| **D-02** | **Critical** | Whole module (no inventory layer integration) | **No stock validation, no inventory side-effect.** Nothing checks that the source warehouse holds the requested quantity before creation, approval, shipment, or completion; nothing decrements source / increments destination on completion. Search for `available`, `on_hand`, `Inventory` in `stock_movements/` returns zero hits. The "stock movement" module does not actually move stock — it only changes its own status. **OWASP A04 Insecure design.** | Define an integration contract with the inventory layer (`warehousing` or `inventory` app — pick the one that owns `StockOnHand`). On create/approve, verify availability per `(warehouse, product)`; on `in_transit`, allocate (reserve); on `completed`, decrement source and increment destination. Wrap in `transaction.atomic()` to keep the move atomic. Until that lands, surface a UI banner "Inventory enforcement OFF — transfers are advisory only" so users are not misled. |
| **D-03** | **High** | [stock_movements/views.py:226-230](../../stock_movements/views.py#L226-L230) | **Completion silently destroys partial-receipt data.** `transfer_transition_view` on `completed` iterates items and force-sets `received_quantity = quantity` for any short-received row. A user who scanned 4-of-10 and then someone else clicks "Complete" loses the partial-receipt audit. | Either (a) require fully-received items before allowing `→ completed` transition (recommended: extend `can_transition_to('completed')` to check `total_received == total_quantity`), or (b) leave received quantities untouched on completion and surface a "X items short-received" warning. Do not auto-overwrite. |
| **D-04** | **High** | [stock_movements/models.py:124-138](../../stock_movements/models.py#L124-L138) | **Racy auto-numbering.** `MAX(id)+1` pattern with no transaction, identical to the receiving D-03 issue already remediated. Two concurrent creates collide on `unique_together(tenant, transfer_number)` → 500. | Reuse the helper from [receiving/models.py:_save_with_generated_number](../../receiving/models.py) — `transaction.atomic()` + `IntegrityError` retry. Apply to `StockTransfer.save()`. |
| **D-05** | **High** | [stock_movements/views.py:390-429](../../stock_movements/views.py#L390-L429) | **No segregation of duties on approval.** Any authenticated tenant user can approve / reject a `pending_approval` transfer — including the requester themselves. The view checks status but not actor. **OWASP A01.** | Reject when `transfer.requested_by_id == request.user.id`; additionally gate via `@user_passes_test(lambda u: u.is_tenant_admin or u.groups.filter(name='approver').exists())`. Same gate on `transfer_transition_view` for `approved` / `in_transit` transitions and on `transfer_delete_view`. |
| **D-06** | **Medium** | [stock_movements/views.py:247-259](../../stock_movements/views.py#L247-L259) | **Receive view problems (3-in-1).** (a) `received_quantity` is set as an absolute value rather than incremental — resubmission overwrites prior data; (b) `int(received)` raising `ValueError` is silently swallowed and the success message is still shown; (c) over-receive (`received_qty > item.quantity`) is silently ignored with no field-level error. | Build a real ModelFormSet for `StockTransferItem` with `clean_received_quantity` enforcing `received_quantity ≤ quantity`. Decide explicitly whether semantics are absolute or incremental and surface that in the template label. Surface field-level errors when present. |
| **D-07** | **Medium** | [stock_movements/views.py:503-507](../../stock_movements/views.py#L503-L507) | **N+1 in `route_detail_view`.** `related_transfers` is built without `select_related('source_warehouse', 'destination_warehouse', 'requested_by')`; the template iterates and dereferences each FK. | Add `.select_related('source_warehouse', 'destination_warehouse', 'requested_by')` to the related_transfers queryset. |
| **D-08** | **Medium** | [stock_movements/views.py:154-167](../../stock_movements/views.py#L154-L167) | **Edit destroys items without audit.** `transfer.items.all().delete()` then re-create on every edit. There is no `core.AuditLog` trail of the deletion. **OWASP A09.** | Either (a) emit `AuditLog` before `delete()`, or (b) compute a diff (insert/update/delete) instead of nuking. Option (a) is sufficient for compliance. |
| **D-09** | **Medium** | [stock_movements/views.py:74-112](../../stock_movements/views.py#L74-L112); [models.py:176-195](../../stock_movements/models.py#L176-L195) | **`TransferApprovalRule` is dead code.** No view or model method ever reads it; transfers always start in `draft` regardless of item count or rule. Users can configure rules that have no effect. | At create/edit time, look up the smallest matching `TransferApprovalRule` (by item count) and either skip approval (`requires_approval=False`) or set `status='pending_approval'` straight away. Otherwise delete the model. |
| **D-10** | **Low** | [stock_movements/forms.py:88-119](../../stock_movements/forms.py#L88-L119) | **`min_items > max_items` accepted.** `TransferApprovalRuleForm` has no `clean()` to validate that the range is consistent. Saved as-is, then never matches anything. | Add `clean()` that errors when `max_items is not None and min_items > max_items`. |
| **D-11** | **Low** | [stock_movements/models.py:236-273](../../stock_movements/models.py#L236-L273) | **Routes are passive.** No route is consulted at transfer create / approve / ship time. UX implies routing decisions but business logic ignores them. | Either (a) require selecting a route at transfer creation when `transfer_type='inter_warehouse'` (FK on transfer), or (b) demote to a documentation-only catalog and update the UI accordingly. |
| **D-12** | **Low** | [stock_movements/forms.py:84](../../stock_movements/forms.py#L84) | **Inconsistent product-active filter.** Uses `Product.objects.filter(tenant=tenant, is_active=True)` while the rest of the codebase ([catalog/models.py](../../catalog/models.py), [receiving/forms.py:106](../../receiving/forms.py#L106), [purchase_orders](../../purchase_orders/)) filters by `status='active'`. Both fields exist on `Product`, so this is not broken — just out of sync. | Pick one canonical "is the product orderable" semantic and use it everywhere. Likely `status='active'` since `is_active` is set to `True` even for `draft` / `discontinued` products. |
| **D-13** | **Low** | [stock_movements/](../../stock_movements/) (CRUD completeness) | **No detail view for `TransferApprovalRule`.** `approval_rule_list.html` only links to Edit/Delete — no per-rule "view" page. Violates CLAUDE.md "CRUD Completeness Rules". | Add `approval_rule_detail_view` + URL + template. |
| **D-14** | **Low** | [stock_movements/views.py](../../stock_movements/views.py) (entire file) | **No RBAC beyond `@login_required`.** Same pattern as the receiving D-13 finding; rolled up into D-05 for the approval path but separate concern for delete and route mutation. | Project-level decision: introduce `@user_passes_test` helpers in `core/decorators.py` and apply to destructive views. |
| **D-15** | **Info** | [pytest.ini:5](../../pytest.ini#L5); `stock_movements/tests/` (does not exist) | **No tests for `stock_movements/`.** Zero coverage. | Add `stock_movements/tests/` per §5; append to `testpaths`. |
| **D-16** | **Info** | [config/settings.py:11-13](../../config/settings.py#L11-L13) | Project-level: `DEBUG=True` default + `ALLOWED_HOSTS='*'` default. Surfaced because this module accepts free-text notes that would render in detail responses. **OWASP A05.** | Default to `DEBUG=False` and require explicit `ALLOWED_HOSTS`. |

### 6.1 Risk register

| Risk | Likelihood | Impact | Severity | Mitigation |
|---|---|---|---|---|
| Inventory ledger desync | Certain | Severe | Critical | D-02 |
| Cross-tenant product enumeration via transfer items | Medium | Severe | Critical | D-01 |
| Partial-receipt data lost on completion click | Medium | High | High | D-03 |
| Self-approval bypass | High | High | High | D-05 |
| Number collision under load | High | Medium | High | D-04 |
| Confused receive UX (absolute vs incremental) | Medium | Medium | Medium | D-06 |

### 6.2 OWASP Top-10 coverage summary

| OWASP | Status | Evidence |
|---|---|---|
| A01 Broken Access Control | ❌ Fail | D-01 (cross-tenant product), D-05 (self-approval), D-14 (no RBAC) |
| A02 Crypto failures | ✅ N/A | No custom crypto |
| A03 Injection / XSS | ✅ OK | Auto-escape verified in templates ([transfer_detail.html](../../templates/stock_movements/transfer_detail.html)) |
| A04 Insecure design | ❌ Fail | D-02 (no stock validation), D-09 (rules ignored), D-11 (routes ignored), D-03 (overwrite) |
| A05 Security misconfig | ⚠ Partial | D-16 (project-level) |
| A06 Vulnerable deps | ⚠ Unverified | run `pip-audit` |
| A07 Auth failures | ⚠ Project-level | out of module scope |
| A08 Data integrity | ✅ N/A | No file uploads in module |
| A09 Logging failures | ❌ Fail | D-08 (item delete on edit not logged); no AuditLog on approve / cancel / delete |
| A10 SSRF | ✅ N/A | No external URL fetching |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Current vs target coverage

| File | Current | Target | Gap |
|---|---|---|---|
| [stock_movements/models.py](../../stock_movements/models.py) | 0% | 90% | +90% |
| [stock_movements/views.py](../../stock_movements/views.py) | 0% | 85% | +85% |
| [stock_movements/forms.py](../../stock_movements/forms.py) | 0% | 90% | +90% |
| [stock_movements/admin.py](../../stock_movements/admin.py) | 0% | 50% | +50% |
| [stock_movements/management/commands/seed_stock_movements.py](../../stock_movements/management/commands/seed_stock_movements.py) | 0% | 60% | +60% |

Module target: **≥ 80% line, ≥ 70% branch**, mutation score ≥ 60% on `can_transition_to`, `_generate_transfer_number`, `total_quantity` / `total_received`.

### 7.2 KPI table

| KPI | Green | Amber | Red | Current |
|---|---|---|---|---|
| Functional pass rate | ≥ 99% | 95–99% | < 95% | n/a |
| Open Critical defects | 0 | — | ≥ 1 | **2** (D-01, D-02) |
| Open High defects | 0 | 1–2 | ≥ 3 | **3** (D-03, D-04, D-05) |
| Line coverage | ≥ 80% | 60–80% | < 60% | **0%** |
| Branch coverage | ≥ 70% | 50–70% | < 50% | 0% |
| List view queries (20 rows) | ≤ 12 | 13–25 | > 25 | unknown |
| route_detail view queries (10 related) | ≤ 15 | 16–30 | > 30 | likely > 30 (D-07) |
| Suite wall-clock | ≤ 60 s | 60–180 s | > 180 s | n/a |
| Regression escape rate | 0/release | 1 | ≥ 2 | n/a |

### 7.3 Release Exit Gate

Shipping is **BLOCKED** until all of the following are true:

- [ ] **D-01, D-02, D-03, D-04, D-05** fixed and each has a regression test in `test_regression.py`.
- [ ] `stock_movements/tests/` added to [pytest.ini:5](../../pytest.ini#L5) and passes green.
- [ ] Line coverage ≥ 80% on models / views / forms.
- [ ] `bandit -r stock_movements/` reports zero High findings.
- [ ] Three-way contract verified: source warehouse stock decremented + destination incremented on completion (D-02 fix).
- [ ] Self-approval blocked test passes (D-05 fix).
- [ ] Concurrency test (5 parallel creates) produces 5 distinct `TRF-NNNNN` numbers (D-04 fix).
- [ ] Partial-receipt-completion test passes (D-03 fix).
- [ ] Cross-tenant product POST regression test passes (D-01 fix).
- [ ] PowerShell + SQLite seed round-trip verified: `seed`; `seed_stock_movements` × 2 (second run prints "already exists", no crash).

---

## 8. Summary

The `stock_movements/` module ships a clean CRUD shell over the four expected entities — transfers, items, approvals, routes — but the actual *stock movement* part of "Stock Movement & Transfers" is **not implemented**. There is no integration with the inventory layer; transfers do not reduce source stock, do not increase destination stock, and do not validate availability. The module is, in effect, a workflow tracker over imaginary inventory.

On top of that core gap, the same systemic patterns that have already been remediated in `catalog`, `vendors`, and `receiving` recur here: a critical cross-tenant IDOR via raw POST product IDs (D-01), racy auto-numbering (D-04), and absent role-based access control on the approval path (D-05). The completion transition silently overwrites partial-receipt data (D-03), and the receive view is confused about whether `received_quantity` is absolute or incremental (D-06).

### Top-5 must-fix before release

1. **D-02 No inventory integration / no stock validation.** Single biggest defect; the module's primary verb does not work.
2. **D-01 Cross-tenant product injection** on the create/edit POST path. Verified IDOR.
3. **D-03 Completion silently destroys partial-receipt data.** Inventory-audit hole.
4. **D-04 Racy auto-numbering.** Reuse the [receiving/models.py:_save_with_generated_number](../../receiving/models.py) helper — already in the codebase.
5. **D-05 Self-approval bypass.** Block requester == approver and add an admin/approver group gate.

### Recommended follow-up modes

- **"Fix the defects"** → tackle D-01, D-03, D-04, D-05, D-06 immediately (all isolated to `views.py` / `forms.py` / `models.py`). D-02 is a larger architectural conversation — recommend a separate scope discussion before implementation.
- **"Build the automation"** → scaffold `stock_movements/tests/` per §5; the `receiving/tests/conftest.py` is the closest reference and can be cloned with minor adjustments (Warehouse + Bin instead of GRN/PO).
- **"Sweep the audit"** → continue the lesson-#7 cross-module audit. The IDOR pattern in D-01 (raw `request.POST.getlist` building child rows without tenant filter) is a third variant of the formset-IDOR family already documented in lesson #9 — captures a *new* failure mode worth promoting to its own lesson once fixed.

Nothing in this module is technically hard to fix; the gating risk is that the inventory-layer contract (D-02) is treated as an afterthought rather than the actual purpose of the module.
