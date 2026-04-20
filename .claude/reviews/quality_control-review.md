# Module 16 — Quality Control & Inspection — Comprehensive SQA Test Report

**Target:** Django app [quality_control/](../../quality_control/) — QC Checklists, Inspection Routing, Quarantine Management, Defect Reporting, Scrap Write-Offs.
**Reviewer:** Senior SQA (15+ yrs, Django/Python).
**Date:** 2026-04-20.
**Module status:** Implemented, seeded, smoke-tested; no automated suite yet (by plan). Review covers the module post-implementation (no diff-vs-main filter — every file in the app is in scope).

---

## 1. Module Analysis

### 1.1 Surface area

| Artefact | Path | Summary |
|---|---|---|
| Models (8) | [quality_control/models.py](../../quality_control/models.py) | `QCChecklist`, `QCChecklistItem`, `InspectionRoute`, `InspectionRouteRule`, `QuarantineRecord`, `DefectReport`, `DefectPhoto`, `ScrapWriteOff` |
| Forms (7 + 3 inline formsets) | [quality_control/forms.py](../../quality_control/forms.py) | Tenant-scoped ModelForms with `TenantUniqueCodeMixin` on `QCChecklistForm` + `InspectionRouteForm`; `QCChecklistItemFormSet`, `InspectionRouteRuleFormSet`, `DefectPhotoFormSet` |
| Views (35) | [quality_control/views.py](../../quality_control/views.py) | 6 checklist + 5 route + 7 quarantine + 8 defect + 8 scrap + 1 helper |
| URLs | [quality_control/urls.py](../../quality_control/urls.py) | `app_name='quality_control'`, mounted at `/quality-control/` |
| Admin | [quality_control/admin.py](../../quality_control/admin.py) | `TenantScopedAdmin` base + 3 inlines |
| Migration | [quality_control/migrations/0001_initial.py](../../quality_control/migrations/0001_initial.py) | Creates all 8 tables |
| Seeder | [quality_control/management/commands/seed_quality_control.py](../../quality_control/management/commands/seed_quality_control.py) | Per-tenant: 3 checklists, 2 routes, 4 quarantines, 5 defects, 2 scrap (one posted writes a real `StockAdjustment`) |
| Templates (15) | [templates/quality_control/](../../templates/quality_control/) | List/form/detail × 5 entities |
| Wiring | [config/settings.py](../../config/settings.py), [config/urls.py](../../config/urls.py), [templates/partials/sidebar.html](../../templates/partials/sidebar.html) | Module registered; sidebar submenu added |

### 1.2 Business rules (extracted)

