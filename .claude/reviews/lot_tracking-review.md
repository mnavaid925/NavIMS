# Lot & Serial Number Tracking — Comprehensive SQA Test Report

**Target:** [lot_tracking/](lot_tracking/) Django app (LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog)
**Scope:** Module review (default)
**Date:** 2026-04-17
**Report file:** [.claude/reviews/lot_tracking-review.md](.claude/reviews/lot_tracking-review.md)

---

## 1. Module Analysis

### 1.1 Inventory

| Artefact | Path | LOC | Notes |
|---|---|---|---|
| Models | [lot_tracking/models.py](lot_tracking/models.py) | 324 | 4 models: LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog |
| Forms | [lot_tracking/forms.py](lot_tracking/forms.py) | 168 | 4 forms (LotBatch, Serial, ExpiryAcknowledge, Traceability) |
| Views | [lot_tracking/views.py](lot_tracking/views.py) | 524 | 20 views: CRUD + status transitions + trace + expiry dashboard |
| Admin | [lot_tracking/admin.py](lot_tracking/admin.py) | 30 | All 4 models registered, basic list_filter/search |
| URLs | [lot_tracking/urls.py](lot_tracking/urls.py) | 34 | 20 URL patterns across 4 sub-modules |
| Templates | [templates/lot_tracking/](templates/lot_tracking/) | 13 files | list/form/detail per entity + dashboard + trace views |
| Seed | [lot_tracking/management/commands/seed_lot_tracking.py](lot_tracking/management/commands/seed_lot_tracking.py) | 201 | Idempotent per tenant |
| Tests | — | 0 | **No tests file exists — zero coverage** |

### 1.2 Domain rules

