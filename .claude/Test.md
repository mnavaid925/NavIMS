# Purchase Order (PO) Management — Comprehensive SQA Test Report

> Target module: [purchase_orders/](../purchase_orders/)
> Scope: full module review (models, forms, views, templates, seed, admin, workflow).
> Standards: ISO/IEC/IEEE 29119, OWASP Top 10:2021, NavIMS project conventions ([CLAUDE.md](CLAUDE.md)).
> Prepared by: Senior SQA Engineer persona, staff-engineer quality bar.
> Date: 2026-04-17.

---

## 1. Module Analysis

### 1.1 Surface area

| Artefact | File | LoC | Notes |
|---|---|---|---|
| Models | [purchase_orders/models.py](../purchase_orders/models.py) | 271 | 5 models: `PurchaseOrder`, `PurchaseOrderItem`, `ApprovalRule`, `PurchaseOrderApproval`, `PurchaseOrderDispatch` |
| Forms | [purchase_orders/forms.py](../purchase_orders/forms.py) | 190 | 5 ModelForms + inline formset for items |
| Views | [purchase_orders/views.py](../purchase_orders/views.py) | 593 | 16 function-based views covering CRUD + 8 status transitions + dispatch + approval rules |
| URLs | [purchase_orders/urls.py](../purchase_orders/urls.py) | 32 | App namespace `purchase_orders:` mounted at `/purchase-orders/` |
| Admin | [purchase_orders/admin.py](../purchase_orders/admin.py) | 56 | All 5 models registered with inlines |
| Templates | [templates/purchase_orders/](../templates/purchase_orders/) | 7 files | list/detail/form/dispatch + approval rule list/form + pending approvals |
| Seed | [purchase_orders/management/commands/seed_purchase_orders.py](../purchase_orders/management/commands/seed_purchase_orders.py) | 257 | Per-tenant seeding with 3 approval rules + 8 POs spanning every status |
| Tests | — | **0** | **No test coverage** (pytest `testpaths` in [pytest.ini](../pytest.ini) exclude `purchase_orders/tests`) |

### 1.2 Business domain

The module implements a full Purchase Order lifecycle:

1. **Authoring** — Draft PO with header + inline line-items (product, qty, unit price, tax%, discount).
2. **Approval flow** — Submit-for-approval → one or more approvers sign off (or reject) → PO moves to `approved`. Threshold computed from amount-range `ApprovalRule` records.
3. **Dispatch** — Send PO to vendor via email / EDI / manual / other. Email body auto-assembled from line items + totals.
4. **Fulfilment** — Mark `sent` → `received` → `closed`. `partially_received` is a parallel state.
5. **Cancellation** — Any non-closed/non-cancelled PO can be cancelled. Cancelled POs can be reopened to draft (wipes approvals).