| # | Rule | Evidence |
|---|---|---|
| R-01 | Auto-numbered codes (`QCC-NNNNN`, `IR-NNNNN`, `QR-NNNNN`, `DEF-NNNNN`, `SCR-NNNNN`) — TOCTOU-safe via `_save_with_number_retry()` | [models.py:11-30](../../quality_control/models.py#L11-L30) |
| R-02 | Checklist scope: if `applies_to=product/vendor/category`, the corresponding FK is required | [forms.py:66-77](../../quality_control/forms.py#L66-L77) |
| R-03 | Zone must belong to warehouse (cross-validation) on route + quarantine | [forms.py:132-141](../../quality_control/forms.py#L132-L141), [forms.py:215-225](../../quality_control/forms.py#L215-L225) |
| R-04 | Positive qty on `QuarantineRecord`, `DefectReport.quantity_affected`, `ScrapWriteOff.quantity` | model validators + form `clean_*` |
| R-05 | `QuarantineRecord` state machine: `active ↔ under_review → released/scrapped` | [models.py:257-262](../../quality_control/models.py#L257-L262) |
| R-06 | `DefectReport` state machine: `open ↔ investigating → resolved/scrapped` | [models.py:334-339](../../quality_control/models.py#L334-L339) |
| R-07 | `ScrapWriteOff` lifecycle: `pending → approved → posted`; `rejected` branch; segregation-of-duties (requester ≠ approver) | [views.py:649-661](../../quality_control/views.py#L649-L661) |
| R-08 | Scrap post = canonical `decrease` `StockAdjustment` inside `transaction.atomic()` + `select_for_update()` on `StockLevel` | [views.py:687-720](../../quality_control/views.py#L687-L720) |
| R-09 | Releasing a quarantine with `disposition='scrap'` auto-creates a pending `ScrapWriteOff` | [views.py:438-450](../../quality_control/views.py#L438-L450) |
| R-10 | Soft-delete on top-level docs (`deleted_at`) + list queries filter `deleted_at__isnull=True` | [views.py](../../quality_control/views.py) throughout |
| R-11 | `total_value = quantity × unit_cost` computed in `ScrapWriteOff.save()` | [models.py:469-473](../../quality_control/models.py#L469-L473) |
| R-12 | Delete only allowed in early states (quarantine `active`, defect `open`, scrap `pending`) | [views.py](../../quality_control/views.py) |

### 1.3 Dependencies

- **Inbound:** `catalog.Product/Category`, `vendors.Vendor`, `warehousing.Warehouse/Zone`, `receiving.GoodsReceiptNote`, `lot_tracking.LotBatch/SerialNumber`, `inventory.StockLevel/StockAdjustment`, `core.Tenant/User/AuditLog`.
- **Outbound:** writes `inventory.StockAdjustment` on scrap post.

### 1.4 Pre-test risk profile

| Risk area | Inherent | Design mitigation | Residual |
|---|---|---|---|
| Multi-tenant IDOR | High | `get_object_or_404(..., tenant=request.tenant)` + tenant-scoped form querysets + ModelChoiceField enforcement | Low (verified — no findings) |
| Double-post race on scrap | High | `transaction.atomic()` + `select_for_update()` on StockLevel | **Medium–High (D-01)** — obj.approval_status not re-checked under lock |
| Scrap financial correctness | High | `total_value = qty × cost` auto-computed | Low |
| File upload abuse (defect photos) | Medium | Django `ImageField` + Pillow magic-bytes + 2.5 MB request cap | **Medium (D-03)** — no explicit MIME/size/ext whitelist |
| N+1 on list views | Medium | `select_related` on top-level FKs | **Medium (D-02)** — `.count()` on reverse FK in list templates |
| State machine bypass | Medium | `StateMachineMixin.can_transition_to` defined | **Low (D-05)** — ScrapWriteOff + `quarantine_release` bypass it |
| Editing historical records | Medium | `is_active=True` on Product/Warehouse querysets | **Medium (D-04)** — deactivating an FK bricks edit |

---

## 2. Test Plan

| Layer | Tool | Scope |
|---|---|---|
| Unit | `pytest` + `pytest-django` | Model invariants, auto-number, `total_value`, state-machine matrix, `clean()` scope guards |
| Integration | `pytest-django` + `Client` | View × form × model × DB; `@tenant_admin_required` RBAC; `emit_audit` rows; inline formset save path; soft-delete |
| Regression | `test_D<NN>_*` | One per defect below once fixes ship |
| Functional / E2E | Playwright (optional, smoke) | Happy path: checklist → route → receive → quarantine → defect → scrap-post |
| Boundary | Parametrised pytest | qty=0/-1/max; unit_cost<0; description '' and 65k chars; caption overflow |
| Edge | pytest | Unicode / emoji in `description`, `caption`, `notes`; whitespace-only strings |
| Negative | pytest | Invalid state transitions, cross-tenant FK injection via POST, duplicate codes, self-approval, post non-approved, decrement > on_hand |
| Security | pytest + `bandit` + `pip-audit` + manual | OWASP A01/A03/A04/A05/A08/A09 (see §2.1) |
| Performance | `django_assert_max_num_queries` | List-view query budgets; scrap post under contention |
| Scalability | Locust (optional) | 50 concurrent users on `checklist_list` |
| Reliability | pytest + `transaction=True` | Race test for scrap post double-commit |
| Usability | Manual | Flow walkthrough with and without seed data |

### 2.1 OWASP Top 10 evaluation

| OWASP | Applicable? | Verdict | Notes |
|---|---|---|---|
| A01 Broken Access Control | Yes | **Pass** (verified) | `get_object_or_404(..., tenant=request.tenant)` on every entity lookup; IDOR probe returned 404 across checklist/edit/delete |
| A02 Crypto | No | n/a | No secrets / TLS handled in this module |
| A03 Injection / XSS | Yes | **Pass** | ORM queries + Q(); template auto-escape; `linebreaksbr` only on trusted output |
| A04 Insecure design | Yes | **Partial** | R-07 SoD OK; D-01 race + D-04 queryset trap are design gaps |
| A05 Security misconfig | Partial | Info | MariaDB `STRICT_TRANS_TABLES` warning on every `migrate` (out-of-module, flagged as D-10) |
| A06 Vulnerable deps | Partial | Not re-run | No new deps added; rely on `pip-audit` |
| A07 Auth failures | Partial | n/a (inherits platform auth) | — |
| A08 Data integrity / upload | Yes | **Partial** | `DefectPhoto.image` — no explicit MIME whitelist, size cap, or SVG block (D-03) |
| A09 Logging failures | Yes | **Pass** | `emit_audit` on every mutation / transition endpoint |
| A10 SSRF | No | n/a | No outbound URL fetches |

---

## 3. Test Scenarios

### 3.1 QC Checklist (C-)

| # | Scenario | Type |
|---|---|---|
| C-01 | Create checklist auto-generates `QCC-00001` | Integration |
| C-02 | Two concurrent creates → distinct codes (race retry) | Integration / race |
| C-03 | Explicit duplicate `code` within tenant → form error | Unit |
| C-04 | Same `code` across tenants → allowed | Unit |
| C-05 | `applies_to=product` without `product` → rejected | Unit |
| C-06 | `applies_to=vendor` without `vendor` → rejected | Unit |
| C-07 | `applies_to=category` without `category` → rejected | Unit |
| C-08 | Edit checklist whose product was later `is_active=False` → form rejects (D-04) | Regression |
| C-09 | Delete cascades `QCChecklistItem` rows | Integration |
| C-10 | Toggle-active flips flag + emits audit row | Integration |
| C-11 | Cross-tenant IDOR → 404 | Security (A01) |
| C-12 | `list_view` scales without N+1 (D-02) | Performance |
| C-13 | XSS in `name`/`description` rendered escaped | Security (A03) |
| C-14 | Inline item formset: deletion flag survives save | Integration |

### 3.2 Inspection Route (R-)

| # | Scenario | Type |
|---|---|---|
| R-01 | QC zone not in `source_warehouse` → rejected | Unit |
| R-02 | `putaway_zone` in different warehouse → rejected | Unit |
| R-03 | Duplicate `code` within tenant → rejected | Unit |
| R-04 | Inline rules saved atomically with route | Integration |
| R-05 | Delete route cascades `InspectionRouteRule` rows | Integration |
| R-06 | `list_view` N+1 via `r.rules.count` (D-02) | Performance |
| R-07 | Rule with `applies_to=product` but no `product` — no guard (D-08) | Data-integrity |
| R-08 | Cross-tenant IDOR on route/rule endpoints → 404 | Security (A01) |

### 3.3 Quarantine (Q-)

| # | Scenario | Type |
|---|---|---|
| Q-01 | Create hold, auto `QR-00001`, status `active` | Integration |
| Q-02 | `quantity=0` → rejected at form + model | Boundary |
| Q-03 | Zone not in warehouse → form rejects | Unit |
| Q-04 | `active → under_review` via `review` endpoint | Integration |
| Q-05 | `active → released (return_to_stock)` | Integration |
| Q-06 | `active → released (scrap)` auto-creates pending `ScrapWriteOff` | Integration |
| Q-07 | Transition from terminal state → rejected | Negative |
| Q-08 | Delete while `active` → soft-delete | Integration |
| Q-09 | Delete while `released` → rejected | Negative |
| Q-10 | Soft-deleted hold omitted from list + detail 404 | Integration |
| Q-11 | POST without CSRF → 403 | Security |
| Q-12 | Release form: invalid disposition → error | Negative |
| Q-13 | Cross-tenant IDOR on `/release/` → 404 | Security (A01) |
| Q-14 | Audit row per `review`/`release`/`delete` | Regression |
| Q-15 | Concurrent double-release — state-machine guard | Race |

### 3.4 Defect (F-)

| # | Scenario | Type |
|---|---|---|
| F-01 | `quantity_affected=0` → rejected | Boundary |
| F-02 | Photo upload: valid JPEG → saved | Integration |
| F-03 | Photo upload: `.exe` renamed `.jpg` → Pillow rejects (D-03) | Security (A08) |
| F-04 | Photo upload: > 2.5 MB → request-cap rejects | Security (A08) |
| F-05 | Photo upload: SVG → Pillow raises; no explicit guard | Security (A08) |
| F-06 | `open → investigating → resolved` transitions | Integration |
| F-07 | `resolved → open` → rejected (terminal) | Negative |
| F-08 | Delete while `open` → soft-delete | Integration |
| F-09 | Delete while `investigating` → rejected | Negative |
| F-10 | Photo delete while defect `resolved` → verify guard (D-11 candidate) | Negative |
| F-11 | Lot belongs to different product than defect — no guard (D-07) | Data-integrity |
| F-12 | Cross-tenant IDOR on defect + photo endpoints → 404 | Security (A01) |
| F-13 | Filter retention across pagination (D-06) | UX |

### 3.5 Scrap Write-Off (S-)

| # | Scenario | Type |
|---|---|---|
| S-01 | Create `pending`; `total_value` computed | Unit |
| S-02 | `unit_cost < 0` → rejected | Boundary |
| S-03 | `quantity=0` → rejected | Boundary |
| S-04 | Requester self-approval → rejected (SoD) | Negative |
| S-05 | Approve by different user → `approved` | Integration |
| S-06 | Post decrements `on_hand`; creates `StockAdjustment`; sets `posted_at` | Integration |
| S-07 | Post when `on_hand < qty` → raises; no mutation | Negative |
| S-08 | Post when no `StockLevel` row → raises | Negative |
| S-09 | **Concurrent double-post (D-01)** — both pass guard → stock double-decrements | Race / security |
| S-10 | Reject from `pending` → `rejected` | Integration |
| S-11 | Reject from `approved` → `rejected` | Integration |
| S-12 | Post from non-approved → rejected | Negative |
| S-13 | Delete while `posted` → rejected | Negative |
| S-14 | Soft-deleted scrap omitted from list | Integration |
| S-15 | Audit row per approve/reject/post/delete | Regression |
| S-16 | Cross-tenant scrap post → 404 | Security (A01) |

### 3.6 Cross-cutting (X-)

| # | Scenario | Type |
|---|---|---|
| X-01 | Anonymous user hits any view → login redirect | Security (A07) |
| X-02 | Non-admin tenant user hits create/edit/delete → 403 | Security (A01) |
| X-03 | Superuser (tenant=None) gets empty lists | Regression |
| X-04 | Sidebar renders QC submenu | UX |
| X-05 | `python manage.py seed_quality_control` is idempotent | Regression |
| X-06 | `--flush` tears down in FK-safe order | Regression |

---

## 4. Detailed Test Cases (representative — 40+ shown; full matrix tracks per §3)

### 4.1 Checklist

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-CHK-001 | Auto-number on first create | Fresh tenant | POST `/quality-control/checklists/create/` | `{name:'QC1', applies_to:'all', is_mandatory:'on', is_active:'on'}` | 302 to detail; `code='QCC-00001'` | Row persisted, `created_by=request.user`, `tenant=request.tenant` |
| TC-CHK-002 | Duplicate code within tenant rejected | Existing `QCC-TEST` | POST create with same code | `{code:'QCC-TEST', name:'x', applies_to:'all'}` | 200 + `ValidationError` on `code` | No new row |
| TC-CHK-003 | Same code across tenants allowed | Tenant A has `QCC-A`; login as B admin | POST create | `{code:'QCC-A', name:'y', applies_to:'all'}` | 302 | Both tenants retain their row |
| TC-CHK-004 | `applies_to=product` without product rejected | Form load | POST | `{applies_to:'product', product:''}` | 200 + error on `product` | No row |
| TC-CHK-005 | Historical-inactive product on edit (D-04) | Tenant has checklist for product X; X later deactivated | GET + POST `/checklists/<pk>/edit/` | Unchanged data | **Currently:** 200 + `Select a valid choice.` | Row unchanged; user cannot re-save |
| TC-CHK-006 | Cross-tenant detail 404 | A's checklist; login as B admin | GET `/checklists/<pk>/` | — | 404 | Row untouched |
| TC-CHK-007 | Non-admin POST create forbidden | user without `is_tenant_admin` | POST create | Any valid data | 403 | No row |
| TC-CHK-008 | Toggle-active + audit | Checklist active | POST `/toggle-active/` | — | 302; `is_active=False`; `AuditLog` row | Subsequent toggle restores |
| TC-CHK-009 | List query count bounded (D-02) | 50 checklists × 5 items | GET `/checklists/` | — | Queries ≤ const baseline + pagination — **currently fails (linear scaling)** | Rows unchanged |
| TC-CHK-010 | XSS in name rendered escaped | `name='<script>alert(1)</script>'` | GET list + detail | — | Rendered as `&lt;script&gt;` | — |

### 4.2 Inspection Route

| ID | Description | Pre-conditions | Steps | Test Data | Expected |
|---|---|---|---|---|---|
| TC-RTE-001 | QC zone in different warehouse rejected | WH-A/Zone-A; WH-B/Zone-B | POST create | `{source_warehouse:A, qc_zone:B}` | 200 + error on `qc_zone` |
| TC-RTE-002 | Rule `applies_to=product` but product empty — currently accepted (D-08) | Route created | POST edit via formset | `applies_to='product', product=''` | Row saved (defect) |
| TC-RTE-003 | Delete route cascades rules | Route with 3 rules | POST delete | — | 302; 0 rules remain |
| TC-RTE-004 | Route list N+1 (D-02) | 20 routes × 5 rules | GET `/routes/` | — | **Fails budget** — ~20 COUNT subqueries |

### 4.3 Quarantine

| ID | Description | Pre-conditions | Steps | Test Data | Expected |
|---|---|---|---|---|---|
| TC-QUA-001 | `quantity=0` rejected | Form load | POST create | `{quantity:0}` | 200 + error on `quantity` |
| TC-QUA-002 | Zone/warehouse mismatch | WH-A / WH-B | POST create | mismatched | 200 + error on `zone` |
| TC-QUA-003 | Release disposition=scrap auto-creates pending ScrapWriteOff | Active hold | POST `/release/` | `disposition=scrap` | 302; `record.status='scrapped'`; `ScrapWriteOff.pending` row linked |
| TC-QUA-004 | Release from terminal | Released hold | POST `/release/` | any | 302 + error; state unchanged |
| TC-QUA-005 | Delete while `active` soft-deletes | Active hold | POST delete | — | `deleted_at` set; list excludes |
| TC-QUA-006 | Delete while `released` rejected | Released hold | POST delete | — | 302 + error |
| TC-QUA-007 | POST without CSRF | Logged-in, raw POST w/o token | — | — | 403 |

### 4.4 Defect

| ID | Description | Pre-conditions | Steps | Test Data | Expected |
|---|---|---|---|---|---|
| TC-DEF-001 | Create defect with 3 photos | Tenant seeded | POST multipart | 3 small JPEGs | 302; defect + 3 `DefectPhoto` rows |
| TC-DEF-002 | `.exe` renamed `.jpg` | — | POST create with mal file | PE header → `bad.jpg` | Pillow rejects → form invalid on `image` |
| TC-DEF-003 | 5 MB image (D-03) | — | POST multipart | 5 MB JPEG | Currently: Django request cap 2.5 MB → 400/413; should be user-friendly validation |
| TC-DEF-004 | `open → resolved` direct | Open defect | POST `/resolve/` | — | 302; `status='resolved'`; `resolved_*` set |
| TC-DEF-005 | `resolved → open` rejected (terminal) | Resolved defect | POST `/investigate/` | — | 302 + error |
| TC-DEF-006 | Delete while `investigating` rejected | Investigating | POST delete | — | 302 + error |
| TC-DEF-007 | Cross-tenant photo delete | B's photo, login A | POST `/defects/X/photos/Y/delete/` | — | 404 |
| TC-DEF-008 | Filter retention on paginate (D-06) | 50 defects | GET `?severity=critical&page=2` | — | Nav URL should retain `severity=critical` — currently drops |

### 4.5 Scrap

| ID | Description | Pre-conditions | Steps | Test Data | Expected |
|---|---|---|---|---|---|
| TC-SCR-001 | `total_value` auto-computed | `unit_cost=12.5, quantity=4` | POST create | — | `total_value=50.00` |
| TC-SCR-002 | Self-approval rejected | Scrap `requested_by=U` | U POST `/approve/` | — | 302 + error; unchanged |
| TC-SCR-003 | Post decrements on_hand atomically | Approved; on_hand=10, qty=3 | POST `/post/` | — | `on_hand=7`; StockAdjustment row; `posted_at` set |
| TC-SCR-004 | Post when qty > on_hand | on_hand=2, qty=5 | POST `/post/` | — | 302 + error; rolled back |
| TC-SCR-005 | **Concurrent double-post (D-01)** | Approved scrap | 2 simultaneous `/post/` | — | **Expected:** one succeeds, one 302+"already posted". **Current:** both succeed → `on_hand` decremented twice, 2 StockAdjustment rows, scrap overwrites own `posted_at/stock_adjustment` |
| TC-SCR-006 | Reject from `approved` | Approved | POST `/reject/` | — | `status='rejected'` |
| TC-SCR-007 | Delete while `posted` rejected | Posted | POST delete | — | 302 + error |

### 4.6 Cross-cutting

| ID | Description | Expected |
|---|---|---|
| TC-X-001 | Anonymous GET any list | 302 to login |
| TC-X-002 | Non-admin POST create | 403 |
| TC-X-003 | Superuser GET list | 200, empty |
| TC-X-004 | Re-run seeder | Skip existing tenants |
| TC-X-005 | `--flush` + re-seed | Clean slate; no FK orphans |

---

## 5. Automation Strategy

### 5.1 Stack

| Layer | Tool |
|---|---|
| Test runner | `pytest` + `pytest-django` |
| Fixtures | Plain fixtures (match other NavIMS modules — e.g., [stocktaking/tests/conftest.py](../../stocktaking/tests/)) |
| Performance | `django_assert_max_num_queries` |
| Security | `bandit`, `pip-audit` (already in `requirements.txt`) |
| E2E (optional) | Playwright |
| Load (optional) | Locust |

### 5.2 Proposed suite layout

```
quality_control/tests/
├── __init__.py
├── conftest.py                    # tenant / user / product / warehouse / zone / stock_level fixtures
├── test_models.py                 # auto-number, state machines, total_value
├── test_forms.py                  # scope-guard clean(), zone-vs-warehouse, negative qty, D-04 regression
├── test_views_checklists.py
├── test_views_routes.py
├── test_views_quarantine.py
├── test_views_defects.py
├── test_views_scrap.py            # happy path, SoD, D-01 race regression
├── test_security.py               # OWASP A01/A08/A09, CSRF, RBAC
├── test_performance.py            # D-02 N+1 budgets
└── test_regression.py             # bundled test_D<NN>_* guards
```

### 5.3 `conftest.py` — canonical fixtures

```python
# quality_control/tests/conftest.py
import pytest
from core.models import Tenant, User
from catalog.models import Category, Product
from vendors.models import Vendor
from warehousing.models import Warehouse, Zone
from inventory.models import StockLevel


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='Acme QC', slug='acme-qc', is_active=True)


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='Globex QC', slug='globex-qc', is_active=True)


@pytest.fixture
def user(db, tenant):
    return User.objects.create_user(
        username='qc_admin', password='qc_pass_123!',
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username='qc_admin_other', password='qc_pass_123!',
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin(db, tenant):
    return User.objects.create_user(
        username='qc_viewer', password='qc_pass_123!',
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Widgets', slug='widgets')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku='SKU-001', name='Widget A',
        category=category, is_active=True,
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name='Foo', slug='foo')
    return Product.objects.create(
        tenant=other_tenant, sku='SKU-X', name='Foreign Widget',
        category=cat, is_active=True,
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH-1', name='Main', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH-X', name='Foreign', is_active=True,
    )


@pytest.fixture
def qc_zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse,
        name='QC Hold', code='Z-QC', zone_type='quarantine',
    )


@pytest.fixture
def storage_zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse,
        name='Main Storage', code='Z-STO', zone_type='storage',
    )


@pytest.fixture
def stock_level(db, tenant, warehouse, product):
    return StockLevel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product, on_hand=100,
    )


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(tenant=tenant, company_name='Acme Supplies')
```

### 5.4 `test_models.py`

```python
# quality_control/tests/test_models.py
import pytest
from decimal import Decimal
from django.db import IntegrityError
from quality_control.models import (
    QCChecklist, QuarantineRecord, DefectReport, ScrapWriteOff,
)


@pytest.mark.django_db
def test_checklist_autonumbers(tenant, user):
    c1 = QCChecklist.objects.create(tenant=tenant, name='A', applies_to='all', created_by=user)
    c2 = QCChecklist.objects.create(tenant=tenant, name='B', applies_to='all', created_by=user)
    assert c1.code == 'QCC-00001'
    assert c2.code == 'QCC-00002'


@pytest.mark.django_db
def test_checklist_unique_code_per_tenant(tenant, other_tenant, user):
    QCChecklist.objects.create(tenant=tenant, code='QCC-SHARED', name='A', applies_to='all', created_by=user)
    QCChecklist.objects.create(tenant=other_tenant, code='QCC-SHARED', name='B', applies_to='all')
    with pytest.raises(IntegrityError):
        QCChecklist.objects.create(tenant=tenant, code='QCC-SHARED', name='C', applies_to='all')


@pytest.mark.django_db
def test_quarantine_state_machine(tenant, product, warehouse, qc_zone):
    q = QuarantineRecord.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, zone=qc_zone,
        quantity=5, reason='defect',
    )
    assert q.can_transition_to('under_review')
    assert q.can_transition_to('released')
    assert q.can_transition_to('scrapped')
    q.status = 'released'; q.save()
    assert not q.can_transition_to('active')
    assert not q.can_transition_to('under_review')


@pytest.mark.django_db
def test_defect_state_machine(tenant, product, warehouse):
    d = DefectReport.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity_affected=1, description='x',
    )
    assert d.status == 'open'
    assert d.can_transition_to('resolved')
    d.status = 'resolved'; d.save()
    assert not d.can_transition_to('open')


@pytest.mark.django_db
def test_scrap_total_value_computed(tenant, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=4, unit_cost=Decimal('12.5000'), reason='demo',
    )
    assert s.total_value == Decimal('50.00')


@pytest.mark.django_db
def test_scrap_status_mirrors_approval_status(tenant, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=1, reason='x', approval_status='approved',
    )
    assert s.status == 'approved'
    s.approval_status = 'posted'; s.save()
    assert s.status == 'posted'
```

### 5.5 `test_forms.py`

```python
# quality_control/tests/test_forms.py
import pytest
from quality_control.forms import (
    QCChecklistForm, InspectionRouteForm, QuarantineRecordForm, ScrapWriteOffForm,
)
from warehousing.models import Zone


@pytest.mark.django_db
@pytest.mark.parametrize('applies_to, fk_field', [
    ('product', 'product'), ('vendor', 'vendor'), ('category', 'category'),
])
def test_checklist_requires_scope_fk(tenant, applies_to, fk_field):
    form = QCChecklistForm(
        data={'name': 'X', 'applies_to': applies_to, 'is_mandatory': 'on'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert fk_field in form.errors


@pytest.mark.django_db
def test_route_qc_zone_must_belong_to_warehouse(tenant, warehouse, other_tenant):
    other_wh = other_tenant.warehouses.create(code='WH-X', name='X', is_active=True)
    alien_zone = Zone.objects.create(tenant=other_tenant, warehouse=other_wh, name='Z', code='Z', zone_type='quarantine')
    form = InspectionRouteForm(
        data={'name': 'R', 'source_warehouse': warehouse.pk, 'qc_zone': alien_zone.pk,
              'priority': 100, 'is_active': 'on'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'qc_zone' in form.errors


@pytest.mark.django_db
def test_quarantine_quantity_positive(tenant, product, warehouse, qc_zone):
    form = QuarantineRecordForm(
        data={'product': product.pk, 'warehouse': warehouse.pk, 'zone': qc_zone.pk,
              'quantity': 0, 'reason': 'defect'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'quantity' in form.errors


@pytest.mark.django_db
def test_scrap_unit_cost_non_negative(tenant, product, warehouse):
    form = ScrapWriteOffForm(
        data={'product': product.pk, 'warehouse': warehouse.pk,
              'quantity': 1, 'unit_cost': '-1.0', 'reason': 'x'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'unit_cost' in form.errors


@pytest.mark.django_db
def test_D04_checklist_edit_after_product_deactivated(tenant, user, product):
    """D-04 regression: deactivating a product must not break edit of historical checklist."""
    from quality_control.models import QCChecklist
    c = QCChecklist.objects.create(
        tenant=tenant, name='hist', applies_to='product', product=product, created_by=user,
    )
    product.is_active = False; product.save()
    form = QCChecklistForm(
        data={'code': c.code, 'name': c.name, 'applies_to': 'product',
              'product': product.pk, 'is_mandatory': 'on', 'is_active': 'on'},
        instance=c, tenant=tenant,
    )
    assert form.is_valid(), form.errors
```

### 5.6 `test_views_scrap.py` (includes the D-01 race guard)

```python
# quality_control/tests/test_views_scrap.py
import pytest
from decimal import Decimal
from django.urls import reverse
from quality_control.models import ScrapWriteOff
from inventory.models import StockAdjustment


@pytest.mark.django_db
def test_scrap_post_decrements_stock(client_logged_in, tenant, user, product, warehouse, stock_level):
    scrap = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=3, unit_cost=Decimal('10.00'), reason='x',
        approval_status='approved', requested_by=user,
    )
    resp = client_logged_in.post(reverse('quality_control:scrap_post', args=[scrap.pk]))
    assert resp.status_code == 302
    scrap.refresh_from_db(); stock_level.refresh_from_db()
    assert scrap.approval_status == 'posted'
    assert stock_level.on_hand == 97
    assert scrap.stock_adjustment is not None
    assert scrap.stock_adjustment.adjustment_type == 'decrease'


@pytest.mark.django_db
def test_scrap_post_insufficient_stock_rolls_back(client_logged_in, tenant, user, product, warehouse, stock_level):
    stock_level.on_hand = 1; stock_level.save()
    scrap = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=5, unit_cost=1, reason='x',
        approval_status='approved', requested_by=user,
    )
    resp = client_logged_in.post(reverse('quality_control:scrap_post', args=[scrap.pk]))
    assert resp.status_code == 302
    scrap.refresh_from_db(); stock_level.refresh_from_db()
    assert scrap.approval_status == 'approved'
    assert stock_level.on_hand == 1
    assert not StockAdjustment.objects.exists()


@pytest.mark.django_db
def test_scrap_self_approval_forbidden(client_logged_in, tenant, user, product, warehouse):
    scrap = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=1, reason='x', requested_by=user,
    )
    client_logged_in.post(reverse('quality_control:scrap_approve', args=[scrap.pk]))
    scrap.refresh_from_db()
    assert scrap.approval_status == 'pending'


@pytest.mark.django_db(transaction=True)
def test_D01_scrap_post_concurrent_double_post_is_guarded(user, product, warehouse, tenant, stock_level):
    """D-01 regression: concurrent POST /scrap/<pk>/post/ must not decrement on_hand twice."""
    import threading
    from django.test import Client
    scrap = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=2, unit_cost=1, reason='x',
        approval_status='approved', requested_by=user,
    )
    stock_level.refresh_from_db()
    initial = stock_level.on_hand
    results = []

    def post():
        c = Client(); c.force_login(user)
        r = c.post(reverse('quality_control:scrap_post', args=[scrap.pk]))
        results.append(r.status_code)

    threads = [threading.Thread(target=post) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    stock_level.refresh_from_db()
    assert stock_level.on_hand == initial - scrap.quantity, (
        f'Expected single decrement; got on_hand={stock_level.on_hand} (initial={initial})'
    )
    assert StockAdjustment.objects.filter(stock_level=stock_level).count() == 1
```

### 5.7 `test_security.py` (OWASP-mapped)

```python
# quality_control/tests/test_security.py
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from quality_control.models import QCChecklist, DefectReport, ScrapWriteOff


@pytest.mark.django_db
class TestA01AccessControl:
    def test_cross_tenant_checklist_detail_404(self, client, user, other_tenant):
        c = QCChecklist.objects.create(tenant=other_tenant, name='x', applies_to='all')
        client.force_login(user)
        r = client.get(reverse('quality_control:checklist_detail', args=[c.pk]))
        assert r.status_code == 404

    def test_non_admin_create_forbidden(self, client, non_admin):
        client.force_login(non_admin)
        r = client.post(reverse('quality_control:checklist_create'),
                        data={'name': 'X', 'applies_to': 'all'})
        assert r.status_code in (302, 403)


@pytest.mark.django_db
class TestA08FileUpload:
    def test_defect_photo_rejects_non_image(self, client_logged_in, tenant, product, warehouse):
        defect = DefectReport.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity_affected=1, description='x',
        )
        bad = SimpleUploadedFile('malicious.jpg', b'not-a-jpeg', content_type='image/jpeg')
        client_logged_in.post(
            reverse('quality_control:defect_edit', args=[defect.pk]),
            data={'product': product.pk, 'warehouse': warehouse.pk,
                  'quantity_affected': 1, 'defect_type': 'visual', 'severity': 'minor',
                  'source': 'receiving', 'description': 'x',
                  'photos-TOTAL_FORMS': '1', 'photos-INITIAL_FORMS': '0',
                  'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '1000',
                  'photos-0-image': bad, 'photos-0-caption': ''},
            format='multipart',
        )
        assert DefectReport.objects.get(pk=defect.pk).photos.count() == 0

    def test_defect_photo_size_cap(self):
        pytest.skip('D-03 remediation pending')


@pytest.mark.django_db
class TestA09Audit:
    def test_checklist_create_emits_audit(self, client_logged_in, tenant):
        from core.models import AuditLog
        before = AuditLog.objects.count()
        client_logged_in.post(
            reverse('quality_control:checklist_create'),
            data={'name': 'Audit test', 'applies_to': 'all', 'is_mandatory': 'on', 'is_active': 'on'},
        )
        assert AuditLog.objects.count() == before + 1
        entry = AuditLog.objects.latest('id')
        assert entry.action == 'create' and entry.model_name == 'QCChecklist'


@pytest.mark.django_db
class TestCSRF:
    def test_scrap_approve_requires_post(self, client_logged_in, tenant, product, warehouse):
        scrap = ScrapWriteOff.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, unit_cost=1, reason='x',
        )
        r = client_logged_in.get(reverse('quality_control:scrap_approve', args=[scrap.pk]))
        assert r.status_code == 405
```

### 5.8 `test_performance.py`

```python
# quality_control/tests/test_performance.py
import pytest
from django.urls import reverse
from quality_control.models import QCChecklist, QCChecklistItem, InspectionRoute


@pytest.mark.django_db
def test_D02_checklist_list_no_n_plus_one(client_logged_in, django_assert_max_num_queries, tenant, user):
    for i in range(30):
        c = QCChecklist.objects.create(tenant=tenant, name=f'C{i}', applies_to='all', created_by=user)
        for j in range(5):
            QCChecklistItem.objects.create(tenant=tenant, checklist=c, sequence=j, check_name=f'c{j}', check_type='visual')
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse('quality_control:checklist_list'))
        assert r.status_code == 200


@pytest.mark.django_db
def test_D02_route_list_no_n_plus_one(client_logged_in, django_assert_max_num_queries, tenant, warehouse, qc_zone):
    for i in range(20):
        InspectionRoute.objects.create(tenant=tenant, name=f'R{i}', source_warehouse=warehouse, qc_zone=qc_zone)
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse('quality_control:route_list'))
        assert r.status_code == 200
```

---

## 6. Defects, Risks & Recommendations

### 6.1 Defect register (verified unless marked CANDIDATE)

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-01** | **High** | A04 / A01 | [quality_control/views.py:686-722](../../quality_control/views.py#L686-L722) (`scrap_post_view`) | Two concurrent POSTs to `/scrap/<pk>/post/` both pass the `if obj.approval_status != 'approved'` guard (in-memory read from before the atomic block). After the first commits, the second still holds `approval_status='approved'` locally, re-enters the block, locks the now-updated StockLevel, and decrements `on_hand` a **second time** — producing a duplicate `StockAdjustment` and overwriting `scrap.stock_adjustment` + `posted_at`. **Verified**: no `select_for_update()` on `ScrapWriteOff`, no `refresh_from_db()` inside the atomic block. | Inside `transaction.atomic()`, re-fetch: `obj = ScrapWriteOff.objects.select_for_update().get(pk=obj.pk)` and re-assert `approval_status == 'approved'`. Abort with a user message otherwise. Add threaded regression `TC-SCR-005`. |
| **D-02** | Medium | A04 / performance | [templates/quality_control/checklist_list.html:43](../../templates/quality_control/checklist_list.html#L43) (`{{ c.items.count }}`), [templates/quality_control/route_list.html:45](../../templates/quality_control/route_list.html#L45) (`{{ r.rules.count }}`) | N+1 on list views. **Verified**: 3 checklists → 8 queries; 18 checklists → 23 queries (linear scaling). | In the view, `qs.annotate(item_count=Count('items'))` and `qs.annotate(rule_count=Count('rules'))`; render the annotation in the template. Add `test_D02_*_no_n_plus_one` performance guards. |
| **D-03** | Medium | A08 | [quality_control/models.py:399-401](../../quality_control/models.py#L399-L401) (`DefectPhoto.image`), [quality_control/forms.py:310-322](../../quality_control/forms.py#L310-L322) | `ImageField` relies on Django's 2.5 MB request cap + Pillow magic-byte check. No explicit per-image size validator, no MIME/extension whitelist, no SVG exclusion, no filename sanitisation. Allows 2.5 MB polyglots and repeated uploads. | Add validators: `FileExtensionValidator(['jpg','jpeg','png','gif','webp'])`, custom `validate_image_size` (≤ 5 MB), and `clean_image()` in `DefectPhotoForm` re-reading the first 16 bytes to reject known-bad signatures. Set an explicit `FILE_UPLOAD_MAX_MEMORY_SIZE` in settings. |
| **D-04** | Medium | A04 / UX | [quality_control/forms.py:57-60](../../quality_control/forms.py#L57-L60), [forms.py:260-262](../../quality_control/forms.py#L260-L262), [forms.py:294-295](../../quality_control/forms.py#L294-L295), [forms.py:327-329](../../quality_control/forms.py#L327-L329) | Form querysets filter `Product.objects.filter(tenant=tenant, is_active=True)`. **Verified**: deactivating a product breaks edit of its historical checklist with `"Select a valid choice."` Same pattern applies across routes / quarantine / defect / scrap. | In `__init__`, union the currently-selected value: `qs = Product.objects.filter(tenant=tenant, is_active=True)`; `if self.instance.pk and self.instance.product_id: qs = qs \| Product.objects.filter(pk=self.instance.product_id)`. Apply to every active-filtered FK. |
| **D-05** | Low | — | [quality_control/models.py:453-459](../../quality_control/models.py#L453-L459) (`ScrapWriteOff.VALID_TRANSITIONS`), [quality_control/views.py:425-471](../../quality_control/views.py#L425-L471) (`quarantine_release_view`) | `ScrapWriteOff` inherits `StateMachineMixin` and declares `VALID_TRANSITIONS`, but no view calls `can_transition_to()`. All scrap state changes use inline `if obj.approval_status != X` checks. Similarly `quarantine_release_view` bypasses `can_transition_to`. Dead code + drift from `barcode_rfid`/`returns` convention. | Route every write through `can_transition_to()`: `if not obj.can_transition_to(new): abort`. Keeps `VALID_TRANSITIONS` authoritative. |
| **D-06** | Medium | UX | all `*_list.html` `<a href="?page=N">` links | Paginator drops current filter GET params. Consistent with older modules but against CLAUDE.md filter-retention rules. | Introduce a `{% querystring page=N %}` template tag (or inline helper); keep all non-page GET params across pagination. Propagate fix across modules. |
| **D-07** | Low | Data integrity | [quality_control/forms.py:306-329](../../quality_control/forms.py#L306-L329) (`DefectReportForm`) | `lot` / `serial` / `grn` / `quarantine_record` querysets filter only by `tenant`, not by `product`. A user can link a defect to a lot/serial that belongs to a different product. | Add `clean()` cross-validation: `lot.product_id == cleaned['product'].pk`, `serial.product_id == cleaned['product'].pk`. |
| **D-08** | Low | Data integrity | [quality_control/models.py:196-210](../../quality_control/models.py#L196-L210) (`InspectionRouteRule`) | `applies_to='product'` but `product` FK is nullable — no guard ensures it's populated when scope demands it. | Add `clean()` to `InspectionRouteRuleForm` mirroring `QCChecklistForm.clean()` scope logic. |
| **D-09** | Low | Consistency | [quality_control/views.py:678-679](../../quality_control/views.py#L678-L679) | `scrap_post_view` audit record says only `'approved->posted'`. The resulting `StockAdjustment.adjustment_number` is not captured in the payload. | `emit_audit(request, 'post', obj, changes=f'approved->posted; adj={adjustment.adjustment_number}; on_hand {prev}->{new}')`. |
| **D-10** | Info | A05 | [config/settings.py:76-85](../../config/settings.py#L76-L85) | `manage.py migrate` emits `mysql.W002 MariaDB Strict Mode is not set`. Not module-specific but surfaces on every QC-module CI run. | Add `'OPTIONS': {'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"}` to `DATABASES['default']`. |
| D-11 (CANDIDATE) | Low | — | [quality_control/views.py:598-606](../../quality_control/views.py#L598-L606) (`defect_photo_delete_view`) | Photo delete succeeds regardless of parent defect status; UI hides the button but no server-side guard. May be intentional (evidence-management). | Confirm intent. If block is desired post-resolution: gate with `if defect.status in ('open','investigating')`; otherwise leave but document. |

### 6.2 Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Concurrent scrap post double-decrements on_hand | Medium | High — financial / inventory integrity | Fix D-01 + regression TC-SCR-005 |
| R-02 | N+1 degrades UX at 1k+ rows | High at scale | Medium | Fix D-02; enforce query budget |
| R-03 | Malicious image upload | Low | Medium — disk fill / polyglot | Fix D-03 with size + MIME whitelist |
| R-04 | Product deactivation bricks historical QC docs | Medium | Medium — ops need to re-activate to edit | Fix D-04 (queryset union with current FK) |
| R-05 | No automated test suite — regressions land silently | High until tests ship | Medium | Implement §5 suite; gate PRs on `pytest quality_control/tests` |

### 6.3 Strengths (keep doing)

- Tenant scoping at every query site — IDOR probe verified safe on sampled paths.
- RBAC + CSRF + audit triad consistently applied on every mutation endpoint.
- Segregation-of-duties on `scrap_approve_view`.
- Scrap posting uses `apply_adjustment()` — the canonical single write path shared with `stocktaking` and `returns`. Good architectural discipline.
- Soft-delete with `deleted_at` + list-filter on top-level docs — matches `returns/` convention.
- Idempotent seeder with `--flush`, per-tenant skip, and warehouse-missing fallback.

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets per file

| File | LoC | Target branch coverage |
|---|---|---|
| `models.py` | ~500 | ≥ 95% |
| `forms.py` | ~330 | ≥ 90% |
| `views.py` | ~715 | ≥ 85% |
| `management/commands/seed_quality_control.py` | ~200 | ≥ 70% (idempotency + flush paths) |

### 7.2 KPI thresholds

| KPI | Green | Amber | Red |
|---|---|---|---|
| `pytest quality_control/tests` pass rate | 100 % | ≥ 95 % | < 95 % |
| Open **Critical** defects | 0 | 0 | ≥ 1 |
| Open **High** defects | 0 | ≤ 1 | ≥ 2 |
| Suite runtime | < 10 s | < 30 s | ≥ 30 s |
| p95 latency on list views (Locust, 50 rps) | < 200 ms | < 400 ms | ≥ 400 ms |
| Max queries per list view (`django_assert_max_num_queries`) | ≤ 8 | ≤ 12 | > 12 |
| OWASP A01 / A08 / A09 findings | 0 | 0 | ≥ 1 |

### 7.3 Release Exit Gate — all must be TRUE

- [ ] Zero **Critical**, zero **High** open defects (currently D-01 High → **blocked**).
- [ ] `pytest quality_control/tests` passes at 100 %.
- [ ] All §5 test files exist and are referenced in CI.
- [ ] Every OWASP category in §2.1 has at least one assertion or documented dismissal.
- [ ] Seed command is idempotent on a clean DB and on a re-run.
- [ ] List views stay within query budget.
- [ ] Scrap-post thread-safety test (TC-SCR-005) green.
- [ ] D-03 (upload hygiene) remediated or accepted with written risk sign-off.
- [ ] README Module 16 test-coverage row updated with the final test count.

---

## 8. Summary

**Module 16 is functionally complete and architecturally aligned with the codebase** — multi-tenant, RBAC-gated, audit-logged, soft-deleted, with a canonical stock write path through `StockAdjustment.apply_adjustment()`. Smoke-testing confirms all 35 views render / transition cleanly.

**Ship-blocker (1):**
- **D-01** concurrent scrap-post race — High, verified, fix is a two-line addition inside the atomic block.

**Should-fix before production traffic (3):**
- **D-02** N+1 on `checklist_list` / `route_list` — Medium, verified, straightforward `annotate(Count(...))` fix.
- **D-03** Defect-photo upload hygiene — Medium, closes OWASP A08 surface.
- **D-04** `is_active=True` queryset trap on edit — Medium, verified, one-line `qs | pk_filter` union in each form `__init__`.

**Nice-to-have (6):** D-05 through D-10 + D-11 candidate — consistency and data-integrity polish.

**Automated test suite is not yet in place.** The §5 scaffolding is ready to paste in; priority tests are `test_D01_...` (scrap race), `test_D02_...` (N+1 budgets), and the `test_security.py` OWASP matrix. Recommended first wave: conftest + test_models + test_forms + test_views_scrap + test_security → approx 40 tests, ~1 hour to implement, matches the coverage depth of `stocktaking/` / `returns/`.

**Recommendation:** Land D-01 fix + regression test before any user acceptance testing. Bundle D-02 / D-03 / D-04 + the initial automated suite into a single hardening PR. D-05 through D-11 can ride a later refactor.