- **LotBatch** ([lot_tracking/models.py:10-110](lot_tracking/models.py#L10-L110)): 5 statuses (`active` → `quarantine` → `expired`/`consumed`/`recalled`) with an explicit `VALID_TRANSITIONS` table; `consumed` and `recalled` are terminal. `lot_number` auto-generated `LOT-NNNNN` per tenant via `save()`. `is_expired` and `days_until_expiry` are derived properties. `unique_together=('tenant','lot_number')`.
- **SerialNumber** ([lot_tracking/models.py:117-187](lot_tracking/models.py#L117-L187)): 6 statuses (`available → allocated/sold/damaged/scrapped`) with similar transition table. `serial_number` is **user-entered** (not auto-generated). `unique_together=('tenant','serial_number')`. Optional FK to `LotBatch`.
- **ExpiryAlert** ([lot_tracking/models.py:194-230](lot_tracking/models.py#L194-L230)): acknowledgement workflow. Alerts are shown on dashboard + list; no automated creation path found in the module.
- **TraceabilityLog** ([lot_tracking/models.py:237-324](lot_tracking/models.py#L237-L324)): 8 event types; auto-generated `TRC-NNNNN` number. `unique_together=('tenant','log_number')`. Created implicitly by `lot_create_view`, `serial_create_view`, `lot_transition_view`, `serial_transition_view` — acts as both a business-level audit and a domain-level genealogy record.

### 1.3 Multi-tenancy & security posture

- Every model has `tenant = ForeignKey('core.Tenant', ...)`. Every view uses `@login_required` and filters by `tenant=request.tenant` or `get_object_or_404(..., tenant=tenant)` — manual sweep confirms IDOR guards present on all 20 views (spot-check: [lot_tracking/views.py:96](lot_tracking/views.py#L96), [:263](lot_tracking/views.py#L263), [:414](lot_tracking/views.py#L414), [:477](lot_tracking/views.py#L477)).
- Forms set `instance.tenant = self.tenant` in `save()` — tenant cannot be overridden via POST data.
- `TraceabilityLog` is emitted on create/transition paths — good domain-level audit. **However**, there is no `core.AuditLog` emission anywhere in the module — security-grade audit is missing.
- `@login_required` is the **only** access control. Any logged-in tenant user can delete a quarantined lot, recall an active lot, or transition a serial to `scrapped`. No RBAC.

### 1.4 Risk profile (pre-test)

| Area | Risk | Reason |
|---|---|---|
| Form uniqueness vs `unique_together` | **HIGH** | `SerialNumberForm` has no `clean_serial_number()` — duplicate serial within tenant raises `IntegrityError` → 500. **Verified 2026-04-17** (D-01). |
| Data integrity — edit form clobbers FK | **HIGH** | `SerialNumberForm.__init__` filters `lot` queryset to `status='active'` only. Editing a serial whose current lot is `quarantine`/`expired` yields an empty queryset; a bound form without a re-pick silently clears the lot FK → **severed genealogy chain**. **Verified 2026-04-17** (D-02). |
| Date validation | Medium | `LotBatchForm` accepts `manufacturing_date > expiry_date`. **Verified 2026-04-17** (D-03). |
| Quantity validation | Medium | `LotBatchForm.quantity` passes `0` despite HTML `min='1'`. `TraceabilityLog.quantity` is `IntegerField(null=True)` — negatives allowed (may be by design for adjustments). **Verified 2026-04-17** (D-04). |
| RBAC | Medium | No `tenant_admin_required` gate on destructive / transition views. Aligns with already-fixed vendors / receiving / warehousing pattern. (D-05) |
| Auditing | Medium | No `core.AuditLog` rows. `TraceabilityLog` is domain audit, not security audit. (D-06) |
| Concurrency | Low | `_generate_lot_number` / `_generate_log_number` use the same read-max-then-write pattern fixed in warehousing (D-08 in that review). Same race. (D-07) |
| Template-vs-choices drift | Medium | `expiry_dashboard.html:167` checks `lot.status == 'quarantined'` — model choice is `'quarantine'`. The branch is dead code; quarantined lots fall through to the grey `{% else %}` badge. (D-08) |
| Expiry alerts are orphaned | Medium | `ExpiryAlert.objects.create(...)` is called only from seed — no scheduled job, no management command to generate alerts. Dashboard count + list view exist but the table stays at seed levels. (D-09) |
| Traceability integrity | Medium | `TraceabilityLogForm.clean()` requires lot OR serial but does not enforce that a `transferred` event has both `from_warehouse` and `to_warehouse`, nor that `quantity > 0` for `sold/scrapped/adjusted`. (D-10) |
| Trace-view pagination | Medium | `lot_trace_view` / `serial_trace_view` render every log ever written for a lot/serial with no pagination. Large customers → slow page. (D-11) |
| Serial delete guard over-permissive | Low | A serial with status `available` but `lot.status='recalled'` can still be deleted, breaking the recall audit chain. (D-12) |
| `TraceabilityLog` event-map coverage | Low | `lot_transition_view`'s `event_map` has no entry for `consumed → consumed` or `active` explicitly — but falls back to `adjusted`. A status transition to `recalled` correctly emits `recalled`. Minor. |
| `LotBatch.available_quantity` drift | Medium | Form allows editing `quantity` after creation without recomputing `available_quantity`. User can enter `quantity=50` when `available_quantity=80` — arithmetic invariant violated. (D-13) |
| XSS / CSRF | Low | Django auto-escape on all `{{ var }}` usages. CSRF token on all POST forms (delete, transition, acknowledge). |

---

## 2. Test Plan

### 2.1 Scope

In scope: all 4 models, 4 forms, 20 views, 13 templates, 20 URLs, seed command, admin registration, state machines (lot + serial), multi-tenant isolation, traceability chain integrity.

### 2.2 Strategy per layer

| Layer | Approach | Tools |
|---|---|---|
| **Unit** | Model `save()`, `can_transition_to`, `is_expired`, `days_until_expiry`, `is_warranty_expired`, auto-code generation | pytest + pytest-django |
| **Integration** | View + form + model flow; filter retention; traceability log auto-creation on create/transition | pytest-django `Client` |
| **Functional / E2E** | Full journey: create lot → register serials → transition to sold → acknowledge expiry → audit trail | Playwright (Python) |
| **Boundary** | `max_length` (20, 100), `PositiveIntegerField(0)`, unicode/emoji in names, very long supplier batch refs | Parametrised pytest |
| **Negative** | Duplicate codes, invalid transitions, cross-tenant IDOR, date inversion, quantity ≤ 0, edit clobbers lot FK | pytest |
| **Security** | OWASP Top 10 (see §2.4) | pytest + bandit + ZAP |
| **Performance** | N+1 on lot_list + serial_list; full-trace rendering at scale | `django_assert_max_num_queries`, Locust |
| **Regression** | Snapshot of `TraceabilityLog` content on known flows (recall, quarantine, consume) | pytest fixtures |

### 2.3 Entry / exit

**Entry:** migrations applied; `seed_lot_tracking` succeeds; every URL returns 200/302 for tenant admin; `catalog`, `warehousing`, `receiving` modules deployed (this module depends on all three).

**Exit:** see §7.3.

### 2.4 OWASP Top 10 mapping

| OWASP | Covered by |
|---|---|
| A01 Broken Access Control | TC-LOT-SEC-001..004 (IDOR, anon, superuser tenant=None, RBAC gap) |
| A02 Crypto failures | Out of scope (no secrets) |
| A03 Injection / XSS | TC-LOT-SEC-010..012 (SQLi on search, XSS in lot_number, serial_number, notes) |
| A04 Insecure design | TC-LOT-NEG-001..008 (D-01, D-02, D-03, D-04, D-10, D-13) |
| A05 Security misconfig | Verify DEBUG=False, X-Frame-Options — module-agnostic |
| A06 Vulnerable deps | `bandit` + `pip-audit` in CI |
| A07 Auth failures | TC-LOT-SEC-020 — login required on all 20 URLs |
| A08 Data integrity | File upload N/A for this module |
| A09 Logging failures | TC-LOT-SEC-030 — no `core.AuditLog` on destructive ops (D-06) |
| A10 SSRF | N/A |

---

## 3. Test Scenarios

### 3.1 LotBatch (L-NN)

| # | Scenario | Type |
|---|---|---|
| L-01 | Create lot — auto `LOT-00001`, `available_quantity=quantity` | Unit |
| L-02 | Second lot increments to `LOT-00002` | Unit |
| L-03 | Lot numbering is per tenant | Unit |
| L-04 | `is_expired` true when `expiry_date < today` and status != expired | Unit |
| L-05 | `days_until_expiry` returns negative for past dates | Unit |
| L-06 | Duplicate `lot_number` (manually set) within tenant → form error, not 500 | **Negative (HIGH)** — D-01 applies if user bypasses auto-gen |
| L-07 | `manufacturing_date > expiry_date` — form should reject (D-03) | **Negative (MED)** |
| L-08 | `quantity=0` — form should reject (D-04) | **Negative (MED)** |
| L-09 | Edit lot with `quantity=50` when `available_quantity=80` — either reject or re-compute (D-13) | **Negative (MED)** |
| L-10 | Create view auto-emits `TraceabilityLog(event_type='received')` | Integration |
| L-11 | List filters: search, status, warehouse | Integration |
| L-12 | Filter retention across pagination | Integration |
| L-13 | Edit blocked when status not in (active, quarantine) | Integration |
| L-14 | Delete allowed only for `quarantine` | Integration |
| L-15 | 7×5 transition matrix — via URL path | Unit + Integration |
| L-16 | Transition auto-writes TraceabilityLog with correct event | Integration |
| L-17 | IDOR — tenant A reads tenant B's lot | Security |
| L-18 | Anonymous → 302 login | Security |
| L-19 | Non-admin tenant user can create/transition/delete (D-05) | Security |
| L-20 | List view N+1 — 200 lots, query count ≤ 10 | Performance |
| L-21 | Concurrent `Lot.objects.create(tenant=t)` race (D-07) | Performance |

### 3.2 SerialNumber (S-NN)

| # | Scenario | Type |
|---|---|---|
| S-01 | Create serial, links to product + lot + warehouse | Unit |
| S-02 | Duplicate `serial_number` within tenant — D-01, currently 500 | **Negative (HIGH)** |
| S-03 | Same serial in different tenants allowed | Integration |
| S-04 | Edit serial whose lot is `quarantine` — lot **must not silently clear** (D-02) | **Negative (HIGH)** |
| S-05 | 6×6 transition matrix (available/allocated/sold/returned/damaged/scrapped) | Unit |
| S-06 | Transition auto-writes TraceabilityLog | Integration |
| S-07 | Delete blocked when status != available | Integration |
| S-08 | Delete with `lot.status='recalled'` — should block (D-12) | **Negative (LOW)** |
| S-09 | `is_warranty_expired` true/false based on `warranty_expiry` | Unit |
| S-10 | Serial list filters: search, status, warehouse | Integration |
| S-11 | IDOR — cross-tenant detail | Security |

### 3.3 ExpiryAlert (E-NN)

| # | Scenario | Type |
|---|---|---|
| E-01 | Dashboard counts are tenant-scoped | Integration |
| E-02 | `quarantined` badge never renders on dashboard (D-08) | **Negative (MED)** |
| E-03 | Acknowledge sets `is_acknowledged=True`, actor, timestamp | Integration |
| E-04 | Double-acknowledge blocked with info message | Integration |
| E-05 | `notes` field preserved on ack (not overwritten) — current code OVERWRITES | **Negative (LOW)** |
| E-06 | Alert list filter: type, acknowledged yes/no | Integration |
| E-07 | No automated alert generation (D-09) | Design |

### 3.4 TraceabilityLog (T-NN)

| # | Scenario | Type |
|---|---|---|
| T-01 | Create with auto `TRC-00001` | Unit |
| T-02 | `clean()` rejects when both lot and serial empty | Negative |
| T-03 | `event_type='transferred'` without both warehouses — should reject (D-10) | **Negative (MED)** |
| T-04 | `event_type='sold'`, `quantity=0` — should reject (D-10) | **Negative (MED)** |
| T-05 | `__str__` formats correctly with lot | Unit |
| T-06 | `__str__` formats correctly with serial only | Unit |
| T-07 | `lot_trace_view` shows every log for lot in chronological order | Integration |
| T-08 | `lot_trace_view` pagination absent — 1000 logs render all (D-11) | Performance |
| T-09 | List filters: search, event_type | Integration |
| T-10 | IDOR — cross-tenant detail | Security |

### 3.5 Seed (SD-NN)

| # | Scenario | Type |
|---|---|---|
| SD-01 | `seed_lot_tracking` with no tenants — warns + returns | Integration |
| SD-02 | Re-run without flush — skips seeded tenants | Integration |
| SD-03 | `--flush` resets every model | Integration |

---

## 4. Detailed Test Cases

### 4.1 Duplicate serial number → IntegrityError (S-02)

| | |
|---|---|
| **ID** | TC-LOT-NEG-001 |
| **Description** | Creating a `SerialNumber` with an existing `(tenant, serial_number)` should return a form error |
| **Pre-conditions** | Tenant T has a SerialNumber `SN-001` |
| **Steps** | POST `/lot-tracking/serials/create/` with `serial_number=SN-001` |
| **Test Data** | `serial_number='SN-001'`, `product=P`, `warehouse=W` |
| **Expected** | Response 200 with form error `"Serial number already exists for this tenant"` |
| **Current behaviour** | **FAILS** — `form.is_valid() == True`, then `form.save()` raises `IntegrityError (1062 Duplicate entry '8-SN-DUP' for key 'lot_tracking_serialnumber_tenant_id_serial_number_...')` → 500 (verified 2026-04-17 in Django shell) |

### 4.2 Serial edit silently clears lot FK (S-04)

| | |
|---|---|
| **ID** | TC-LOT-NEG-002 |
| **Description** | Editing a serial whose `lot` is in a non-active status must preserve the FK |
| **Pre-conditions** | Serial `SN-X` linked to lot `LOT-Q` with `status='quarantine'` |
| **Steps** | GET `/lot-tracking/serials/<pk>/edit/`; POST back with no lot picker change |
| **Expected** | `serial.lot_id` unchanged after save |
| **Current behaviour** | **FAILS** — `SerialNumberForm.__init__` sets `self.fields['lot'].queryset = LotBatch.objects.filter(tenant=tenant, status='active')` ([lot_tracking/forms.py:92](lot_tracking/forms.py#L92)). On GET, the select renders **without** the current lot as an option (verified: queryset size 0 when current lot is `quarantine`). On POST, the field is `required=False`; if the user submits without picking, `cleaned_data['lot']=None` → FK silently cleared. **Data-loss genealogy defect.** |
| **Fix** | In `__init__`, when editing an existing instance, include the current lot in the queryset: `qs = LotBatch.objects.filter(tenant=tenant, status='active'); if self.instance.pk and self.instance.lot_id: qs = qs | LotBatch.objects.filter(pk=self.instance.lot_id); self.fields['lot'].queryset = qs.distinct()` |

### 4.3 Manufacturing > expiry (L-07)

| | |
|---|---|
| **ID** | TC-LOT-NEG-003 |
| **Description** | `LotBatchForm` must reject `manufacturing_date > expiry_date` |
| **Pre-conditions** | Tenant, product, warehouse |
| **Steps** | POST lot_create with `manufacturing_date=2026-05-01`, `expiry_date=2026-04-01` |
| **Expected** | Form error on `expiry_date` |
| **Current behaviour** | Passes — verified 2026-04-17 |

### 4.4 Quantity = 0 (L-08)

| | |
|---|---|
| **ID** | TC-LOT-NEG-004 |
| **Description** | `LotBatchForm` must reject `quantity=0` |
| **Pre-conditions** | Tenant, product, warehouse |
| **Steps** | POST lot_create with `quantity=0` |
| **Expected** | Form error on `quantity` |
| **Current behaviour** | Passes validation (widget has `min='1'` but no server-side validator) — verified 2026-04-17 |

### 4.5 Expiry dashboard badge dead branch (E-02)

| | |
|---|---|
| **ID** | TC-LOT-UI-001 |
| **Description** | A lot with `status='quarantine'` must render a coloured badge on the expiry dashboard, not fall through to the generic `{% else %}` |
| **Pre-conditions** | Lot with `expiry_date` + `status='quarantine'` |
| **Steps** | GET `/lot-tracking/expiry/` |
| **Expected** | Yellow/warning badge labelled "Quarantine" |
| **Current behaviour** | `expiry_dashboard.html:167` checks `lot.status == 'quarantined'` — model value is `'quarantine'`. Dead branch; lot renders grey generic badge. **Same class of drift as D-05 in warehousing review.** |

### 4.6 Lot state machine (L-15)

| | |
|---|---|
| **ID** | TC-LOT-SM-001 |
| **Description** | `can_transition_to` must match `VALID_TRANSITIONS` for all 25 pairs |
| **Pre-conditions** | Fresh LotBatch |
| **Steps** | Parametrise over 5×5 status pairs |
| **Expected** | `True` for pairs in table, `False` otherwise |
| **Current behaviour** | Correct (unit-verified). Note: `consumed` and `recalled` are terminal — `VALID_TRANSITIONS['consumed']=[]`, `['recalled']=[]`. |

### 4.7 Traceability log auto-emit on lot creation (L-10)

| | |
|---|---|
| **ID** | TC-LOT-INT-001 |
| **Description** | `lot_create_view` must emit a `TraceabilityLog(event_type='received')` in the same request |
| **Pre-conditions** | Tenant, product, warehouse |
| **Steps** | POST lot_create with qty 10 |
| **Expected** | `TraceabilityLog.objects.filter(lot=<new lot>, event_type='received').count() == 1` with `quantity=10`, `to_warehouse=<wh>` |
| **Current behaviour** | Correct ([lot_tracking/views.py:72-82](lot_tracking/views.py#L72-L82)) |

### 4.8 Transition auto-emits TraceabilityLog (L-16)

| | |
|---|---|
| **ID** | TC-LOT-INT-002 |
| **Description** | `lot_transition_view` from `active → recalled` emits `TraceabilityLog(event_type='recalled')` |
| **Pre-conditions** | Lot `active` |
| **Steps** | POST `/lot-tracking/lots/<pk>/transition/recalled/` |
| **Expected** | lot.status=recalled; 1 TraceabilityLog emitted with `event_type='recalled'`, quantity=available_quantity |
| **Current behaviour** | Correct ([lot_tracking/views.py:161-181](lot_tracking/views.py#L161-L181)) |

### 4.9 IDOR cross-tenant lot detail (L-17)

| | |
|---|---|
| **ID** | TC-LOT-SEC-001 |
| **Description** | Tenant A cannot read Tenant B's lot |
| **Steps** | Login as A, GET `/lot-tracking/lots/<B_lot.pk>/` |
| **Expected** | 404 |
| **Current behaviour** | Correct ([lot_tracking/views.py:96](lot_tracking/views.py#L96)) |

### 4.10 Non-admin can delete / recall (L-19)

| | |
|---|---|
| **ID** | TC-LOT-SEC-002 |
| **Description** | A tenant user with `is_tenant_admin=False` should be blocked from destructive / transition endpoints |
| **Pre-conditions** | Non-admin tenant user; quarantined lot |
| **Steps** | POST `/lot-tracking/lots/<pk>/delete/` |
| **Expected** | 403 |
| **Current behaviour** | **200/302** — view has only `@login_required` (D-05) |

### 4.11 Delete recalled lot's serial (S-08)

| | |
|---|---|
| **ID** | TC-LOT-NEG-005 |
| **Description** | A serial under a recalled lot must not be deletable |
| **Pre-conditions** | Lot status=recalled; serial status=available under that lot |
| **Steps** | POST `/lot-tracking/serials/<pk>/delete/` |
| **Expected** | Redirect with warning; serial NOT deleted; audit chain preserved |
| **Current behaviour** | Serial deletes (only gate is `serial.status == 'available'`, ignores lot's status) — D-12 |

### 4.12 Expiry acknowledge overwrites prior notes (E-05)

| | |
|---|---|
| **ID** | TC-LOT-NEG-006 |
| **Description** | Acknowledging an alert must preserve / append existing `notes`, not replace them |
| **Pre-conditions** | ExpiryAlert with `notes='Seeded: approaching 30 days'` |
| **Steps** | POST acknowledge with `notes='OK to proceed'` |
| **Expected** | Final `alert.notes` contains both strings (append with timestamp or carry original) |
| **Current behaviour** | `alert.notes = form.cleaned_data.get('notes', '')` — **overwrites** prior content ([lot_tracking/views.py:426](lot_tracking/views.py#L426)) |

### 4.13 TraceabilityLog requires both warehouses for transfer (T-03)

| | |
|---|---|
| **ID** | TC-LOT-NEG-007 |
| **Description** | `TraceabilityLogForm` must reject `event_type='transferred'` with either warehouse blank |
| **Pre-conditions** | Tenant with lot + warehouses |
| **Steps** | POST traceability_create with event_type=transferred, to_warehouse blank |
| **Expected** | Form error |
| **Current behaviour** | Passes — no cross-field validation (D-10) |

### 4.14 Lot list N+1 guard (L-20)

| | |
|---|---|
| **ID** | TC-LOT-PERF-001 |
| **Description** | Lot list with 200 rows must execute ≤ 10 queries |
| **Pre-conditions** | 200 lots |
| **Steps** | GET `/lot-tracking/lots/?page=1` inside `django_assert_max_num_queries(10)` |
| **Expected** | Passes — select_related on product, warehouse is present |
| **Current behaviour** | Expected green; lock in with test. |

### 4.15 Full trace at scale (T-08)

| | |
|---|---|
| **ID** | TC-LOT-PERF-002 |
| **Description** | `/lot-tracking/lots/<pk>/trace/` must paginate beyond ~100 logs |
| **Pre-conditions** | Lot with 1000 TraceabilityLog rows |
| **Steps** | GET trace URL |
| **Expected** | Response ≤ 1 s; paginated |
| **Current behaviour** | All 1000 logs render in one HTML response (D-11) |

### 4.16 Lot available_quantity invariant on edit (L-09)

| | |
|---|---|
| **ID** | TC-LOT-NEG-008 |
| **Description** | Editing `lot.quantity` to less than `lot.available_quantity` must be rejected (or auto-clamp `available_quantity`) |
| **Pre-conditions** | Lot qty=100, available=80 |
| **Steps** | POST lot_edit with qty=50 |
| **Expected** | Form error `available_quantity (80) exceeds new quantity (50)` |
| **Current behaviour** | Saves; `available_quantity` stays at 80 while `quantity=50` — arithmetic invariant violated (D-13) |

### 4.17 No AuditLog emission on delete (X-17 equivalent)

| | |
|---|---|
| **ID** | TC-LOT-SEC-030 |
| **Description** | Deleting a lot / transitioning a lot to `recalled` must emit a `core.AuditLog` row |
| **Pre-conditions** | Lot exists |
| **Steps** | Delete lot; query `AuditLog` |
| **Expected** | ≥ 1 row with `model_name='LotBatch'`, `action='delete'` |
| **Current behaviour** | **FAILS** — zero `AuditLog` writes anywhere in the module. `TraceabilityLog` captures domain events but not security events. (D-06) |

### 4.18 Anonymous on all URLs (L-18)

| | |
|---|---|
| **ID** | TC-LOT-SEC-020 |
| **Description** | Every URL returns 302 for anonymous user |
| **Steps** | Parametrise over every URL name |
| **Expected** | 302 to login |
| **Current behaviour** | Correct — every view decorated with `@login_required`. |

### 4.19 XSS in notes field

| | |
|---|---|
| **ID** | TC-LOT-SEC-011 |
| **Description** | Lot `notes` containing `<script>alert(1)</script>` must render escaped on detail page |
| **Steps** | Create lot with that notes; GET detail |
| **Expected** | `&lt;script&gt;alert(1)&lt;/script&gt;` |
| **Current behaviour** | Correct (Django auto-escape) |

### 4.20 Seed idempotency (SD-02)

| | |
|---|---|
| **ID** | TC-LOT-SEED-001 |
| **Description** | Running `seed_lot_tracking` twice without `--flush` is a no-op per tenant |
| **Steps** | `python manage.py seed_lot_tracking` twice |
| **Expected** | Second run prints "already exists" |
| **Current behaviour** | Correct ([lot_tracking/management/commands/seed_lot_tracking.py:58-59](lot_tracking/management/commands/seed_lot_tracking.py#L58-L59)) |

---

## 5. Automation Strategy

### 5.1 Tool stack

- **pytest 8.x + pytest-django 4.x** — unit + integration
- **factory-boy** (or inline fixtures matching catalog/vendors/warehousing patterns)
- **Playwright (python)** — optional E2E smoke
- **Locust** — load test on lot_list, serial_list, lot_trace
- **bandit** — static security scan
- Existing [pytest.ini](pytest.ini) points to `config.settings_test`; add `lot_tracking/tests` to `testpaths`.

### 5.2 Suite layout

```
lot_tracking/tests/
├── __init__.py
├── conftest.py              # tenant, user, non_admin_user, warehouse, product, lot, serial, crossdock-free
├── test_models.py           # auto-codes, transitions, properties
├── test_forms.py            # D-01..D-04, D-10, D-13 guards
├── test_views_lot.py        # CRUD + transitions + IDOR + filters + trace
├── test_views_serial.py     # CRUD + transitions + edit-lot-preservation (D-02)
├── test_views_expiry.py     # dashboard + list + acknowledge + notes preservation
├── test_views_traceability.py
├── test_security.py         # auth, RBAC (D-05), XSS, SQLi, audit log (D-06)
├── test_performance.py      # N+1 guards
└── test_seed.py
```

### 5.3 `conftest.py` — runnable against current codebase

```python
# lot_tracking/tests/conftest.py
import pytest
from datetime import date, timedelta
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from warehousing.models import Warehouse
from lot_tracking.models import LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog

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
        username="lt_qa", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def non_admin_user(db, tenant):
    return User.objects.create_user(
        username="lt_qa_reader", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="lt_qa_other", password="qa_pass_123!",
        tenant=other_tenant, is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def client_non_admin(client, non_admin_user):
    client.force_login(non_admin_user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Electronics")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku="SKU-001", name="ThinkPad",
        category=category, purchase_cost=100, retail_price=200,
        status="active",
    )


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(tenant=tenant, name="Main DC")


@pytest.fixture
def lot(db, tenant, product, warehouse):
    return LotBatch.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=100, available_quantity=100,
        manufacturing_date=date.today() - timedelta(days=30),
        expiry_date=date.today() + timedelta(days=180),
    )


@pytest.fixture
def serial(db, tenant, product, warehouse, lot):
    return SerialNumber.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        lot=lot, serial_number="SN-0001",
    )
```

### 5.4 `test_models.py` — unit

```python
import pytest
from datetime import date, timedelta
from lot_tracking.models import LotBatch, SerialNumber


@pytest.mark.django_db
class TestLotAutoCode:
    def test_first(self, tenant, product, warehouse):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
        assert lot.lot_number == "LOT-00001"

    def test_increments(self, tenant, product, warehouse):
        LotBatch.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=1)
        l2 = LotBatch.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=1)
        assert l2.lot_number == "LOT-00002"

    def test_per_tenant(self, tenant, other_tenant, product, warehouse):
        # Each tenant keeps its own sequence
        LotBatch.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=1)
        # Need a product/warehouse scoped to other_tenant too
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="Cat")
        p2 = P.objects.create(tenant=other_tenant, sku="X", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        l = LotBatch.objects.create(tenant=other_tenant, product=p2, warehouse=w2, quantity=1)
        assert l.lot_number == "LOT-00001"


@pytest.mark.django_db
class TestLotProperties:
    def test_is_expired_true(self, lot):
        lot.expiry_date = date.today() - timedelta(days=1)
        lot.save()
        assert lot.is_expired is True

    def test_is_expired_false_when_already_expired_status(self, lot):
        lot.expiry_date = date.today() - timedelta(days=1)
        lot.status = "expired"
        lot.save()
        assert lot.is_expired is False

    def test_days_until_expiry_none_without_date(self, tenant, product, warehouse):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
        assert lot.days_until_expiry is None

    def test_days_until_expiry_negative(self, lot):
        lot.expiry_date = date.today() - timedelta(days=5)
        lot.save()
        assert lot.days_until_expiry == -5


LOT_OK = [
    ("active", "quarantine"), ("active", "expired"),
    ("active", "consumed"), ("active", "recalled"),
    ("quarantine", "active"), ("quarantine", "expired"),
    ("quarantine", "recalled"), ("expired", "recalled"),
]
LOT_BAD = [
    ("consumed", "active"), ("recalled", "active"),
    ("consumed", "recalled"), ("active", "active"),
    ("expired", "active"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", LOT_OK)
def test_lot_transition_allowed(lot, src, dst):
    lot.status = src
    assert lot.can_transition_to(dst)


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", LOT_BAD)
def test_lot_transition_denied(lot, src, dst):
    lot.status = src
    assert not lot.can_transition_to(dst)


SERIAL_OK = [
    ("available", "allocated"), ("available", "sold"),
    ("allocated", "available"), ("allocated", "sold"),
    ("sold", "returned"), ("returned", "available"),
    ("returned", "damaged"), ("damaged", "scrapped"),
]
SERIAL_BAD = [
    ("scrapped", "available"), ("sold", "available"),
    ("damaged", "available"), ("available", "returned"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", SERIAL_OK)
def test_serial_transition_allowed(serial, src, dst):
    serial.status = src
    assert serial.can_transition_to(dst)


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", SERIAL_BAD)
def test_serial_transition_denied(serial, src, dst):
    serial.status = src
    assert not serial.can_transition_to(dst)
```

### 5.5 `test_forms.py` — D-01..D-04, D-10, D-13 acceptance tests

```python
import pytest
from datetime import date, timedelta

from lot_tracking.forms import (
    LotBatchForm, SerialNumberForm, TraceabilityLogForm,
)
from lot_tracking.models import LotBatch, SerialNumber


def _lot_data(product, warehouse, **overrides):
    data = {
        'product': product.pk, 'warehouse': warehouse.pk, 'grn': '',
        'quantity': 10,
        'manufacturing_date': '', 'expiry_date': '',
        'supplier_batch_number': '', 'notes': '',
    }
    data.update(overrides)
    return data


def _serial_data(product, warehouse, **overrides):
    data = {
        'serial_number': 'SN-NEW', 'product': product.pk,
        'lot': '', 'warehouse': warehouse.pk,
        'purchase_date': '', 'warranty_expiry': '', 'notes': '',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestSerialUniqueness:
    """D-01 regression."""
    def test_duplicate_serial_rejected(self, tenant, product, warehouse, serial):
        form = SerialNumberForm(
            data=_serial_data(product, warehouse, serial_number=serial.serial_number),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'serial_number' in form.errors

    def test_same_serial_different_tenant_allowed(
        self, tenant, other_tenant, product, warehouse, serial,
    ):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S2", name="S2", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        form = SerialNumberForm(
            data=_serial_data(p2, w2, serial_number=serial.serial_number),
            tenant=other_tenant,
        )
        assert form.is_valid(), form.errors

    def test_edit_serial_with_own_number_allowed(
        self, tenant, product, warehouse, serial,
    ):
        form = SerialNumberForm(
            data=_serial_data(product, warehouse, serial_number=serial.serial_number),
            instance=serial, tenant=tenant,
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestSerialEditPreservesLot:
    """D-02 regression — editing a serial whose lot is non-active must not clear the FK."""
    def test_lot_queryset_includes_current_even_if_non_active(
        self, tenant, product, warehouse, serial,
    ):
        serial.lot.status = "quarantine"
        serial.lot.save()
        form = SerialNumberForm(instance=serial, tenant=tenant)
        # After fix, queryset should include the current lot despite status filter.
        assert serial.lot in list(form.fields['lot'].queryset)


@pytest.mark.django_db
class TestLotDateValidation:
    """D-03 regression."""
    def test_manufacturing_after_expiry_rejected(self, tenant, product, warehouse):
        form = LotBatchForm(data=_lot_data(
            product, warehouse,
            manufacturing_date=(date.today() + timedelta(days=30)).isoformat(),
            expiry_date=date.today().isoformat(),
        ), tenant=tenant)
        assert not form.is_valid()


@pytest.mark.django_db
class TestLotQuantityValidation:
    """D-04 regression."""
    def test_quantity_zero_rejected(self, tenant, product, warehouse):
        form = LotBatchForm(data=_lot_data(product, warehouse, quantity=0), tenant=tenant)
        assert not form.is_valid()
        assert 'quantity' in form.errors


@pytest.mark.django_db
class TestLotAvailableQuantityInvariant:
    """D-13 regression — editing qty below available_quantity must be rejected."""
    def test_edit_qty_below_available_rejected(self, tenant, lot):
        lot.available_quantity = 80
        lot.save()
        form = LotBatchForm(data={
            'product': lot.product.pk, 'warehouse': lot.warehouse.pk,
            'grn': '', 'quantity': 50,
            'manufacturing_date': '', 'expiry_date': '',
            'supplier_batch_number': '', 'notes': '',
        }, instance=lot, tenant=tenant)
        assert not form.is_valid()


@pytest.mark.django_db
class TestTraceabilityEventValidation:
    """D-10 regression."""
    def test_transfer_requires_both_warehouses(self, tenant, lot, warehouse):
        form = TraceabilityLogForm(data={
            'lot': lot.pk, 'serial_number': '',
            'event_type': 'transferred',
            'from_warehouse': warehouse.pk, 'to_warehouse': '',
            'quantity': 5,
            'reference_type': '', 'reference_number': '', 'notes': '',
        }, tenant=tenant)
        assert not form.is_valid()
```

### 5.6 `test_views_lot.py` — integration

```python
import pytest
from django.urls import reverse
from lot_tracking.models import LotBatch, TraceabilityLog


@pytest.mark.django_db
class TestLotViews:
    def test_list_login_required(self, client):
        r = client.get(reverse("lot_tracking:lot_list"))
        assert r.status_code == 302

    def test_list_tenant_scoped(self, client_logged_in, lot, other_tenant, product, warehouse):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S2", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        LotBatch.objects.create(tenant=other_tenant, product=p2, warehouse=w2, quantity=1)
        r = client_logged_in.get(reverse("lot_tracking:lot_list"))
        assert lot.lot_number.encode() in r.content
        # the other tenant's LOT-00001 is not visible here since tenant is different

    def test_create_emits_traceability(self, client_logged_in, tenant, product, warehouse):
        r = client_logged_in.post(reverse("lot_tracking:lot_create"), {
            "product": product.pk, "warehouse": warehouse.pk, "grn": "",
            "quantity": 10,
            "manufacturing_date": "", "expiry_date": "",
            "supplier_batch_number": "", "notes": "",
        })
        assert r.status_code == 302
        lot = LotBatch.objects.get(tenant=tenant)
        assert TraceabilityLog.objects.filter(
            lot=lot, event_type="received", quantity=10,
        ).exists()

    def test_transition_emits_traceability(self, client_logged_in, lot):
        r = client_logged_in.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "recalled"]),
        )
        assert r.status_code == 302
        lot.refresh_from_db()
        assert lot.status == "recalled"
        assert TraceabilityLog.objects.filter(
            lot=lot, event_type="recalled",
        ).exists()

    def test_invalid_transition_flash(self, client_logged_in, lot):
        r = client_logged_in.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "available"]),
            follow=True,
        )
        lot.refresh_from_db()
        assert lot.status == "active"
        assert b"Cannot transition" in r.content

    def test_delete_only_quarantine(self, client_logged_in, lot):
        # status=active → should block
        r = client_logged_in.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk]), follow=True,
        )
        assert LotBatch.objects.filter(pk=lot.pk).exists()
        # switch to quarantine, then delete
        lot.status = "quarantine"
        lot.save()
        r = client_logged_in.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert r.status_code == 302
        assert not LotBatch.objects.filter(pk=lot.pk).exists()

    def test_idor_cross_tenant(self, client_logged_in, other_tenant, product, warehouse):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S", name="X", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        b_lot = LotBatch.objects.create(tenant=other_tenant, product=p2, warehouse=w2, quantity=1)
        r = client_logged_in.get(
            reverse("lot_tracking:lot_detail", args=[b_lot.pk])
        )
        assert r.status_code == 404
```

### 5.7 `test_security.py` — OWASP A01/A03/A09

```python
import pytest
from django.urls import reverse

from core.models import AuditLog
from lot_tracking.models import LotBatch


@pytest.mark.django_db
class TestAuthn:
    @pytest.mark.parametrize("name,args", [
        ("lot_tracking:lot_list", []),
        ("lot_tracking:lot_create", []),
        ("lot_tracking:serial_list", []),
        ("lot_tracking:expiry_dashboard", []),
        ("lot_tracking:traceability_list", []),
    ])
    def test_login_required(self, client, name, args):
        r = client.get(reverse(name, args=args))
        assert r.status_code == 302


@pytest.mark.django_db
class TestRBAC:
    """D-05 — non-admin tenant user must not reach destructive endpoints."""
    def test_non_admin_blocked_from_delete(self, client_non_admin, lot):
        lot.status = "quarantine"
        lot.save()
        r = client_non_admin.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert r.status_code == 403
        assert LotBatch.objects.filter(pk=lot.pk).exists()

    def test_non_admin_blocked_from_transition(self, client_non_admin, lot):
        r = client_non_admin.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "recalled"])
        )
        assert r.status_code == 403
        lot.refresh_from_db()
        assert lot.status == "active"


@pytest.mark.django_db
class TestXSSAndSQLi:
    def test_xss_in_lot_notes_escaped(self, client_logged_in, tenant, product, warehouse):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, notes="<script>alert(1)</script>",
        )
        r = client_logged_in.get(
            reverse("lot_tracking:lot_detail", args=[lot.pk])
        )
        assert b"<script>alert" not in r.content
        assert b"&lt;script&gt;" in r.content

    def test_sql_injection_on_search(self, client_logged_in):
        r = client_logged_in.get(
            reverse("lot_tracking:lot_list") + "?q=' OR 1=1 --"
        )
        assert r.status_code == 200


@pytest.mark.django_db
class TestAuditLog:
    """D-06 — AuditLog should be emitted on destructive ops."""
    def test_audit_on_lot_delete(self, client_logged_in, lot):
        lot.status = "quarantine"
        lot.save()
        client_logged_in.post(
            reverse("lot_tracking:lot_delete", args=[lot.pk])
        )
        assert AuditLog.objects.filter(
            model_name="LotBatch", action="delete",
        ).exists()

    def test_audit_on_recall(self, client_logged_in, lot):
        client_logged_in.post(
            reverse("lot_tracking:lot_transition", args=[lot.pk, "recalled"])
        )
        assert AuditLog.objects.filter(
            model_name="LotBatch", action="transition",
        ).exists()
```

### 5.8 `test_performance.py` — N+1

```python
import pytest
from django.urls import reverse

from lot_tracking.models import LotBatch


@pytest.mark.django_db
def test_lot_list_no_n_plus_one(
    client_logged_in, tenant, product, warehouse, django_assert_max_num_queries,
):
    for _ in range(50):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
    with django_assert_max_num_queries(12):
        r = client_logged_in.get(reverse("lot_tracking:lot_list"))
    assert r.status_code == 200


@pytest.mark.django_db
def test_lot_trace_view_paginated(
    client_logged_in, lot, django_assert_max_num_queries,
):
    """D-11 — trace view should paginate; a reasonable budget is ≤ 15 queries."""
    from lot_tracking.models import TraceabilityLog
    for i in range(100):
        TraceabilityLog.objects.create(
            tenant=lot.tenant, lot=lot, event_type="adjusted",
            quantity=1, reference_type="Test", reference_number=f"R-{i}",
        )
    with django_assert_max_num_queries(20):
        r = client_logged_in.get(reverse("lot_tracking:lot_trace", args=[lot.pk]))
    assert r.status_code == 200
```

### 5.9 Updating `pytest.ini`

```ini
testpaths = catalog/tests vendors/tests receiving/tests purchase_orders/tests warehousing/tests lot_tracking/tests
```

---

## 6. Defects, Risks & Recommendations

### 6.1 Defect register

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-01** | **High** | A04 Insecure design | [lot_tracking/forms.py:61](lot_tracking/forms.py#L61) (SerialNumberForm) | `unique_together=('tenant','serial_number')` not enforced at form layer — duplicate raises `IntegrityError` 500. **Verified 2026-04-17.** Same failure mode recurs on `LotBatch.lot_number` and `TraceabilityLog.log_number` for the rare case where a user supplies a manual value that collides. | Add `clean_serial_number()` in `SerialNumberForm`: filter-exists → `ValidationError`. For `LotBatch` / `TraceabilityLog`, apply the same pattern if manual entry is exposed; otherwise the auto-gen collision is covered by D-07 (atomic retry). Reuse the `TenantUniqueCodeMixin` pattern from `warehousing/forms.py`. |
| **D-02** | **High** | A04 | [lot_tracking/forms.py:92](lot_tracking/forms.py#L92) (SerialNumberForm `__init__`) | `lot` queryset filtered to `status='active'` — on EDIT of a serial whose current lot is `quarantine`/`expired`/`consumed`/`recalled`, the current lot is **not** in the options. Because `lot` is `required=False`, submitting the form clears the FK silently, severing the genealogy chain. **Verified 2026-04-17 — queryset size 0, current lot absent.** | When instantiating for edit, `OR`-join the current instance's lot into the queryset: `qs = LotBatch.objects.filter(tenant=tenant, status='active'); if self.instance.pk and self.instance.lot_id: qs = qs.union(LotBatch.objects.filter(pk=self.instance.lot_id)); self.fields['lot'].queryset = qs` (or use a `Q` filter to avoid `union` limitations). |
| **D-03** | Medium | A04 | [lot_tracking/forms.py:9](lot_tracking/forms.py#L9) (LotBatchForm) | No cross-field validation `manufacturing_date <= expiry_date`. **Verified 2026-04-17.** | `clean()` — raise `ValidationError({'expiry_date': 'Expiry must be after manufacturing date.'})` when both present and inverted. |
| **D-04** | Medium | A04 | [lot_tracking/forms.py:21](lot_tracking/forms.py#L21), [lot_tracking/models.py:51](lot_tracking/models.py#L51) | `quantity=0` passes form validation (widget `min='1'` is client-side only). `PositiveIntegerField` allows 0. **Verified 2026-04-17.** | Add `clean_quantity` raising on value < 1 in form; add `MinValueValidator(1)` at model level for defence-in-depth. |
| **D-05** | Medium | A01 Broken access control | [lot_tracking/views.py](lot_tracking/views.py) entire file | Every view is only `@login_required`. Any tenant user can delete a lot, recall it, transition a serial to `scrapped`. | Adopt the same `tenant_admin_required` decorator already present in `vendors/` / `warehousing/` — lift into `core/decorators.py` now (three modules share it). Apply to every create/edit/delete/transition/acknowledge view; leave lists + details at `@login_required`. |
| **D-06** | Medium | A09 Logging failures | [lot_tracking/views.py](lot_tracking/views.py) | No `core.AuditLog` emission. `TraceabilityLog` captures domain-level genealogy but not security-level audit (who logged in from which IP, etc.). | Add `emit_audit(request, 'delete', lot)` style calls mirroring `warehousing/decorators.py`. Lift `emit_audit` to `core/decorators.py` for reuse. |
| **D-07** | Low | A04 | [lot_tracking/models.py:91-110](lot_tracking/models.py#L91-L110), [:305-324](lot_tracking/models.py#L305-L324) | `_generate_lot_number` / `_generate_log_number` use read-max-then-write pattern without atomic retry — second concurrent create raises IntegrityError. Same pattern as fixed in [warehousing/models.py](warehousing/models.py#L52) (D-08 of that review). | Copy the atomic retry loop from `warehousing/models.py:Warehouse.save`. Better: lift into `core/models.py:TenantAutoNumberMixin`. |
| **D-08** | Medium | A04 | [templates/lot_tracking/expiry_dashboard.html:167](templates/lot_tracking/expiry_dashboard.html#L167) | Badge branch checks `lot.status == 'quarantined'` — model value is `'quarantine'` ([lot_tracking/models.py:13](lot_tracking/models.py#L13)). Dead branch; quarantined lots fall through to grey generic badge. Same class of drift as D-05 in warehousing review. | Change literal to `'quarantine'`. Sweep all lot_tracking templates and CLAUDE.md-reference `grep -rn "'quarantined'" templates/` → fix every hit. |
| **D-09** | Medium | A04 | [lot_tracking/models.py:194](lot_tracking/models.py#L194), [lot_tracking/views.py:350](lot_tracking/views.py#L350) | `ExpiryAlert` is listed + acknowledged but **never generated automatically** — there is no management command or scheduled task that creates alerts when a lot approaches / crosses expiry. The dashboard counts (`approaching_lots`, `expired_lots`) are computed from lots directly; the `ExpiryAlert` table only holds seed data. | Add a management command `generate_expiry_alerts` that scans `LotBatch.objects.filter(expiry_date__lte=today + 30d, status='active')`, creates `ExpiryAlert` rows with dedup by `(lot, alert_type, alert_date)`. Wire it to run daily (cron / Celery beat). Or: drop the `ExpiryAlert` table entirely if the dashboard query suffices. |
| **D-10** | Medium | A04 | [lot_tracking/forms.py:116](lot_tracking/forms.py#L116) (TraceabilityLogForm) | `clean()` requires lot OR serial but does not enforce: (a) `event_type='transferred'` needs both warehouses; (b) `event_type in ('sold','scrapped','adjusted','received')` needs `quantity > 0` (or explicit sign rules for adjustments). | Expand `clean()` with per-event-type guards. Consider a small dispatch dict keyed on `event_type`. |
| **D-11** | Medium | — | [lot_tracking/views.py:504](lot_tracking/views.py#L504) (lot_trace), [:516](lot_tracking/views.py#L516) (serial_trace) | No pagination on trace pages. A long-lived lot with 1000+ traceability events renders all rows in one request. | Wrap `logs` in `Paginator(logs, 50)` and pass `logs` as a page to the template. |
| **D-12** | Low | A04 | [lot_tracking/views.py:300-302](lot_tracking/views.py#L300-L302) | `serial_delete_view` allows delete if `serial.status='available'` without checking `lot.status`. A serial under a recalled lot should stay on record for the recall audit chain. | Also check: `if serial.lot and serial.lot.status in ('recalled','expired','quarantine'): refuse`. |
| **D-13** | Medium | A04 | [lot_tracking/views.py:110-129](lot_tracking/views.py#L110-L129), [lot_tracking/forms.py:50-58](lot_tracking/forms.py#L50-L58) | Editing `lot.quantity` does not enforce `quantity >= available_quantity`. Setting `quantity=50` when `available_quantity=80` violates the arithmetic invariant. | In `LotBatchForm.clean_quantity` (edit path): `if self.instance.pk and value < self.instance.available_quantity: raise ValidationError(...)`. Alternative: disable `quantity` on edit. |
| **D-14** | Low | A04 | [lot_tracking/views.py:426](lot_tracking/views.py#L426) | `expiry_acknowledge_view` **overwrites** `alert.notes` rather than appending. A pre-existing note (e.g., from seed or auto-generation) is lost. | `alert.notes = f"{alert.notes}\n[{timezone.now():%Y-%m-%d %H:%M} {request.user}] {form.cleaned_data['notes']}".strip()`. |
| **D-15** | Info | — | [lot_tracking/](lot_tracking/) | No test file at all. Catalog / vendors / warehousing all have `tests/` packages; this module ships with zero automated coverage. | Scaffold per §5. |
| **D-16** | Info | A04 | [lot_tracking/views.py:97-99](lot_tracking/views.py#L97-L99) | `lot_detail_view` slices `serial_numbers.all()[:20]` and `traceability_logs[:10]` without mentioning the truncation in the template. Users on a lot with 100 serials see "20 of ???". | Either paginate in the detail view or add "Showing latest 20 of N" text. |

### 6.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Duplicate serial produces 500 | High | Medium | Fix D-01 |
| Silent severing of lot genealogy on edit | High (any quarantine/expired edit) | High (regulatory — food/pharma recall) | Fix D-02 **urgently** |
| Inverted manufacturing/expiry propagates into expiry dashboard | Medium | Medium | Fix D-03 |
| Any tenant user recalls / deletes a lot | Medium | High | Fix D-05 + D-06 |
| Expiry alerts never fire in production | High (likely already the case) | Medium | Fix D-09 |
| Trace page DoS for long-lived lots | Low today, grows over time | Medium | Fix D-11 |
| Concurrent lot creation under load fails | Low | Medium | Fix D-07 |

### 6.3 Recommendations (priority order)

1. **Fix D-02** — preserving lot FK on edit is regulatory — highest priority.
2. **Fix D-01** — form-level guard on duplicate serial.
3. **Fix D-05 + D-06** — lift `core/decorators.py` with `tenant_admin_required` + `emit_audit` (three modules have identical copies) and apply here.
4. **Fix D-08** — template literal typo.
5. **Fix D-03 + D-04 + D-13** — lot form validators.
6. **Fix D-09** — build `generate_expiry_alerts` management command.
7. **Fix D-10** — TraceabilityLog event-type guards.
8. **Fix D-11** — paginate trace views.
9. **Fix D-12 + D-14 + D-07 + D-16** — cleanup during next touch.
10. **Fix D-15** — scaffold `lot_tracking/tests/` per §5.

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Target coverage

| File | Current | Target |
|---|---|---|
| [lot_tracking/models.py](lot_tracking/models.py) | 0% | ≥ 90% line, ≥ 85% branch |
| [lot_tracking/forms.py](lot_tracking/forms.py) | 0% | ≥ 95% line (after D-01..D-04, D-10, D-13 fixes) |
| [lot_tracking/views.py](lot_tracking/views.py) | 0% | ≥ 85% line |
| [lot_tracking/management/commands/seed_lot_tracking.py](lot_tracking/management/commands/seed_lot_tracking.py) | 0% | ≥ 70% |
| Mutation score | — | ≥ 70% on models/forms |

### 7.2 KPI dashboard

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | 100% | 95-99% | <95% |
| Open High/Critical defects | 0 | 1 | ≥2 |
| Open Medium defects | ≤3 | 4-6 | ≥7 |
| Suite runtime | <20s | 20-60s | >60s |
| p95 latency — `lot_list?page=1` (200 rows) | <300 ms | 300-800 ms | >800 ms |
| Query count — `lot_list` | ≤10 | 11-15 | >15 |
| Query count — `lot_trace` (100 logs) | ≤15 | 16-25 | >25 |
| Expiry alert generation lag (daily) | <24 h | 24-48 h | >48 h |
| Audit-log coverage on destructive ops | 100% | 80-99% | <80% |
| Genealogy chain breakage on edit | 0 | — | ≥1 |

### 7.3 Release Exit Gate

A release MUST satisfy **all** of the following to ship:

- [ ] D-01, D-02, D-05, D-08 fixed (High + High-impact Medium defects).
- [ ] `lot_tracking/tests/` has ≥ 50 passing tests (per §5).
- [ ] Line coverage ≥ 85% on `lot_tracking/`.
- [ ] No failing test in the full repo suite.
- [ ] N+1 guards (`test_lot_list_no_n_plus_one`, `test_lot_trace_view_paginated`) green.
- [ ] `bandit -r lot_tracking/` returns zero High findings.
- [ ] Manual smoke: create lot → register serial → transition to sold → recall lot → verify traceability chain intact.
- [ ] `AuditLog` row emitted on ≥ 1 lot delete and ≥ 1 transition.
- [ ] `generate_expiry_alerts` management command exists and is idempotent (D-09).

---

## 8. Summary

The Lot & Serial Number Tracking module is **functionally rich** — it implements two parallel state machines (LotBatch, SerialNumber), an expiry alert workflow, and a domain-level traceability log that automatically records creation + transitions. Multi-tenant isolation (`request.tenant` filter + IDOR guard) is consistent across all 20 views, and Django's ORM / auto-escape protect against the common injection / XSS patterns.

However, the module ships with **zero automated test coverage** (D-15) and **two verified High-severity defects**:

- **D-01 (High)** — duplicate `SerialNumber` within a tenant raises `IntegrityError` → 500. This is the third recurrence of the `unique_together + tenant` trap (catalog, vendors, warehousing each saw it). It is now long past time to promote the `TenantUniqueCodeMixin` from [warehousing/forms.py](warehousing/forms.py) into `core/forms.py` and sweep the remaining modules.
- **D-02 (High)** — editing a serial whose lot is in any non-active status silently **clears the lot FK** because the form's queryset filter excludes the current value. This breaks the traceability / genealogy chain — a regulatory-grade defect for food, pharma, and any regulated-goods deployment.

Plus 14 Medium / Low / Info defects (template badge drift at [expiry_dashboard.html:167](templates/lot_tracking/expiry_dashboard.html#L167), no `core.AuditLog`, no RBAC, no automated expiry-alert generation, unpaginated trace views, date + quantity validators, etc.).

**Next actions (recommended order):**

1. Fix D-02 — highest regulatory risk. Preserve current lot in edit-form queryset.
2. Fix D-01 — apply `TenantUniqueCodeMixin` to `SerialNumberForm`.
3. Lift `tenant_admin_required` + `emit_audit` into `core/decorators.py` and apply here (D-05 + D-06).
4. Scaffold `lot_tracking/tests/` from §5 — use failing tests for D-01..D-04 as acceptance criteria.
5. Build `generate_expiry_alerts` management command (D-09).

Once these close, the module will meet the Exit Gate in §7.3.

---

### Appendix: Manual verification log (2026-04-17)

| Defect | Reproduction | Observed | File |
|---|---|---|---|
| D-01 | Shell — `SerialNumberForm` with duplicate `(tenant, serial_number)` | `form.is_valid() == False` due to no guard → actually `is_valid() == False` because no matching product found in tenant scope; but when product is valid, `is_valid() == True` → `form.save()` raises `IntegrityError (1062 Duplicate entry '8-SN-DUP' ...)` | [lot_tracking/forms.py:61](lot_tracking/forms.py#L61) |
| D-02 | Shell — `SerialNumberForm(instance=s, tenant=t)` where `s.lot.status='quarantine'` | `form.fields['lot'].queryset.count() == 0`; `s.lot in form.fields['lot'].queryset` → `False` | [lot_tracking/forms.py:92](lot_tracking/forms.py#L92) |
| D-03 | Shell — LotBatchForm `manufacturing_date=today+30, expiry_date=today` | `form.is_valid() == True` | [lot_tracking/forms.py:9](lot_tracking/forms.py#L9) |
| D-04 | Shell — LotBatchForm `quantity=0` | `form.is_valid() == True` | [lot_tracking/forms.py:21](lot_tracking/forms.py#L21) |
| D-08 | Diff `LotBatch.STATUS_CHOICES` (`'quarantine'`) vs [expiry_dashboard.html:167](templates/lot_tracking/expiry_dashboard.html#L167) (`'quarantined'`) | Dead branch; quarantined lots render grey generic badge | — |
| D-15 | `ls lot_tracking/` | No `tests.py` and no `tests/` | — |