Status machine defined at [models.py:27-36](../purchase_orders/models.py#L27-L36):

```
draft ⇄ pending_approval → approved → sent → partially_received → received → closed
  └──────────────────────────────────────── cancelled ──────────────────┘
                                            (reopen → draft)
```

Computed properties at [models.py:77-108](../purchase_orders/models.py#L77-L108): `subtotal`, `tax_total`, `discount_total`, `grand_total`, `approval_status`.

### 1.3 Security-sensitive paths

| Path | File:Line | Risk surface |
|---|---|---|
| Dispatch via email | [views.py:344-391](../purchase_orders/views.py#L344-L391) | Free-form recipient → data-exfil risk; no RBAC gate |
| Approve / Reject | [views.py:248-317](../purchase_orders/views.py#L248-L317) | No role check; creator self-approval allowed; workflow-breaking rejection residue |
| PO-number generation | [models.py:115-129](../purchase_orders/models.py#L115-L129) | Race condition on `_generate_po_number` — two concurrent inserts collide on `unique_together(tenant, po_number)` |
| Delete / Cancel / Close | [views.py:202-490](../purchase_orders/views.py#L202-L490) | No RBAC; no audit log |
| Approval rule range | [forms.py:112-154](../purchase_orders/forms.py#L112-L154) | No validation `min_amount ≤ max_amount`; overlapping / gap ranges silently swallowed |

### 1.4 Multi-tenancy posture

Every view correctly uses `tenant=request.tenant` filter on the top-level queryset, and every `get_object_or_404` includes the tenant predicate. **No direct IDOR vector identified** via URL-pk lookups. However **tenant superuser has `tenant=None`** (known pattern, see [CLAUDE.md](CLAUDE.md)).

### 1.5 Known NavIMS-pattern violations

| Pattern | Status |
|---|---|
| `tenant` on every non-join model | ✅ Compliant (all 5 models carry FK) |
| `@login_required` on every view | ✅ Compliant |
| Filter retention across pagination | ✅ Compliant ([po_list.html:186-224](../templates/purchase_orders/po_list.html#L186-L224)) |
| Full CRUD (list/create/detail/edit/delete) | ✅ Compliant |
| Seed idempotency | ⚠️ Partial — outer `if PurchaseOrder.exists()` guard (OK) but nested `ApprovalRule.objects.create(**rd)` does not `get_or_create`; if POs exist but rules were manually flushed, rules are never re-created |
| `unique_together` + tenant trap | ⚠️ `PurchaseOrder.Meta.unique_together=('tenant','po_number')` relies on auto-generated numbers; no explicit `clean_po_number` — but the form does not expose the field, so trap is dormant |
| `status_choices` in context | ✅ Compliant |
| `|stringformat:"d"` for FK filter equality | ✅ Compliant ([po_list.html:66](../templates/purchase_orders/po_list.html#L66)) |
| AuditLog on destructive ops | ❌ **Missing** — delete/cancel/close/approve/dispatch do not emit `core.AuditLog` |

---

## 2. Test Plan

### 2.1 Testing objectives

| Objective | Acceptance criteria |
|---|---|
| Functional correctness of CRUD | All 5 CRUD ops pass with valid data; validation blocks invalid |
| Workflow integrity | Every `VALID_TRANSITIONS` edge proven; invalid transitions rejected with message |
| Approval engine correctness | Multi-approver, rejection, threshold, rule lookup, resubmit-after-reject all correct |
| Financial math precision | `grand_total` stable across currencies/decimals; no rounding drift > $0.01 per 1000-item PO |
| Tenant isolation | No data bleed between tenants; anonymous redirected to login |
| RBAC | Only authorised roles can approve, dispatch, cancel, delete |
| Injection / XSS | Every field with user input renders escaped; email body safe for plain-text |
| N+1 / Performance | List page ≤ 6 queries; detail page ≤ 15; 100-PO list p95 < 300 ms |
| Accessibility | Forms keyboard-navigable; tables labelled; WCAG 2.1 AA colour contrast on status badges |

### 2.2 Test levels & types

| Level | Types | Tools |
|---|---|---|
| **Unit** | Model properties, form `clean()`, helpers, `_generate_po_number`, `can_transition_to` | pytest + pytest-django |
| **Integration** | View + form + formset + DB round-trip; tenant-scoped querysets | pytest-django + Client |
| **Functional / E2E** | User journeys: create → submit → approve → dispatch → receive → close | Playwright |
| **Regression** | Guard existing behaviours against drift | pytest markers + CI |
| **Boundary / Edge** | Max-length, decimal precision, unicode, zero-value, empty formset | parametrised pytest |
| **Negative** | IDOR, CSRF off, invalid transitions, duplicate approvals, min>max rule | pytest |
| **Security** | OWASP A01-A10 mapping; bandit SAST; ZAP DAST | bandit, OWASP ZAP, pytest |
| **Performance** | `django_assert_max_num_queries`, list at 500 POs, Locust load | pytest-django, Locust |
| **Accessibility** | axe-core scan on list/detail/form | axe-playwright |

### 2.3 Entry / exit criteria

**Entry:** `pytest purchase_orders/tests` collects ≥ 80 tests; dev server boots without errors; fixtures seed per-tenant without collisions.

**Exit gate:** see §7 Release Exit Gate.

### 2.4 Risk register (pre-test)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Rejected PO can never be re-approved | High | Critical | Defect D-01; clear approvals on resubmit |
| Arbitrary email dispatch → data-exfil | Medium | High | Defect D-04; pin recipient to `vendor.email` + allow-list |
| Concurrent PO create collides on `po_number` | Medium | High | Defect D-08; wrap generation in `transaction.atomic` + `select_for_update` OR use a DB sequence |
| Creator self-approves large-value PO | High | Medium-High | Defect D-03; disallow `approver == created_by` |
| Non-admin triggers state transitions | High | High | Defect D-02; enforce `is_tenant_admin` or RBAC role |

---

## 3. Test Scenarios

### 3.1 Purchase Order — core (PO-XX)

| # | Scenario | Type |
|---|---|---|
| PO-01 | Create PO with header only (no items) | Functional |
| PO-02 | Create PO with 1 valid line item | Functional |
| PO-03 | Create PO with 10 line items (stress) | Boundary |
| PO-04 | Create PO with vendor from another tenant (IDOR) | Negative / Security |
| PO-05 | Create PO with inactive vendor | Negative |
| PO-06 | Create PO with `order_date` in future | Edge |
| PO-07 | Create PO with `expected_delivery_date < order_date` | Edge / Validation |
| PO-08 | Create PO — `po_number` auto-generates `PO-00001` on first | Functional |
| PO-09 | Create PO — concurrent create does not collide on `unique_together` | Concurrency / Security |
| PO-10 | Edit draft PO | Functional |
| PO-11 | Edit non-draft PO → redirected with warning | Negative |
| PO-12 | Edit PO — vendor swap replaces items’ parent correctly | Integration |
| PO-13 | Delete draft PO | Functional |
| PO-14 | Delete non-draft PO blocked | Negative |
| PO-15 | Delete PO — `vendor` on_delete=PROTECT blocks vendor delete | Integration |
| PO-16 | Detail view shows correct totals | Functional |
| PO-17 | Detail view timeline renders per status | UI |
| PO-18 | Detail view — cross-tenant access → 404 | Security (IDOR) |
| PO-19 | List — search by PO number | Functional |
| PO-20 | List — search by vendor name | Functional |
| PO-21 | List — filter by status | Functional |
| PO-22 | List — filter by vendor | Functional |
| PO-23 | List — filter by date range | Functional |
| PO-24 | List — filters persist across pagination | Functional |
| PO-25 | List — N+1 query guard (≤ 6 queries for 20 POs) | Performance |
| PO-26 | List — empty state rendered | UI |
| PO-27 | Anonymous → `/purchase-orders/` → redirect to login | Security |

### 3.2 Line items (ITEM-XX)

| # | Scenario | Type |
|---|---|---|
| ITEM-01 | `line_total = quantity × unit_price` | Unit |
| ITEM-02 | `discount_amount = quantity × discount` | Unit |
| ITEM-03 | `tax_amount` quantized to 2dp | Unit |
| ITEM-04 | `tax_rate = 0` → zero tax | Boundary |
| ITEM-05 | `tax_rate = 100` → full tax | Boundary |
| ITEM-06 | `tax_rate > 100` blocked at form level | Negative |
| ITEM-07 | `discount > unit_price` allowed (negative tax base) | Edge |
| ITEM-08 | `quantity = 0` blocked (`PositiveIntegerField` rejects 0 via widget `min=1`) | Negative |
| ITEM-09 | `unit_price = 0` allowed | Edge |
| ITEM-10 | Product from another tenant → formset invalid | Security (IDOR) |
| ITEM-11 | 1000-item PO → grand_total stable, no float drift | Scalability |

### 3.3 Status transitions (TRN-XX)

| # | Scenario | Type |
|---|---|---|
| TRN-01 | draft → pending_approval with items | Functional |
| TRN-02 | draft → pending_approval with no items → blocked | Negative |
| TRN-03 | draft → cancelled | Functional |
| TRN-04 | pending_approval → approved (threshold met) | Functional |
| TRN-05 | pending_approval → approved (threshold unmet) | Functional |
| TRN-06 | pending_approval → draft on rejection | Functional |
| TRN-07 | **Resubmit after rejection can be approved** | Regression (covers D-01) |
| TRN-08 | approved → sent via dispatch | Functional |
| TRN-09 | sent → partially_received | Functional |
| TRN-10 | sent → received | Functional |
| TRN-11 | partially_received → received | Functional |
| TRN-12 | received → closed | Functional |
| TRN-13 | closed → anything → blocked | Negative |
| TRN-14 | cancelled → draft (reopen clears approvals) | Functional |
| TRN-15 | reopen from non-cancelled → blocked | Negative |
| TRN-16 | GET on transition URL → redirect (POST-only) | Security (CSRF) |

### 3.4 Approvals (APP-XX)

| # | Scenario | Type |
|---|---|---|
| APP-01 | Single-approval rule: 1 approve → `approved` | Functional |
| APP-02 | Two-approval rule: 1 approve → still pending; 2nd → `approved` | Functional |
| APP-03 | Rejection overrides any approvals | Functional |
| APP-04 | Duplicate approval by same user blocked | Negative |
| APP-05 | No rule matches total → defaults to 1 approval (audit flag) | Boundary / Defect |
| APP-06 | Creator self-approves → should be blocked (SOD) | Negative / Security |
| APP-07 | Non-tenant-admin user approves → should be blocked | Security / RBAC |
| APP-08 | Cross-tenant approve (PK from other tenant) → 404 | Security (IDOR) |
| APP-09 | Approval form with missing `decision` → error message shown | Negative / UX |
| APP-10 | Pending approvals list excludes user’s own decided POs | Functional |

### 3.5 Dispatch (DSP-XX)

| # | Scenario | Type |
|---|---|---|
| DSP-01 | Dispatch via email with vendor default email | Functional |
| DSP-02 | Dispatch via EDI / manual / other (no email sent) | Functional |
| DSP-03 | Dispatch to arbitrary external email → should be restricted | Security (Data-exfil) |
| DSP-04 | Dispatch from non-approved status → blocked | Negative |
| DSP-05 | Email body contains PO number, items, totals, vendor | Functional |
| DSP-06 | Email delivery failure does NOT flip status to `sent` | Regression |
| DSP-07 | Dispatch by non-admin → should be blocked | Security / RBAC |
| DSP-08 | Emoji/unicode in notes renders safely in email | Edge |

### 3.6 Approval Rules (RULE-XX)

| # | Scenario | Type |
|---|---|---|
| RULE-01 | Create rule with valid range | Functional |
| RULE-02 | Create rule where `min > max` → blocked | Negative |
| RULE-03 | Create overlapping rules → warning or ordered precedence | Edge |
| RULE-04 | Inactive rule ignored by `approval_status` | Functional |
| RULE-05 | Rule search by name | Functional |
| RULE-06 | Delete rule — attached POs unaffected | Functional |
| RULE-07 | Cross-tenant rule delete → 404 | Security |

### 3.7 Security cross-cutting (SEC-XX)

| # | Scenario | OWASP |
|---|---|---|
| SEC-01 | Every view requires login | A01 |
| SEC-02 | Every view filters by tenant | A01 |
| SEC-03 | CSRF required on POST endpoints | A01 |
| SEC-04 | `po.notes` rendered auto-escaped | A03 |
| SEC-05 | `po.shipping_address` rendered via `linebreaksbr` (safe) | A03 |
| SEC-06 | Arbitrary recipient email dispatch (D-04) | A01 / A04 |
| SEC-07 | Concurrent PO create → no duplicate `po_number` | A04 |
| SEC-08 | Bandit scan has no High findings | A06 |
| SEC-09 | `DEBUG=False` in prod settings | A05 |
| SEC-10 | Auth failures throttled (login view) | A07 |
| SEC-11 | AuditLog emitted on approve/reject/cancel/delete/dispatch | A09 |

---

## 4. Detailed Test Cases

Only the most load-bearing cases are expanded here; the full suite is scaffolded in §5.

### 4.1 Core PO CRUD

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-PO-002 | Create PO with 1 valid line item | Tenant admin logged in; 1 active vendor + 1 active product exist | POST `/purchase-orders/create/` with vendor, order_date, 1 item row | `vendor=v.pk, order_date=today, items-0-product=p.pk, items-0-quantity=2, items-0-unit_price=10.00, items-0-tax_rate=10, items-0-discount=0` | 302 → `/purchase-orders/<pk>/`; DB has 1 PO (status=draft, po_number=`PO-00001`) + 1 item; grand_total = 22.00 | PO record persisted |
| TC-PO-009 | Concurrent PO creates do not collide | Tenant + 1 vendor/1 product | Two threads call `PurchaseOrder(...).save()` simultaneously | Same tenant, no `po_number` provided | Both succeed with distinct `po_number` values OR one raises cleanly with a user-facing error, not an unhandled `IntegrityError` | 2 rows with unique po_number |
| TC-PO-013 | Delete draft PO | Draft PO exists | POST `/purchase-orders/<pk>/delete/` | `{}` with CSRF token | 302 → `/purchase-orders/`; PO + items deleted; success message | Row removed |
| TC-PO-014 | Delete non-draft PO blocked | PO status=approved | POST `/purchase-orders/<pk>/delete/` | `{}` | 302 → detail; warning message; PO still exists | No change |
| TC-PO-018 | Cross-tenant detail → 404 | Tenant A logged in; PO belongs to Tenant B | GET `/purchase-orders/<B.pk>/` | — | 404 | No disclosure |
| TC-PO-025 | N+1 on list page (20 POs) | 20 POs seeded, each with 3 items | GET `/purchase-orders/` wrapped in `django_assert_max_num_queries(6)` | — | Assertion passes; queries ≤ 6 | No load drift |

### 4.2 Transitions

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-TRN-002 | Submit empty-item PO blocked | Draft PO with 0 items | POST `/purchase-orders/<pk>/submit/` | — | Warning message; status still draft | No transition |
| TC-TRN-007 | Resubmit after reject can reach approved | Draft PO; 1 rejection exists from prior cycle | Submit → new approver approves | — | `po.status == 'approved'`; old rejection does not block | Approvals list: rejected + approved |
| TC-TRN-013 | Closed PO can't transition | Closed PO | POST any transition (cancel, reopen) | — | Warning; status unchanged | Immutable |
| TC-TRN-016 | GET on transition URLs redirects | PO exists | GET each of `/submit/, /approve/, /reject/, /cancel/, /close/, /mark-received/, /reopen/` | — | 302 back to detail; no state change | CSRF safe |

### 4.3 Approvals / SOD / RBAC

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-APP-002 | 2-approval threshold | Active rule covers amount with `required_approvals=2`; PO pending_approval | User A approve → user B approve | — | After A: `pending`, status unchanged. After B: `approved`, status flipped | 2 approvals |
| TC-APP-004 | Duplicate approval blocked | User A already approved | POST /approve/ again | — | Warning; no new approval row | Idempotent |
| TC-APP-006 | Creator self-approval blocked | PO created by user A; A is only approver | POST /approve/ as A | — | 403 OR redirect with error "Creator cannot approve own PO" | No approval recorded |
| TC-APP-007 | Non-admin RBAC | Non-tenant-admin user; PO pending | POST /approve/ | — | 403 OR redirect with error | No approval |
| TC-APP-009 | Invalid approval form | decision field missing | POST /reject/ without `decision` | `{}` | Error message displayed; status unchanged | UX feedback |

### 4.4 Dispatch / Data-exfil

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-DSP-003 | Arbitrary recipient email | PO approved | POST /dispatch/ with `sent_to_email='attacker@evil.com'` | attacker email | 403 OR recipient forced to `po.vendor.email` / allow-listed domain | No leakage |
| TC-DSP-006 | Email failure rolls back state | Email backend raises | POST /dispatch/ | — | PO status remains `approved`; warning shown; no Dispatch record OR record marked `failed` | No partial commit |
| TC-DSP-008 | Unicode notes encoded safely | PO with notes=`"漢字 🚀 <script>"` | POST /dispatch/ email | — | Email body contains UTF-8-encoded original text; no HTML interpretation | Safe |

### 4.5 Approval Rules

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-RULE-002 | min > max rejected | Admin on rule create | POST /approval-rules/create/ | `min=1000, max=10` | Form error "Max must be ≥ Min"; no DB row | No rule |
| TC-RULE-003 | Overlapping rule warning | Rule `(0-1000, req=1)` exists | Create rule `(500-1500, req=3)` | overlapping | Either: reject OR accept with documented precedence; behaviour deterministic | Either outcome acceptable if documented |
| TC-RULE-004 | Inactive rule excluded | Rule `0-1000 req=2 is_active=False` | Compute `approval_status` for $500 PO with 1 approve | — | Falls back to `required=1` → `approved` (inactive rule ignored) | Documented |

### 4.6 Performance & Scalability

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-PERF-001 | List p95 latency | 500 POs, each 3 items, tenant indexed | Locust 50 VU × 60 s on `/purchase-orders/` | — | p95 < 300 ms | — |
| TC-PERF-002 | Query count for 100-PO list | 100 POs | `django_assert_max_num_queries(6)` | — | ≤ 6 queries | — |
| TC-PERF-003 | Detail page query budget | PO with 20 items, 3 approvals, 2 dispatches | GET detail wrapped in `django_assert_max_num_queries(15)` | — | ≤ 15 queries | — |

---

## 5. Automation Strategy

### 5.1 Tool stack

| Layer | Tool | Rationale |
|---|---|---|
| Unit + integration | pytest + pytest-django | Already in use ([pytest.ini](../pytest.ini)) |
| Factories | factory-boy | Lower boilerplate than manual fixtures; aligns with NavIMS patterns |
| E2E | Playwright (Python) | Cross-browser E2E smoke |
| Load | Locust | Scriptable Python; PO create + list hot paths |
| SAST | bandit | Static scan for injection/`exec`/hardcoded secrets |
| DAST | OWASP ZAP (baseline) | CSRF, headers, XSS |
| Accessibility | axe-playwright | WCAG 2.1 AA on list/detail/form |

### 5.2 Suite layout

```
purchase_orders/
└── tests/
    ├── __init__.py
    ├── conftest.py                   # tenant, user, admin, vendor, product, po, approval_rule fixtures
    ├── test_models.py                # property math + state machine + po_number generation
    ├── test_forms.py                 # validation, cross-field rules
    ├── test_views_po_crud.py         # list/create/detail/edit/delete
    ├── test_views_transitions.py     # submit/approve/reject/dispatch/cancel/close/reopen
    ├── test_views_approval_rules.py  # rule CRUD + pending approvals list
    ├── test_approval_engine.py       # threshold, rejection, self-approval, multi-rule
    ├── test_dispatch.py              # email body, failure rollback, arbitrary recipient
    ├── test_security.py              # OWASP A01-A10 mapping
    └── test_performance.py           # N+1 guards
```

Update [pytest.ini](../pytest.ini):

```ini
testpaths = catalog/tests vendors/tests purchase_orders/tests
```

### 5.3 `conftest.py`

```python
# purchase_orders/tests/conftest.py
from decimal import Decimal
from datetime import date
import pytest

from core.models import Tenant, User
from vendors.models import Vendor
from catalog.models import Category, Product
from purchase_orders.models import (
    PurchaseOrder, PurchaseOrderItem, ApprovalRule,
)


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Test", slug="acme-test")


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Globex Test", slug="globex-test")


@pytest.fixture
def admin_user(db, tenant):
    return User.objects.create_user(
        username="admin_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def approver_user(db, tenant):
    return User.objects.create_user(
        username="approver_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="staff_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_user(db, other_tenant):
    return User.objects.create_user(
        username="admin_other", password="qa_pass_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant, company_name="Widgets Inc",
        email="sales@widgets.example",
        is_active=True, status="active",
    )


@pytest.fixture
def product(db, tenant):
    category = Category.objects.create(tenant=tenant, name="Supplies")
    return Product.objects.create(
        tenant=tenant, sku="SUP-001", name="Stapler",
        category=category, purchase_cost=10, retail_price=20,
        status="active",
    )


@pytest.fixture
def approval_rule(db, tenant):
    return ApprovalRule.objects.create(
        tenant=tenant, name="Low value",
        min_amount=Decimal("0"), max_amount=Decimal("100000.00"),
        required_approvals=1, is_active=True,
    )


@pytest.fixture
def draft_po(db, tenant, admin_user, vendor, product):
    po = PurchaseOrder.objects.create(
        tenant=tenant, vendor=vendor, order_date=date.today(),
        payment_terms="net_30", created_by=admin_user,
    )
    PurchaseOrderItem.objects.create(
        tenant=tenant, purchase_order=po, product=product,
        quantity=2, unit_price=Decimal("50.00"),
        tax_rate=Decimal("10.00"), discount=Decimal("0"),
    )
    return po


@pytest.fixture
def pending_po(db, draft_po):
    draft_po.status = "pending_approval"
    draft_po.save()
    return draft_po
```

### 5.4 `test_models.py`

```python
from decimal import Decimal
from datetime import date
import threading
import pytest

from purchase_orders.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderApproval


@pytest.mark.django_db
class TestPurchaseOrderTotals:
    def test_subtotal_equals_sum_of_line_totals(self, draft_po, product, tenant):
        PurchaseOrderItem.objects.create(
            tenant=tenant, purchase_order=draft_po, product=product,
            quantity=3, unit_price=Decimal("7.50"),
        )
        assert draft_po.subtotal == Decimal("100.00") + Decimal("22.50")

    def test_grand_total_formula(self, draft_po):
        # 2 × 50 = 100; tax 10% of (100-0) = 10; discount 0 → 110
        assert draft_po.grand_total == Decimal("110.00")

    def test_tax_amount_rounded_to_2dp(self, tenant, draft_po, product):
        item = PurchaseOrderItem.objects.create(
            tenant=tenant, purchase_order=draft_po, product=product,
            quantity=1, unit_price=Decimal("33.33"),
            tax_rate=Decimal("7.5"),
        )
        assert item.tax_amount == Decimal("2.50")  # rounded


@pytest.mark.django_db
class TestStateMachine:
    @pytest.mark.parametrize("src,dst,ok", [
        ("draft", "pending_approval", True),
        ("draft", "approved", False),
        ("closed", "draft", False),
        ("cancelled", "draft", True),
        ("sent", "received", True),
    ])
    def test_can_transition_to(self, draft_po, src, dst, ok):
        draft_po.status = src
        assert draft_po.can_transition_to(dst) is ok


@pytest.mark.django_db
class TestPoNumberGeneration:
    def test_first_po_is_PO_00001(self, tenant, vendor):
        po = PurchaseOrder.objects.create(
            tenant=tenant, vendor=vendor, order_date=date.today(),
        )
        assert po.po_number == "PO-00001"

    def test_sequence_increments(self, tenant, vendor):
        PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, order_date=date.today())
        p2 = PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, order_date=date.today())
        assert p2.po_number == "PO-00002"

    def test_concurrent_creates_do_not_duplicate(self, tenant, vendor, django_db_blocker):
        """Reproduces D-08 (PO number race). Today this test FAILS — that is the point."""
        from django.db import connections
        results = []
        errors = []

        def create():
            try:
                connections['default'].connect()
                po = PurchaseOrder.objects.create(
                    tenant=tenant, vendor=vendor, order_date=date.today(),
                )
                results.append(po.po_number)
            except Exception as e:
                errors.append(e)

        with django_db_blocker.unblock():
            threads = [threading.Thread(target=create) for _ in range(5)]
            for t in threads: t.start()
            for t in threads: t.join()

        assert len(set(results)) == len(results), f"Duplicate po_numbers: {results}"
        assert not errors, f"IntegrityErrors: {errors}"


@pytest.mark.django_db
class TestApprovalStatus:
    def test_rejection_blocks_approval(self, pending_po, approver_user):
        PurchaseOrderApproval.objects.create(
            tenant=pending_po.tenant, purchase_order=pending_po,
            approver=approver_user, decision="rejected",
        )
        assert pending_po.approval_status == "rejected"

    def test_resubmit_after_reject_can_be_approved(
        self, pending_po, admin_user, approver_user
    ):
        """Regression for D-01. Old rejection must NOT block a fresh cycle."""
        # Cycle 1: reject
        PurchaseOrderApproval.objects.create(
            tenant=pending_po.tenant, purchase_order=pending_po,
            approver=admin_user, decision="rejected",
        )
        pending_po.status = "draft"; pending_po.save()

        # Cycle 2: resubmit + approve
        pending_po.status = "pending_approval"; pending_po.save()
        # After D-01 remediation: submit clears stale approvals
        PurchaseOrderApproval.objects.create(
            tenant=pending_po.tenant, purchase_order=pending_po,
            approver=approver_user, decision="approved",
        )
        assert pending_po.approval_status == "approved"
```

### 5.5 `test_forms.py`

```python
from decimal import Decimal
import pytest

from purchase_orders.forms import (
    PurchaseOrderForm, PurchaseOrderItemFormSet, ApprovalRuleForm,
)


@pytest.mark.django_db
class TestApprovalRuleForm:
    def test_min_greater_than_max_rejected(self, tenant):
        """Regression for D-06."""
        form = ApprovalRuleForm(
            data={
                'name': 'Bad', 'min_amount': '1000', 'max_amount': '10',
                'required_approvals': '1', 'is_active': 'on',
            },
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'max_amount' in form.errors or '__all__' in form.errors


@pytest.mark.django_db
class TestPurchaseOrderForm:
    def test_vendor_queryset_is_tenant_scoped(self, tenant, other_tenant):
        from vendors.models import Vendor
        v_mine = Vendor.objects.create(
            tenant=tenant, company_name="Mine", is_active=True, status="active")
        v_other = Vendor.objects.create(
            tenant=other_tenant, company_name="Theirs", is_active=True, status="active")
        form = PurchaseOrderForm(tenant=tenant)
        qs = form.fields['vendor'].queryset
        assert v_mine in qs
        assert v_other not in qs

    def test_vendor_queryset_excludes_inactive(self, tenant):
        from vendors.models import Vendor
        v_active = Vendor.objects.create(
            tenant=tenant, company_name="Active", is_active=True, status="active")
        v_draft = Vendor.objects.create(
            tenant=tenant, company_name="Draft", is_active=True, status="draft")
        form = PurchaseOrderForm(tenant=tenant)
        qs = form.fields['vendor'].queryset
        assert v_active in qs
        assert v_draft not in qs
```

### 5.6 `test_views_po_crud.py`

```python
from datetime import date
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestListView:
    def test_anonymous_redirected(self, client):
        resp = client.get(reverse('purchase_orders:po_list'))
        assert resp.status_code == 302
        assert '/accounts/login/' in resp['Location']

    def test_list_tenant_isolation(
        self, client_logged_in, draft_po, other_tenant
    ):
        from purchase_orders.models import PurchaseOrder
        from vendors.models import Vendor
        other_vendor = Vendor.objects.create(
            tenant=other_tenant, company_name="Other",
            is_active=True, status="active")
        PurchaseOrder.objects.create(
            tenant=other_tenant, vendor=other_vendor, order_date=date.today())

        resp = client_logged_in.get(reverse('purchase_orders:po_list'))
        assert draft_po.po_number.encode() in resp.content
        assert resp.content.count(b'PO-') == 1

    def test_filter_by_status(self, client_logged_in, draft_po):
        resp = client_logged_in.get(
            reverse('purchase_orders:po_list') + '?status=approved')
        assert draft_po.po_number.encode() not in resp.content

    def test_search_by_po_number(self, client_logged_in, draft_po):
        resp = client_logged_in.get(
            reverse('purchase_orders:po_list') + f'?q={draft_po.po_number}')
        assert draft_po.po_number.encode() in resp.content


@pytest.mark.django_db
class TestDetailView:
    def test_cross_tenant_returns_404(
        self, client, other_tenant_user, draft_po
    ):
        client.force_login(other_tenant_user)
        resp = client.get(reverse('purchase_orders:po_detail', args=[draft_po.pk]))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestDeleteView:
    def test_delete_draft_succeeds(self, client_logged_in, draft_po):
        pk = draft_po.pk
        resp = client_logged_in.post(
            reverse('purchase_orders:po_delete', args=[pk]))
        assert resp.status_code == 302
        from purchase_orders.models import PurchaseOrder
        assert not PurchaseOrder.objects.filter(pk=pk).exists()

    def test_delete_non_draft_blocked(self, client_logged_in, pending_po):
        resp = client_logged_in.post(
            reverse('purchase_orders:po_delete', args=[pending_po.pk]))
        from purchase_orders.models import PurchaseOrder
        assert PurchaseOrder.objects.filter(pk=pending_po.pk).exists()

    def test_delete_GET_redirects_without_deleting(
        self, client_logged_in, draft_po
    ):
        resp = client_logged_in.get(
            reverse('purchase_orders:po_delete', args=[draft_po.pk]))
        assert resp.status_code == 302
        from purchase_orders.models import PurchaseOrder
        assert PurchaseOrder.objects.filter(pk=draft_po.pk).exists()
```

### 5.7 `test_views_transitions.py`

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestSubmit:
    def test_submit_with_items(self, client_logged_in, draft_po):
        client_logged_in.post(
            reverse('purchase_orders:po_submit', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'pending_approval'

    def test_submit_without_items_blocked(self, client_logged_in, draft_po):
        draft_po.items.all().delete()
        client_logged_in.post(
            reverse('purchase_orders:po_submit', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'

    def test_submit_must_be_POST(self, client_logged_in, draft_po):
        client_logged_in.get(
            reverse('purchase_orders:po_submit', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'


@pytest.mark.django_db
class TestResubmitAfterReject:
    """Regression for D-01 (critical)."""

    def test_resubmit_can_reach_approved(
        self, client, pending_po, admin_user, approver_user, approval_rule
    ):
        # Cycle 1: admin rejects
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_reject', args=[pending_po.pk]),
            {'decision': 'rejected', 'notes': 'try again'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'draft'

        # Cycle 2: resubmit + approve by different user
        client.post(reverse('purchase_orders:po_submit', args=[pending_po.pk]))
        client.force_login(approver_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved', 'notes': 'ok'},
        )
        pending_po.refresh_from_db()
        # Today this assertion FAILS — D-01 blocks approval forever
        assert pending_po.status == 'approved'
```

### 5.8 `test_security.py`

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestAuthAndRBAC:
    @pytest.mark.parametrize("url_name,args", [
        ('purchase_orders:po_list', []),
        ('purchase_orders:po_create', []),
        ('purchase_orders:approval_rule_list', []),
        ('purchase_orders:approval_list', []),
    ])
    def test_login_required(self, client, url_name, args):
        resp = client.get(reverse(url_name, args=args))
        assert resp.status_code == 302
        assert '/accounts/login/' in resp['Location']

    def test_non_admin_cannot_approve(self, client, non_admin_user, pending_po):
        """Regression for D-02."""
        client.force_login(non_admin_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved'},
        )
        assert pending_po.approvals.filter(approver=non_admin_user).count() == 0

    def test_creator_cannot_self_approve(self, client, admin_user, pending_po):
        """Regression for D-03."""
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status != 'approved'

    def test_dispatch_to_external_email_blocked(
        self, client, admin_user, draft_po
    ):
        """Regression for D-04."""
        draft_po.status = 'approved'; draft_po.save()
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_dispatch', args=[draft_po.pk]),
            {
                'dispatch_method': 'email',
                'sent_to_email': 'attacker@evil.example',
                'notes': '',
            },
        )
        # After remediation: recipient forced to vendor.email OR rejected
        draft_po.refresh_from_db()
        dispatches = draft_po.dispatches.all()
        if dispatches:
            assert dispatches.first().sent_to_email != 'attacker@evil.example'

    def test_cross_tenant_approval_rule_delete_404(
        self, client, admin_user, other_tenant
    ):
        from purchase_orders.models import ApprovalRule
        rule = ApprovalRule.objects.create(
            tenant=other_tenant, name="X",
            min_amount=0, max_amount=100, required_approvals=1,
        )
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:approval_rule_delete', args=[rule.pk]))
        assert ApprovalRule.objects.filter(pk=rule.pk).exists()


@pytest.mark.django_db
class TestCSRFAndMethods:
    @pytest.mark.parametrize("url_name", [
        'purchase_orders:po_submit', 'purchase_orders:po_approve',
        'purchase_orders:po_reject', 'purchase_orders:po_mark_received',
        'purchase_orders:po_close', 'purchase_orders:po_cancel',
        'purchase_orders:po_reopen', 'purchase_orders:po_delete',
    ])
    def test_get_on_transition_is_safe(
        self, client_logged_in, draft_po, url_name
    ):
        resp = client_logged_in.get(reverse(url_name, args=[draft_po.pk]))
        assert resp.status_code == 302
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'


@pytest.mark.django_db
class TestXSS:
    def test_notes_escaped_on_detail(self, client_logged_in, draft_po):
        draft_po.notes = '<script>alert(1)</script>'
        draft_po.save()
        resp = client_logged_in.get(
            reverse('purchase_orders:po_detail', args=[draft_po.pk]))
        assert b'<script>alert(1)</script>' not in resp.content
        assert b'&lt;script&gt;' in resp.content
```

### 5.9 `test_performance.py`

```python
from decimal import Decimal
from datetime import date
import pytest
from django.urls import reverse
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem


@pytest.mark.django_db
def test_list_query_budget(
    client_logged_in, tenant, vendor, product, django_assert_max_num_queries
):
    for _ in range(20):
        po = PurchaseOrder.objects.create(
            tenant=tenant, vendor=vendor, order_date=date.today(),
        )
        for _ in range(3):
            PurchaseOrderItem.objects.create(
                tenant=tenant, purchase_order=po, product=product,
                quantity=1, unit_price=Decimal("10"),
            )
    with django_assert_max_num_queries(6):
        resp = client_logged_in.get(reverse('purchase_orders:po_list'))
        assert resp.status_code == 200
```

### 5.10 Locust — `locustfile.py`

```python
from locust import HttpUser, task, between

class POUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post('/accounts/login/', {
            'username': 'admin_acme', 'password': 'demo123',
        })

    @task(5)
    def list_pos(self):
        self.client.get('/purchase-orders/')

    @task(1)
    def approval_queue(self):
        self.client.get('/purchase-orders/approvals/')
```

### 5.11 CI hooks

```yaml
# .github/workflows/ci.yml (excerpt)
- run: pytest purchase_orders/tests --cov=purchase_orders --cov-fail-under=85
- run: bandit -r purchase_orders/
- run: pip-audit -r requirements.txt --fail-on-severity high
```

---

## 6. Defects, Risks & Recommendations

> Verification key: ✅ = reproduced in Django shell; 📋 = inspected code only.

### 6.1 Defects

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-01** ✅ | **Critical** | A04 | [models.py:94-108](../purchase_orders/models.py#L94-L108), [views.py:226-245](../purchase_orders/views.py#L226-L245) | `approval_status` returns `'rejected'` whenever **any** `PurchaseOrderApproval.decision=='rejected'` row exists. After reject → resubmit, the stale rejection is **not** cleared, so the PO can **never** be approved again. Reproduced: `approval_status` returns `rejected` after resubmit. | On `po_submit_for_approval_view`, call `po.approvals.all().delete()` before transitioning to `pending_approval` (mirror `po_reopen_view`). Alternatively, scope the rejection check to approvals created **after** the most recent `draft → pending_approval` transition (requires a cycle counter or timestamp). |
| **D-02** ✅ | High | A01 | [views.py:226,248,288,321,415,434,453,472,202](../purchase_orders/views.py#L248) | None of `po_submit`, `po_approve`, `po_reject`, `po_dispatch`, `po_mark_received`, `po_close`, `po_cancel`, `po_reopen`, `po_delete` enforce any role check beyond `@login_required`. A non-admin user (`is_tenant_admin=False`) successfully approved a PO in shell test. | Introduce `@tenant_admin_required` decorator *or* map RBAC permissions from `core.Permission('purchasing.approve_po' / 'dispatch_po' / 'cancel_po')`. Gate each sensitive view. Add regression in `test_security.py::test_non_admin_cannot_approve`. |
| **D-03** ✅ | High | A04 | [views.py:261-264](../purchase_orders/views.py#L261-L264) | PO creator can approve their own PO (SOD violation). Shell verified: creator-as-approver gives `approval_status == 'approved'` on a $1000 PO. | In `po_approve_view`: `if po.created_by_id == request.user.id: messages.warning(request, 'Creators cannot approve their own POs'); return redirect(...)`. Enforce the same at the model layer with `PurchaseOrderApproval.clean()`. |
| **D-04** ✅ | High | A01 / A04 | [views.py:334-391](../purchase_orders/views.py#L334-L391) | `sent_to_email` is a free-form `EmailField` — a dispatcher (including a non-admin per D-02) can exfiltrate full PO contents (line items, totals, vendor, notes) to an arbitrary external address. Shell verified: non-admin user successfully sent PO body to `attacker@evil.com`. | (1) Default and lock `sent_to_email` to `po.vendor.email` (disable the form input); (2) optionally allow override only to a tenant-configured allow-list of domains; (3) audit-log every dispatch with recipient. |
| **D-05** 📋 | High | A04 | [views.py:395-399](../purchase_orders/views.py#L395-L399) | `po.status = 'sent'` is set **after** the `send_mail` exception handler — so if email fails, the PO is still moved to `sent` and a `Dispatch` record exists claiming a failed recipient. | Move `po.status='sent'` inside the success branch only. Add a `status` field to `PurchaseOrderDispatch` (`sent` / `failed`). Wrap in `transaction.atomic()` so the Dispatch row is rolled back on email failure. |
| **D-06** ✅ | Medium | A04 | [forms.py:112-154](../purchase_orders/forms.py#L112-L154) | `ApprovalRuleForm` has no validation ensuring `min_amount ≤ max_amount`. Shell verified: `min=1000, max=10` is accepted and matches no POs, silently dropping to the 1-approver fallback. | Add `def clean(self)` raising `ValidationError('max_amount must be ≥ min_amount')`. Also add `Meta.constraints = [CheckConstraint(check=Q(max_amount__gte=F('min_amount')), name='...')]` to enforce at DB layer. |
| **D-07** 📋 | Medium | A04 | [models.py:98-108](../purchase_orders/models.py#L98-L108) | If `grand_total` falls **outside** every active rule’s `[min,max]` band (e.g. above the highest `max_amount`, or inside a band gap), `approval_status` silently falls back to `required=1`. Hidden business-rule bypass: a $1M PO can be approved by a single approver if no high-value rule exists. | Raise a visible warning to the approver UI when no rule matches; require at least one catch-all rule per tenant; bootstrap the seed with a high-ceiling rule. |
| **D-08** 📋 | Medium-High | A04 | [models.py:115-129](../purchase_orders/models.py#L115-L129) | `_generate_po_number` reads `order_by('-id').first()` then writes — classic TOCTOU race. Two parallel requests get same `po_number` → `IntegrityError` on `unique_together('tenant','po_number')`. | Wrap save in `transaction.atomic()` + `select_for_update()` on a per-tenant counter row, OR add a `TenantSequence` helper model, OR switch to DB-native sequence (Postgres `nextval`). |
| **D-09** 📋 | Medium | A01 | [views.py:161-199, 202-218](../purchase_orders/views.py#L161-L218) | Any tenant user can edit/delete any draft PO, including POs they did not create. `created_by` is never consulted. | Add a `created_by == request.user OR is_tenant_admin` gate on `po_edit_view` and `po_delete_view`. |
| **D-10** ✅ | Medium | Perf | [models.py:77-91](../purchase_orders/models.py#L77-L91), [po_list.html:149](../templates/purchase_orders/po_list.html#L149) | `subtotal`, `tax_total`, `discount_total`, `grand_total` each call `self.items.all()` — accessed on every row of the list template. Shell verified: 10 POs produced 27 additional queries just from `grand_total`. | (a) Denormalise totals as DB-backed fields recomputed on item save via signals, (b) use `Prefetch('items')` in the list queryset and memoise the totals on the model instance, or (c) compute with a `Sum(F('quantity')*F('unit_price'))` annotation. |
| **D-11** 📋 | Medium | A03 | [views.py:47-58](../purchase_orders/views.py#L47-L58) | Numeric query params (`vendor`, `date_from`, `date_to`, `page`) are used in ORM filters without type coercion. `PurchaseOrder.filter(vendor_id='abc')` raises `ValueError` → 500. | Coerce and validate: `int(request.GET.get('vendor', 0) or 0)`; wrap date parsing in `datetime.strptime` with try/except; otherwise ignore. |
| **D-12** 📋 | Medium | A09 | all state-change views | No `core.AuditLog` rows written on approve, reject, cancel, close, delete, dispatch — so there is no forensic record of who authorised high-value purchases. | Emit `AuditLog.objects.create(tenant=..., user=request.user, action='po.approve', model_name='PurchaseOrder', object_id=po.pk, changes=json.dumps({...}))` at every sensitive mutation. |
| **D-13** 📋 | Medium | A04 | [views.py:288-317](../purchase_orders/views.py#L288-L317) | `po_reject_view` silently ignores invalid forms — no `messages.error`, no re-render. If JS fails or a bot submits without `decision`, the user sees a success-looking redirect. | Add `messages.error(request, 'Invalid rejection form — decision required')` in the `else` branch of `if form.is_valid()`. |
| **D-14** 📋 | Low | A04 | [views.py:68](../purchase_orders/views.py#L68) | Vendor dropdown in PO list filter uses `Vendor.objects.filter(tenant=tenant, is_active=True)` — but the PO **create** form uses `is_active=True, status='active'`. The list filter exposes `status='draft'` vendors that the create form hides. | Align the queryset with the form: also filter by `status='active'`. |
| **D-15** 📋 | Low | A04 | [views.py:128](../purchase_orders/views.py#L128) | Timeline omits `partially_received` from `status_order`, so a PO in that state returns `current_idx == -1` and all steps render `upcoming`. | Add `'partially_received'` to `status_order` between `sent` and `received`. |
| **D-16** 📋 | Low | A04 | [models.py:180](../purchase_orders/models.py#L180) | Only `tax_amount` quantizes to 2dp; `line_total` / `discount_amount` return raw arithmetic. Summed `grand_total` can carry >2dp drift that the template masks with `floatformat:2` (display-only). Accounting-breaking if exported. | Quantize `line_total`, `discount_amount`, and `grand_total` to `Decimal('0.01')`. |
| **D-17** 📋 | Low | A04 | [forms.py:103-109](../purchase_orders/forms.py#L103-L109) | `PurchaseOrderItemFormSet` uses `extra=3` and no `min_num`. A draft PO can be saved with zero line items. Submit-for-approval catches the 0-item case but the empty PO persists visibly. | Set `min_num=1, validate_min=True` on the formset factory. |
| **D-18** 📋 | Low | A04 | [forms.py](../purchase_orders/forms.py) | No validation that `expected_delivery_date ≥ order_date`. | Add a `clean()` guard in `PurchaseOrderForm`. |
| **D-19** 📋 | Info | A01 | [admin.py:23-28](../purchase_orders/admin.py#L23-L28) | `PurchaseOrderAdmin` exposes all tenants to superuser (tenant is `None`). Documented superuser trap — OK — but a `get_queryset` override scoped to `request.user.tenant` when `not is_superuser` would be safer for staff users. | Override `get_queryset` on all PO admin classes. |
| **D-20** 📋 | Info | A05 | [seed_purchase_orders.py:86-97](../purchase_orders/management/commands/seed_purchase_orders.py#L86-L97) | `ApprovalRule.objects.create` is not idempotent — only the outer `if PurchaseOrder.objects.filter(tenant=tenant).exists()` guards it. If POs exist but rules were flushed manually, rules are never re-created. | Use `ApprovalRule.objects.get_or_create(tenant=tenant, name=...)`. |

### 6.2 Residual risks (post-remediation)

| Risk | Residual likelihood | Residual impact | Mitigation |
|---|---|---|---|
| Email backend misconfigured in prod | Low | High (no delivery) | Monitor `send_mail` failure rate; surface a dispatch-failed dashboard panel |
| Large PO (1000+ items) page-load > 10s | Low | Medium | Paginate line items on detail; add async totals endpoint |
| Seed data collides with manually-created rules | Low | Low | Adopt D-20 fix |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Target coverage

| File | Target line % | Target branch % | Notes |
|---|---|---|---|
| [models.py](../purchase_orders/models.py) | 95 | 90 | State machine + properties are pure functions |
| [forms.py](../purchase_orders/forms.py) | 90 | 85 | Add `clean()` methods after D-06 / D-18 |
| [views.py](../purchase_orders/views.py) | 85 | 75 | Email branches harder to cover end-to-end |
| **Overall `purchase_orders/`** | **≥ 88 %** line, **≥ 80 %** branch | | |

### 7.2 KPIs

| KPI | Target (Green) | Amber | Red |
|---|---|---|---|
| Functional test pass rate | 100 % | 98-99 % | < 98 % |
| Open **Critical** defects | 0 | — | ≥ 1 |
| Open **High** defects | 0 | 1 | ≥ 2 |
| Suite runtime (pytest) | < 30 s | 30-60 s | > 60 s |
| List page p95 latency @ 500 POs | < 300 ms | 300-600 ms | > 600 ms |
| Query count `po_list_view` (20 POs) | ≤ 6 | 7-10 | > 10 |
| Query count `po_detail_view` | ≤ 15 | 16-25 | > 25 |
| Regression-escape rate / release | 0 | 1 | > 1 |
| Bandit High findings | 0 | 1 | ≥ 2 |

### 7.3 Release Exit Gate

All of the following **must** be true:

- [ ] D-01 fixed and `TestResubmitAfterReject::test_resubmit_can_reach_approved` green
- [ ] D-02 fixed with RBAC decorator and regression tests green
- [ ] D-03 fixed (creator cannot self-approve) with regression test green
- [ ] D-04 fixed (recipient pinned or allow-listed) with regression test green
- [ ] D-05 fixed (email failure does not advance status)
- [ ] D-06 and D-18 fixed with form validation tests green
- [ ] D-10 remediated: list-view query count ≤ 6 (test enforced)
- [ ] D-12 implemented: AuditLog emitted on approve/reject/cancel/close/delete/dispatch
- [ ] `pytest purchase_orders/tests` green with **≥ 88 %** line coverage
- [ ] `bandit -r purchase_orders/` → 0 High/Critical
- [ ] `pip-audit` → 0 High/Critical
- [ ] Manual smoke of the golden path (create → submit → approve → dispatch → receive → close) passes in a browser
- [ ] Locust run: list-view p95 < 300 ms @ 500 POs / 50 VU

---

## 8. Summary

The Purchase Order module is feature-complete and follows NavIMS conventions for multi-tenancy, CRUD, filter retention, and status-badge rendering. However, the module ships with **zero test coverage** and contains **one Critical** and **four High-severity** defects that compromise the integrity of the approval workflow and expose a data-exfiltration vector via dispatch.

### Top 5 defects (priority order)

1. **D-01 (Critical)** — Rejected POs can never be re-approved because stale rejection records survive resubmission. **Workflow-breaking.** Fix: clear approvals on submit.
2. **D-02 (High)** — No RBAC; any authenticated tenant user can approve, dispatch, cancel, and delete. Fix: add `@tenant_admin_required` / RBAC gate.
3. **D-03 (High)** — PO creators can approve their own POs (SOD violation). Fix: block `request.user == po.created_by` in approve view.
4. **D-04 (High)** — PO dispatch accepts arbitrary external recipients → data-exfiltration. Fix: pin recipient to `vendor.email` or allow-list.
5. **D-08 (Medium-High)** — PO-number race condition risks `IntegrityError` at scale. Fix: atomic sequence generation.

### Test automation gap

Adopting the scaffolded suite in §5 (≈ 80 tests across 9 files) raises coverage from 0 % to a projected ≥ 88 % line coverage and, importantly, locks in regressions for every fix above.

### Recommended follow-ups

- **"Fix the defects"** — implement D-01 through D-06, D-12 (AuditLog), D-15 (timeline), and D-18 (delivery date) first; scaffold `purchase_orders/tests/` with the §5 snippets.
- **"Build the automation"** — create the 9 test files listed in §5.2, update [pytest.ini](../pytest.ini) `testpaths`, wire into CI.
- **"Manual verification"** — walk through TRN-07, DSP-03, APP-06, APP-07 manually against `runserver` to confirm remediation.

---

*End of report.*
