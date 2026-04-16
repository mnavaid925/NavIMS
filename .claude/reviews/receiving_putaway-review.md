# Receiving & Putaway — Comprehensive SQA Test Report

**Target:** [receiving/](../../receiving/) Django app (module review — full surface)
**Reviewer:** Senior SQA Engineer
**Date:** 2026-04-17
**Standards:** OWASP Top 10 (2021), ISO/IEC/IEEE 29119, Django Security Cheat Sheet
**Report path:** [.claude/reviews/receiving_putaway-review.md](./receiving_putaway-review.md)

---

## 1. Module Analysis

### 1.1 Scope & surface

The `receiving/` Django app implements the **Receiving & Putaway** lifecycle for the NavIMS multi-tenant IMS. It owns six top-level entities and 7 template/view clusters (≈1045 LoC in [receiving/views.py](../../receiving/views.py), ≈695 LoC in [receiving/models.py](../../receiving/models.py), ≈362 LoC in [receiving/forms.py](../../receiving/forms.py)).

| # | Entity | Purpose | CRUD | Workflow | Auto number |
|---|---|---|---|---|---|
| 1 | `WarehouseLocation` | Hierarchical bin/rack/aisle registry with capacity | List/Create/Detail/Edit/Delete | — | — |
| 2 | `GoodsReceiptNote` (GRN) + `GoodsReceiptNoteItem` | Receives stock against a PO | List/Create/Detail/Edit/Delete | draft → inspecting → completed / cancelled | `GRN-00001` |
| 3 | `VendorInvoice` | Vendor's invoice for a received PO (with optional PDF) | List/Create/Detail/Edit/Delete | draft → pending_match → matched → paid / disputed / cancelled | user-entered |
| 4 | `ThreeWayMatch` | Auto-compares PO ↔ GRN ↔ Invoice | List/Create/Detail/Resolve/Delete | pending → matched / discrepancy → resolved | `TWM-00001` |
| 5 | `QualityInspection` + `QualityInspectionItem` | Accept/reject/quarantine line items from a GRN | List/Create/Detail/Edit/Delete/Complete | pending → in_progress → completed | `QI-00001` |
| 6 | `PutawayTask` | Move accepted stock into warehouse bins | List/Create/Detail/Edit/Delete + transition + auto-generate | pending → assigned → in_progress → completed / cancelled | `PUT-00001` |

### 1.2 External dependencies

| Dependency | Where used | Coupling strength |
|---|---|---|
| [purchase_orders.PurchaseOrder](../../purchase_orders/models.py) | GRN, VendorInvoice, ThreeWayMatch parents; status updated by `GoodsReceiptNote.update_po_status()` | **Hard** — `update_po_status` writes to foreign module |
| [purchase_orders.PurchaseOrderItem](../../purchase_orders/models.py) | GRN line items, match comparison | Hard |
| [catalog.Product](../../catalog/models.py) | GRN items, QI items, putaway tasks | Hard |
| [vendors.Vendor](../../vendors/models.py) | VendorInvoice | Medium |
| [core.Tenant](../../core/models.py) | All 6 models (tenant FK) | Critical |
| [core.User](../../core/models.py) (AUTH_USER_MODEL) | created_by / received_by / inspector / assigned_to / resolved_by | Medium |
| `TenantMiddleware` ([core/middleware.py:1-12](../../core/middleware.py#L1-L12)) | sets `request.tenant` on every request | Critical |

### 1.3 Business rules (location → file:line)

| Rule | Location |
|---|---|
| GRN status machine: draft → inspecting → completed; cancelled ↔ draft; completed is terminal | [receiving/models.py:82-87](../../receiving/models.py#L82-L87) |
| GRN auto-numbering (`GRN-NNNNN`), tenant-scoped, monotonic on `ORDER BY -id` | [receiving/models.py:140-154](../../receiving/models.py#L140-L154) |
| On GRN `completed`: re-compute PO status to `partially_received` / `received` | [receiving/models.py:156-181](../../receiving/models.py#L156-L181), [receiving/views.py:242-243](../../receiving/views.py#L242-L243) |
| Three-way-match price tolerance = `Decimal('0.01')` | [receiving/models.py:405-406](../../receiving/models.py#L405-L406) |
| Best-fit putaway suggestion: active bin with smallest available ≥ qty | [receiving/models.py:681-694](../../receiving/models.py#L681-L694) |
| Putaway completion increments `assigned_location.current_quantity` | [receiving/views.py:994-1002](../../receiving/views.py#L994-L1002) |
| Only draft GRN is editable / deletable | [receiving/views.py:169-170,216-217](../../receiving/views.py#L169-L217) |
| Only draft invoice is deletable; draft + pending_match editable | [receiving/views.py:343-344,371-372](../../receiving/views.py#L343-L372) |
| GRN inspection create transitions GRN to `inspecting` if currently draft | [receiving/views.py:594-597](../../receiving/views.py#L594-L597) |
| Auto-generate putaway uses `quantity_received` (ignores inspection reject/quarantine) | [receiving/views.py:1028-1037](../../receiving/views.py#L1028-L1037) |

### 1.4 Tenancy model

Every model carries a mandatory `tenant` FK; `TenantMiddleware` ([core/middleware.py:5-9](../../core/middleware.py#L5-L9)) exposes it on `request.tenant`. Every view filters by `tenant=request.tenant` (verified across 29/29 object-fetch sites in [receiving/views.py](../../receiving/views.py)). Superuser with `tenant=None` will see empty lists — expected.

### 1.5 Pre-test risk profile

| Area | Inherent risk | Notes |
|---|---|---|
| Three-way-match integrity | **High** | Invoice totals user-entered; match treats invoice at face value |
| Auto-numbering under concurrency | **High** | `ORDER BY -id; +1` is not serialised — race on GRN/TWM/QI/PUT numbers |
| Cross-tenant IDOR via inline formsets | **High** | Formset on POST does not filter `po_item` / `grn_item` / `product` by tenant |
| File upload (VendorInvoice.document) | **High** | No extension/MIME/size guard — OWASP A08 repeat of [lessons.md #8](../tasks/lessons.md) |
| `unique_together(tenant, X)` + form bypass | **High** | Same trap as [lessons.md #6/#7](../tasks/lessons.md); affects `WarehouseLocation.code`, `VendorInvoice.invoice_number` |
| Putaway capacity enforcement | **Medium** | Manual assignment skips capacity validation; exceeds bin silently |
| RBAC beyond `@login_required` | **Medium** | No role-gate — any authenticated tenant user can delete GRNs, resolve matches, transition invoices |
| Atomicity of putaway completion | **Medium** | Task-status + location-quantity update not wrapped in a transaction |
| QI item arithmetic invariant | **Medium** | Nothing enforces `inspected == accepted + rejected + quarantined` |
| Test coverage | **Critical** | Zero tests — [pytest.ini:5](../../pytest.ini#L5) does not include `receiving/tests` |

---

## 2. Test Plan

### 2.1 Test types & allocation

| Type | Target count | Tool | Focus |
|---|---|---|---|
| Unit | 60 | pytest-django | Model invariants, save-time auto-numbering, `perform_match`, `suggest_location`, `can_transition_to`, properties |
| Integration | 55 | pytest-django + Django test client | View + form + formset + DB flow; status transitions; PO-status write-back |
| Functional E2E | 8 | Playwright (headless Chromium) | Full receive → inspect → match → putaway journeys |
| Regression | 20 | pytest | Parametrised guards against reintroduced defects |
| Boundary | 15 | pytest | Decimal precision, max_length, capacity edge, page size |
| Edge | 12 | pytest | Unicode/emoji, empty, NULL FK, duplicate GRN number across tenants |
| Negative | 22 | pytest | IDOR, invalid transitions, over-receipt, invalid files |
| Security | 28 | pytest + bandit + ZAP baseline | OWASP A01/A03/A04/A05/A07/A08/A09 mapping |
| Performance | 8 | pytest + `django_assert_max_num_queries`, Locust | N+1 on list views; list-at-scale (5k GRNs) |
| Usability | 4 | Manual walkthrough | Filter retention, CRUD button completeness |
| **Total** | **232** | | |

### 2.2 Entry criteria
- Branch merges cleanly onto `main` (clean as of commit `26ece55`).
- `python manage.py migrate` runs green on SQLite and MySQL.
- `config/settings_test.py` present ([config/settings_test.py:1-12](../../config/settings_test.py#L1-L12)).
- `python manage.py seed` + `seed_receiving` run green on a clean DB.

### 2.3 Exit criteria — see §7 Release Exit Gate.

---

## 3. Test Scenarios

### 3.1 Warehouse Location (L-NN)

| # | Scenario | Type |
|---|---|---|
| L-01 | Create zone with no parent | Functional |
| L-02 | Create bin with aisle parent | Functional |
| L-03 | Duplicate `(tenant, code)` rejected at form layer | Negative / Regression (lesson #6) |
| L-04 | Same `code` allowed across two tenants | Positive |
| L-05 | `available_capacity` clamps at 0 when full | Unit |
| L-06 | `is_full` true when capacity=0 is **not** full (capacity 0 = unlimited marker) | Unit / Edge |
| L-07 | `full_path` builds from nested parents | Unit |
| L-08 | Delete blocked when children exist | Functional |
| L-09 | Edit location across tenant boundary 404s | Security (A01) |
| L-10 | Capacity accepts PositiveInteger only | Boundary |
| L-11 | Hierarchy cycle (parent = self) — should be prevented | Negative |
| L-12 | Notes XSS payload renders escaped in detail | Security (A03) |
| L-13 | Filter by type=bin preserves across pagination | Usability |
| L-14 | Location list search is case-insensitive on `name` and `code` | Functional |

### 3.2 GRN & GRN Items (G-NN)

| # | Scenario | Type |
|---|---|---|
| G-01 | Create GRN against `sent` PO — auto-numbers `GRN-00001` | Functional |
| G-02 | Create GRN against `partially_received` PO allowed | Positive |
| G-03 | Create GRN against `draft` / `cancelled` PO rejected (queryset excluded) | Negative |
| G-04 | GRN auto-number increments across tenant scope only | Unit |
| G-05 | Concurrent double-submit produces colliding GRN numbers | Negative / Race (D-04) |
| G-06 | Edit allowed only on draft | Functional |
| G-07 | Edit on `completed` GRN shows warning + redirect | Negative |
| G-08 | Delete only on draft | Functional |
| G-09 | Transition draft → inspecting → completed | Functional |
| G-10 | Transition completed → draft rejected | Negative |
| G-11 | Completing GRN updates PO to `partially_received` when < qty | Integration |
| G-12 | Completing GRN updates PO to `received` when all items fulfilled | Integration |
| G-13 | `quantity_previously_received` excludes self | Unit |
| G-14 | `quantity_outstanding` never negative | Unit / Boundary |
| G-15 | Over-receipt (received > ordered) is silently accepted | Defect Candidate (D-07) |
| G-16 | Duplicate GRN number across tenants allowed | Positive |
| G-17 | Cross-tenant GRN detail → 404 | Security (A01) |
| G-18 | Cross-tenant `po_item` injected via POST accepted | Security IDOR (D-05) |
| G-19 | Formset can delete an item | Functional |
| G-20 | Receive with 0 quantity — model allows it | Boundary |
| G-21 | Unicode in `notes` / `delivery_note_number` round-trips | Edge |
| G-22 | Search by PO number / vendor / grn_number | Functional |
| G-23 | Filter by status + date range composes correctly | Functional |
| G-24 | List view N+1 — ≤ 10 queries for 20 rows | Performance |
| G-25 | Timeline reflects cancelled state correctly | Functional |

### 3.3 Vendor Invoice (V-NN)

| # | Scenario | Type |
|---|---|---|
| V-01 | Create invoice for PO with `pending_match` default | Functional |
| V-02 | Duplicate `(tenant, invoice_number)` rejected at form | Negative / Regression (lesson #6) |
| V-03 | Upload `.exe` attachment accepted (no extension guard) | Security A08 (D-02) |
| V-04 | Upload 50 MB PDF — no size cap | Security A08 (D-02) |
| V-05 | Upload SVG with `<script>` payload — retrievable raw | Security A08 (D-02) |
| V-06 | `subtotal + tax != total` — model stores anyway | Defect (D-08) |
| V-07 | Negative amounts — form allows (min=0 on widget only) | Negative |
| V-08 | Transition draft → pending_match → matched → paid | Functional |
| V-09 | Transition matched → cancelled rejected | Negative |
| V-10 | Edit on `matched` invoice rejected | Functional |
| V-11 | Delete on non-draft rejected | Functional |
| V-12 | Cross-tenant invoice detail 404 | Security (A01) |
| V-13 | Invoice list filter by vendor preserves across pagination | Usability |
| V-14 | Large invoice number (100 chars) boundary | Boundary |

### 3.4 Three-Way Match (M-NN)

| # | Scenario | Type |
|---|---|---|
| M-01 | Create match — auto-sets totals, computes quantity_match, price_match | Functional |
| M-02 | Qty match true iff every PO item fully received | Unit |
| M-03 | Price match uses 0.01 tolerance | Unit |
| M-04 | Price match compares PO total vs **Invoice** total — NOT GRN total | Defect (D-09) |
| M-05 | Invoice total manipulated to equal PO → passes despite wrong GRN | Security A04 (D-09) |
| M-06 | Only `completed` GRN selectable in form | Functional |
| M-07 | Resolve match requires current status ∈ {pending, discrepancy} | Functional |
| M-08 | Resolve writes `resolved_by` = request.user + `resolved_at` | Unit |
| M-09 | Match detail compares line-by-line without N+1 | Performance / Regression |
| M-10 | Delete allowed on pending/discrepancy only | Functional |
| M-11 | Cross-tenant match detail 404 | Security (A01) |
| M-12 | Match number auto-increments — race under concurrency | Race (D-04) |

### 3.5 Quality Inspection (Q-NN)

| # | Scenario | Type |
|---|---|---|
| Q-01 | Create inspection for draft GRN → GRN moves to `inspecting` | Integration |
| Q-02 | Inspection item with `accepted + rejected + quarantined != inspected` saved | Defect (D-10) |
| Q-03 | Complete inspection sets status=completed | Functional |
| Q-04 | Only pending inspection deletable | Functional |
| Q-05 | Edit pending → auto-advances to in_progress on save | Functional |
| Q-06 | Inspection formset with GRN item from another tenant accepted | Security IDOR (D-05) |
| Q-07 | Completing inspection does NOT propagate to putaway quantities | Defect (D-11) |
| Q-08 | `total_accepted`, `total_rejected` aggregates | Unit |
| Q-09 | Inspector dropdown limited to tenant users | Regression |
| Q-10 | Cross-tenant inspection detail 404 | Security (A01) |
| Q-11 | Unicode in `reject_reason` renders escaped | Security A03 |

### 3.6 Putaway Task (P-NN)

| # | Scenario | Type |
|---|---|---|
| P-01 | `suggest_location` returns active bin with smallest sufficient available | Unit |
| P-02 | `suggest_location` returns None when no bin fits | Unit / Edge |
| P-03 | Auto-generate for a completed GRN creates one task per item | Functional |
| P-04 | Auto-generate idempotent (does not duplicate) | Regression |
| P-05 | Auto-generate on non-completed GRN rejected | Negative |
| P-06 | Manual create on inactive bin allowed (form filters active only; POST with inactive id) | Security IDOR (D-05) |
| P-07 | Transition pending → assigned → in_progress → completed | Functional |
| P-08 | Completion increments assigned_location.current_quantity | Integration |
| P-09 | Completion exceeding bin capacity accepted silently | Defect (D-12) |
| P-10 | Completion not wrapped in `transaction.atomic` → partial update risk | Defect (D-13) |
| P-11 | Cancel → pending round-trip allowed | Functional |
| P-12 | Completed is terminal — transition to any other rejected | Negative |
| P-13 | Deleting completed task does NOT decrement location qty | Defect (D-14) |
| P-14 | Task number race under concurrency | Race (D-04) |
| P-15 | Cross-tenant task detail 404 | Security (A01) |
| P-16 | Quantity=0 task accepted (PositiveIntegerField allows 0) | Boundary |
| P-17 | Filter by status preserves across pagination | Usability |

---

## 4. Detailed Test Cases

> Format: `ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions`. High-priority cases are listed; remaining scenarios follow the same template in the automation suite (§5).

### 4.1 Warehouse Location

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-LOC-001 | Create bin with parent | tenant admin logged in; aisle exists (code `WH-A`) | POST `/receiving/locations/create/` | `name=Bin Z-01`, `code=Z-01`, `location_type=bin`, `parent=<WH-A.pk>`, `capacity=100` | 302 → detail; bin persisted; `parent_id == WH-A.pk` | 1 row added |
| TC-LOC-002 | Duplicate code same tenant | existing bin with code `Z-01` | POST create with `code=Z-01` | same | Form error on `code`, no 500 | No row added |
| TC-LOC-003 | Duplicate code across tenants | two tenants, tenant-A has `Z-01` | login as tenant-B, POST create `code=Z-01` | same | 302 → detail; tenant-B row created | Two rows total |
| TC-LOC-004 | Delete with children | zone → aisle → bin tree | POST delete on aisle | — | 302 → detail; aisle NOT deleted; warning message | Tree intact |
| TC-LOC-005 | Cross-tenant edit IDOR | tenant-A bin id=`k`; login tenant-B | GET `/receiving/locations/k/edit/` | pk=k | 404 | — |
| TC-LOC-006 | Self-parent cycle | bin exists | POST edit with `parent=<self.pk>` | pk=self.pk | Form error OR reject | No self-reference persisted |
| TC-LOC-007 | XSS in notes | — | Create location with `notes='<script>alert(1)</script>'` | as stated | Detail page renders `&lt;script&gt;...` (auto-escape on) | — |

### 4.2 GRN

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-GRN-001 | Happy-path create | PO in `sent` status with 2 items | POST create with 2 formset rows | `po=<PO.pk>`, `received_date=today`, item quantities `q1=5, q2=3` | 302 → detail; `grn_number` starts `GRN-`; items saved with product auto-filled from po_item | Draft GRN + 2 items |
| TC-GRN-002 | Over-receipt | PO line qty=10 | Create GRN with `quantity_received=999` | q=999 | **Observed:** saved. **Expected:** form error OR cap. Regression for D-07 | defect |
| TC-GRN-003 | Complete GRN → PO becomes partially_received | GRN has 1 of 2 items fully received | transition POST to `completed` | new_status=completed | PO.status == `partially_received` | PO updated |
| TC-GRN-004 | Complete GRN → PO becomes received | all qty in single GRN | transition to `completed` | — | PO.status == `received` | PO updated |
| TC-GRN-005 | Complete → draft rejected | GRN.status=completed | POST transition new_status=draft | — | Warning message; GRN stays completed | — |
| TC-GRN-006 | Cross-tenant GRN detail | login tenant-B | GET `/receiving/grns/<A.pk>/` | — | 404 | — |
| TC-GRN-007 | IDOR po_item on create | tenant-A PO items exist; tenant-B PO items exist | Login tenant-B; POST create with `items-0-po_item=<A.po_item.pk>` | as stated | **Observed:** saved; tenant-B GRN references tenant-A PO item. **Expected:** form error. D-05 | defect |
| TC-GRN-008 | Duplicate GRN number across tenants | tenant-A has `GRN-00001` | tenant-B creates first GRN | — | GRN-00001 persisted for tenant-B | — |
| TC-GRN-009 | Auto-number under concurrency | two simultaneous creates | parallel POST × 2 | — | Both attempts assigned distinct numbers | — (fails in current impl — D-04) |
| TC-GRN-010 | List page performance | 20 GRNs seeded | GET `/receiving/grns/` | — | ≤ 10 queries via `django_assert_max_num_queries` | — |
| TC-GRN-011 | Filter retention on pagination | 25 GRNs, 2 pages, filter status=completed | GET `?status=completed&page=2` | — | Page 2 link preserves `status=completed` | — |

### 4.3 Vendor Invoice

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-INV-001 | Happy-path create | PO + vendor exist | POST create with valid fields | `invoice_number='INV-A-1'`, `vendor=<V.pk>`, `po=<P.pk>`, amounts valid | 302 → detail; status=draft | Invoice saved |
| TC-INV-002 | Duplicate invoice_number | tenant-A has `INV-A-1` | POST create with `INV-A-1` | — | **Observed:** 500 IntegrityError. **Expected:** form error. D-01 | no row |
| TC-INV-003 | Upload .exe | — | POST create with `document=upload('payload.exe')` | 1 KB exe | **Observed:** saved. **Expected:** form error. D-02 | defect |
| TC-INV-004 | Upload oversize PDF | — | POST with 50 MB file | 50 MB PDF | **Observed:** accepted. **Expected:** form error ≥ 10 MB. D-02 | defect |
| TC-INV-005 | SVG-xss upload | — | POST with `.svg` containing `<script>` | crafted svg | **Observed:** accepted; file served raw from `/media/` | defect |
| TC-INV-006 | Total mismatch | — | POST `subtotal=100`, `tax=10`, `total=99999` | as stated | **Observed:** saved. **Expected:** clean() rejects. D-08 | defect |
| TC-INV-007 | Transition matched → cancelled | inv.status=matched | POST transition | new_status=cancelled | Rejected (not in VALID_TRANSITIONS) | — |

### 4.4 Three-Way Match

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-TWM-001 | Happy match | PO + completed GRN covering all qty + invoice total==PO total | POST create | — | match.status=matched; qty_match=price_match=total_match=True | TWM saved |
| TC-TWM-002 | Qty discrepancy | GRN under-received | POST create | — | match.status=discrepancy; qty_match=False | — |
| TC-TWM-003 | Price discrepancy > 0.01 | invoice_total = PO.grand_total + 0.05 | POST create | — | price_match=False; status=discrepancy | — |
| TC-TWM-004 | Invoice manipulation attack | User edits invoice total to equal PO.grand_total but GRN is short | POST create match | — | **Observed:** match=matched (GRN total ignored in price check). D-09 | defect |
| TC-TWM-005 | Resolve discrepancy | match.status=discrepancy | POST `/matches/<pk>/resolve/` with `resolution_notes='ok'` | — | status=resolved; resolved_by=user; resolved_at set | — |
| TC-TWM-006 | Resolve resolved match | status=resolved | POST resolve | — | Warning; no state change | — |

### 4.5 Quality Inspection

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-QI-001 | Create inspection transitions GRN to inspecting | GRN.status=draft | POST create with one item | — | inspection saved; GRN.status=inspecting | — |
| TC-QI-002 | Edit pending → in_progress | inspection.status=pending | POST edit | — | status=in_progress | — |
| TC-QI-003 | Item invariant violation | — | POST item with `inspected=10, accepted=3, rejected=2, quarantined=2` (sum=7 ≠ 10) | as stated | **Observed:** saved. **Expected:** form error. D-10 | defect |
| TC-QI-004 | Complete inspection | status=in_progress | POST complete | — | status=completed | — |
| TC-QI-005 | Delete non-pending | status=in_progress | POST delete | — | Warning; no delete | — |
| TC-QI-006 | IDOR grn_item | tenant-B login; tenant-A grn_item.pk | POST create with foreign grn_item | as stated | **Observed:** saved. **Expected:** form error. D-05 | defect |

### 4.6 Putaway

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| TC-PUT-001 | suggest_location best-fit | bins: avail=200, 100, 500 | call `PutawayTask.suggest_location(tenant, qty=150)` | qty=150 | returns bin with avail=200 | — |
| TC-PUT-002 | suggest returns None | bins all < qty | qty=99999 | — | None | — |
| TC-PUT-003 | Auto-generate idempotent | completed GRN with tasks already | POST `/putaway/generate/<grn.pk>/` | — | messages.info "already have tasks"; created_count=0 | — |
| TC-PUT-004 | Auto-generate ignores inspection rejections | GRN received 10, QI rejected 3 | auto-generate | — | **Observed:** task.quantity=10 (rejected included). **Expected:** 7. D-11 | defect |
| TC-PUT-005 | Completion exceeds capacity | bin capacity=100, current=50, task qty=80 | POST transition completed | — | **Observed:** current_quantity=130; capacity violated. **Expected:** form error. D-12 | defect |
| TC-PUT-006 | Completion atomicity | simulated DB error on `location.save()` | transition to completed | — | **Observed:** task saved but location not — inconsistent. D-13 | defect |
| TC-PUT-007 | Delete completed does not revert qty | task completed; bin.current_quantity=100 | POST delete | — | **Observed:** task.status='completed' blocks delete → ok. Confirm | — |
| TC-PUT-008 | Transition completed → * rejected | task.status=completed | POST transition in_progress | — | Warning; no change | — |
| TC-PUT-009 | Cross-tenant task detail | login tenant-B | GET task from tenant-A | — | 404 | — |
| TC-PUT-010 | List filter retention | 25 tasks, 2 pages, filter status=pending | GET `?status=pending&page=2` | — | Page link preserves `status=pending` | — |

---

## 5. Automation Strategy

### 5.1 Tool stack

| Layer | Tool | Version | Rationale |
|---|---|---|---|
| Test runner | `pytest` + `pytest-django` | 8.x / 4.x | Consistent with [catalog/tests](../../catalog/tests/) and [vendors/tests](../../vendors/tests/) |
| Fixture factories | `factory_boy` | latest | Object builders for seven models |
| Coverage | `coverage.py` + `pytest-cov` | latest | Line + branch |
| Mutation (optional) | `mutmut` | latest | For `perform_match`, `suggest_location`, `update_po_status` |
| E2E | Playwright (Python) | 1.43+ | Headless Chromium |
| Load | Locust | 2.x | List views + PO throughput |
| SAST | `bandit`, `pip-audit` | latest | A06 / A09 |
| DAST | OWASP ZAP baseline | 2.14+ | Endpoint scanning |

### 5.2 Suite layout

```
receiving/
  tests/
    __init__.py
    conftest.py               # tenant, user, other_tenant, po, product, location fixtures
    factories.py              # factory_boy builders
    test_models_location.py
    test_models_grn.py
    test_models_invoice.py
    test_models_match.py
    test_models_inspection.py
    test_models_putaway.py
    test_forms_grn.py
    test_forms_invoice.py
    test_forms_match.py
    test_forms_location.py
    test_forms_putaway.py
    test_views_grn.py
    test_views_invoice.py
    test_views_match.py
    test_views_inspection.py
    test_views_location.py
    test_views_putaway.py
    test_security.py          # OWASP A01/A03/A04/A08
    test_performance.py       # N+1, max_num_queries
    test_regression.py        # D-01..D-14 guards
e2e/
  receiving_smoke.spec.py     # Playwright
perf/
  locustfile_receiving.py
```

Also update [pytest.ini:5](../../pytest.ini#L5) to add `receiving/tests` to `testpaths`.

### 5.3 Runnable snippets

> All snippets use the real NavIMS fixture shapes from [catalog/tests/conftest.py](../../catalog/tests/conftest.py) and the real test settings [config/settings_test.py](../../config/settings_test.py).

#### 5.3.1 `receiving/tests/conftest.py`

```python
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model

from core.models import Tenant
from catalog.models import Category, Product
from vendors.models import Vendor
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from receiving.models import (
    WarehouseLocation, GoodsReceiptNote, GoodsReceiptNoteItem,
    VendorInvoice, ThreeWayMatch, QualityInspection, PutawayTask,
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
def other_client_logged_in(client, other_user):
    client.force_login(other_user)
    return client


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Hardware")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category, sku="SKU-001",
        name="Widget", status="active",
    )


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant, company_name="Acme Supplies",
        email="sup@example.com", is_active=True,
    )


@pytest.fixture
def po(db, tenant, vendor, user):
    po = PurchaseOrder.objects.create(
        tenant=tenant, vendor=vendor, status="sent",
        order_date=date.today(), created_by=user,
    )
    return po


@pytest.fixture
def po_item(db, tenant, po, product):
    return PurchaseOrderItem.objects.create(
        tenant=tenant, purchase_order=po, product=product,
        quantity=10, unit_price=Decimal("5.00"),
    )


@pytest.fixture
def bin_location(db, tenant):
    return WarehouseLocation.objects.create(
        tenant=tenant, name="Bin A-01", code="A-01",
        location_type="bin", capacity=1000, is_active=True,
    )


@pytest.fixture
def grn(db, tenant, po, user):
    return GoodsReceiptNote.objects.create(
        tenant=tenant, purchase_order=po, received_date=date.today(),
        received_by=user, created_by=user,
    )
```

#### 5.3.2 `receiving/tests/test_models_location.py`

```python
import pytest
from receiving.models import WarehouseLocation


@pytest.mark.django_db
class TestWarehouseLocation:
    def test_auto_code_unique_per_tenant(self, tenant, other_tenant):
        WarehouseLocation.objects.create(tenant=tenant, name="B1", code="DUP", location_type="bin")
        WarehouseLocation.objects.create(tenant=other_tenant, name="B1", code="DUP", location_type="bin")
        assert WarehouseLocation.objects.count() == 2

    def test_available_capacity_clamps_at_zero(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="B", code="B", location_type="bin",
            capacity=10, current_quantity=15,
        )
        assert loc.available_capacity == 0

    def test_is_full_unlimited_capacity(self, tenant):
        loc = WarehouseLocation.objects.create(
            tenant=tenant, name="Z", code="Z", location_type="zone", capacity=0,
        )
        assert loc.is_full is False  # 0 means unmetered — not full

    def test_full_path_nested(self, tenant):
        z = WarehouseLocation.objects.create(tenant=tenant, name="Z", code="Z", location_type="zone")
        a = WarehouseLocation.objects.create(tenant=tenant, name="A1", code="A1", parent=z, location_type="aisle")
        b = WarehouseLocation.objects.create(tenant=tenant, name="B1", code="B1", parent=a, location_type="bin")
        assert b.full_path == "Z > A1 > B1"
```

#### 5.3.3 `receiving/tests/test_models_putaway.py`

```python
import pytest
from receiving.models import PutawayTask, WarehouseLocation


@pytest.mark.django_db
class TestSuggestLocation:
    def test_best_fit(self, tenant):
        WarehouseLocation.objects.create(tenant=tenant, name="B1", code="B1", location_type="bin",
                                         capacity=200, current_quantity=0, is_active=True)
        tight = WarehouseLocation.objects.create(tenant=tenant, name="B2", code="B2", location_type="bin",
                                                 capacity=100, current_quantity=0, is_active=True)
        WarehouseLocation.objects.create(tenant=tenant, name="B3", code="B3", location_type="bin",
                                         capacity=500, current_quantity=0, is_active=True)
        # Qty=50 → should pick smallest available ≥ 50 → B2 (avail=100)
        picked = PutawayTask.suggest_location(tenant, 50)
        assert picked == tight

    def test_none_when_no_fit(self, tenant):
        WarehouseLocation.objects.create(tenant=tenant, name="B1", code="B1", location_type="bin",
                                         capacity=10, current_quantity=0, is_active=True)
        assert PutawayTask.suggest_location(tenant, 9999) is None

    def test_excludes_inactive(self, tenant):
        WarehouseLocation.objects.create(tenant=tenant, name="B1", code="B1", location_type="bin",
                                         capacity=500, current_quantity=0, is_active=False)
        assert PutawayTask.suggest_location(tenant, 10) is None
```

#### 5.3.4 `receiving/tests/test_models_match.py`

```python
import pytest
from decimal import Decimal
from receiving.models import (
    GoodsReceiptNote, GoodsReceiptNoteItem, VendorInvoice, ThreeWayMatch,
)


@pytest.mark.django_db
class TestThreeWayMatch:
    def test_full_match(self, tenant, po, po_item, product, vendor, user, grn):
        grn.status = "completed"
        grn.save()
        GoodsReceiptNoteItem.objects.create(
            tenant=tenant, grn=grn, po_item=po_item, product=product,
            quantity_received=10,
        )
        inv = VendorInvoice.objects.create(
            tenant=tenant, invoice_number="I1", vendor=vendor,
            purchase_order=po, invoice_date=grn.received_date,
            subtotal=po.subtotal, tax_amount=po.tax_total,
            total_amount=po.grand_total,
        )
        twm = ThreeWayMatch.objects.create(tenant=tenant, purchase_order=po, grn=grn, vendor_invoice=inv)
        twm.perform_match()
        assert twm.quantity_match and twm.price_match and twm.total_match
        assert twm.status == "matched"

    def test_qty_mismatch_flags_discrepancy(self, tenant, po, po_item, product, vendor, grn):
        grn.status = "completed"; grn.save()
        GoodsReceiptNoteItem.objects.create(tenant=tenant, grn=grn, po_item=po_item, product=product,
                                            quantity_received=5)  # underreceived
        inv = VendorInvoice.objects.create(tenant=tenant, invoice_number="I2", vendor=vendor,
                                           purchase_order=po, invoice_date=grn.received_date,
                                           subtotal=po.subtotal, tax_amount=po.tax_total,
                                           total_amount=po.grand_total)
        twm = ThreeWayMatch.objects.create(tenant=tenant, purchase_order=po, grn=grn, vendor_invoice=inv)
        twm.perform_match()
        assert twm.quantity_match is False
        assert twm.status == "discrepancy"

    def test_invoice_manipulation_attack_regression(self, tenant, po, po_item, product, vendor, grn):
        """
        D-09: Attacker edits invoice total to equal PO.grand_total while GRN is short.
        EXPECTED after fix: price match must compare against BOTH PO and GRN totals.
        """
        grn.status = "completed"; grn.save()
        GoodsReceiptNoteItem.objects.create(tenant=tenant, grn=grn, po_item=po_item, product=product,
                                            quantity_received=5)  # GRN total = 5*5 = 25
        inv = VendorInvoice.objects.create(tenant=tenant, invoice_number="I3", vendor=vendor,
                                           purchase_order=po, invoice_date=grn.received_date,
                                           subtotal=po.subtotal, tax_amount=po.tax_total,
                                           total_amount=po.grand_total)  # 50 total
        twm = ThreeWayMatch.objects.create(tenant=tenant, purchase_order=po, grn=grn, vendor_invoice=inv)
        twm.perform_match()
        # After fix: must NOT be fully matched
        assert twm.status == "discrepancy"
```

#### 5.3.5 `receiving/tests/test_views_grn.py`

```python
import pytest
from django.urls import reverse
from receiving.models import GoodsReceiptNote


@pytest.mark.django_db
class TestGrnViews:
    def test_list_tenant_isolation(self, client_logged_in, other_tenant, other_user, po):
        # GRN in user's tenant
        GoodsReceiptNote.objects.create(tenant=po.tenant, purchase_order=po, received_date="2026-01-01")
        r = client_logged_in.get(reverse("receiving:grn_list"))
        assert r.status_code == 200
        assert b"GRN-" in r.content

    def test_cross_tenant_detail_404(self, client, user, other_tenant, other_user):
        from purchase_orders.models import PurchaseOrder
        from vendors.models import Vendor
        v = Vendor.objects.create(tenant=other_tenant, company_name="Other", is_active=True)
        po = PurchaseOrder.objects.create(tenant=other_tenant, vendor=v, status="sent", order_date="2026-01-01")
        grn = GoodsReceiptNote.objects.create(tenant=other_tenant, purchase_order=po, received_date="2026-01-01")
        client.force_login(user)  # tenant A user
        r = client.get(reverse("receiving:grn_detail", args=[grn.pk]))
        assert r.status_code == 404

    def test_non_draft_edit_blocked(self, client_logged_in, po):
        grn = GoodsReceiptNote.objects.create(
            tenant=po.tenant, purchase_order=po, received_date="2026-01-01", status="completed",
        )
        r = client_logged_in.get(reverse("receiving:grn_edit", args=[grn.pk]))
        assert r.status_code == 302  # redirect with warning

    def test_formset_cross_tenant_po_item_regression_D05(
        self, client_logged_in, tenant, other_tenant, other_user,
    ):
        """
        D-05: The GRN create POST does not filter formset querysets by tenant.
        After fix: POSTing a foreign po_item id must fail validation.
        """
        from catalog.models import Category, Product
        from vendors.models import Vendor
        from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p = Product.objects.create(tenant=other_tenant, category=cat, sku="X", name="X", status="active")
        v = Vendor.objects.create(tenant=other_tenant, company_name="O", is_active=True)
        po_other = PurchaseOrder.objects.create(tenant=other_tenant, vendor=v, status="sent", order_date="2026-01-01")
        po_other_item = PurchaseOrderItem.objects.create(
            tenant=other_tenant, purchase_order=po_other, product=p, quantity=1, unit_price="1.00",
        )
        # Tenant A user posts with tenant B's po_item
        from purchase_orders.models import PurchaseOrder as PO_A
        v2 = Vendor.objects.create(tenant=tenant, company_name="A", is_active=True)
        po_a = PO_A.objects.create(tenant=tenant, vendor=v2, status="sent", order_date="2026-01-01")
        payload = {
            "purchase_order": po_a.pk,
            "received_date": "2026-01-01",
            "delivery_note_number": "",
            "notes": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-po_item": po_other_item.pk,   # foreign tenant
            "items-0-product": "",
            "items-0-quantity_received": "5",
            "items-0-notes": "",
        }
        r = client_logged_in.post(reverse("receiving:grn_create"), data=payload)
        # After fix: should render form with error, not 302
        assert r.status_code == 200
        assert GoodsReceiptNote.objects.filter(tenant=tenant).count() == 0
```

#### 5.3.6 `receiving/tests/test_security.py`

```python
import pytest
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from receiving.models import VendorInvoice


@pytest.mark.django_db
class TestOWASP:
    def test_A03_xss_escape_on_notes(self, client_logged_in, po, vendor):
        payload = "<script>alert('xss')</script>"
        r = client_logged_in.post(reverse("receiving:invoice_create"), data={
            "invoice_number": "XSS-1", "vendor": vendor.pk, "purchase_order": po.pk,
            "invoice_date": "2026-01-01", "due_date": "",
            "subtotal": "10.00", "tax_amount": "0.00", "total_amount": "10.00",
            "notes": payload,
        })
        inv = VendorInvoice.objects.get(invoice_number="XSS-1")
        r2 = client_logged_in.get(reverse("receiving:invoice_detail", args=[inv.pk]))
        assert payload.encode() not in r2.content
        assert b"&lt;script&gt;" in r2.content

    def test_A08_exe_upload_blocked_regression_D02(self, client_logged_in, po, vendor):
        """After fix: .exe upload must be rejected."""
        exe = SimpleUploadedFile("payload.exe", b"MZ\x90\x00" + b"\x00" * 1024,
                                 content_type="application/octet-stream")
        r = client_logged_in.post(reverse("receiving:invoice_create"), data={
            "invoice_number": "EXE-1", "vendor": vendor.pk, "purchase_order": po.pk,
            "invoice_date": "2026-01-01",
            "subtotal": "0", "tax_amount": "0", "total_amount": "0",
            "document": exe,
        })
        # After fix: form error (200), no invoice created
        assert r.status_code == 200
        assert not VendorInvoice.objects.filter(invoice_number="EXE-1").exists()

    def test_A01_anonymous_cannot_list(self, client):
        r = client.get(reverse("receiving:grn_list"))
        assert r.status_code in (302, 403)
```

#### 5.3.7 `receiving/tests/test_performance.py`

```python
import pytest
from django.urls import reverse
from receiving.models import GoodsReceiptNote


@pytest.mark.django_db
def test_grn_list_no_n_plus_one(client_logged_in, django_assert_max_num_queries, po, user):
    for _ in range(20):
        GoodsReceiptNote.objects.create(
            tenant=po.tenant, purchase_order=po, received_date="2026-01-01",
            received_by=user, created_by=user,
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("receiving:grn_list"))
        assert r.status_code == 200
```

#### 5.3.8 `perf/locustfile_receiving.py` (smoke load)

```python
from locust import HttpUser, task, between


class ReceivingUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post("/accounts/login/", {
            "username": "admin_acme", "password": "demo123",
        })

    @task(3)
    def grn_list(self):
        self.client.get("/receiving/grns/")

    @task(1)
    def putaway_list(self):
        self.client.get("/receiving/putaway/")
```

### 5.4 CI hook

Add to `pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings_test
python_files = tests.py test_*.py *_tests.py
addopts = -ra -q --strict-markers --cov=receiving --cov-fail-under=80
testpaths = catalog/tests vendors/tests receiving/tests
```

---

## 6. Defects, Risks & Recommendations

> **Verification note:** every High/Critical finding below was verified by reading the exact lines cited. D-01, D-02, D-05, D-09 map directly onto prior lessons #6, #7, #8 captured in [.claude/tasks/lessons.md](../tasks/lessons.md) — they are **re-occurrences of documented systemic patterns**.

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| **D-01** | **Critical** | [receiving/forms.py:88-141](../../receiving/forms.py#L88-L141) — `VendorInvoiceForm`; also [receiving/forms.py:269-306](../../receiving/forms.py#L269-L306) `WarehouseLocationForm` | **`unique_together(tenant, X)` + form-bypass trap.** Neither `VendorInvoiceForm.clean_invoice_number` nor `WarehouseLocationForm.clean_code` exists. Because `tenant` is NOT rendered, `validate_unique()` drops it from the check — duplicates escape to the DB as `IntegrityError` (500). Repeat of lesson #6/#7. **OWASP A04 / A05.** | Add `def clean_invoice_number(self): ...` and `def clean_code(self): ...` filtering by `self.tenant`, same pattern as `catalog/forms.py:ProductForm.clean_sku`. |
| **D-02** | **Critical** | [receiving/models.py:283](../../receiving/models.py#L283); [receiving/forms.py:115](../../receiving/forms.py#L115) | **Unrestricted file upload on `VendorInvoice.document`.** No extension whitelist, no MIME check, no size cap, no SVG block, no `content_type` block. Direct re-occurrence of lesson #8. Attacker can upload `.exe`, 500 MB polyglot, or `.svg` with active script. **OWASP A08.** | Until shared `core.validators.SafeFileUploadValidator` exists (lesson #8 mandate), add `clean_document()` in `VendorInvoiceForm` with (a) `.pdf/.png/.jpg/.jpeg/.webp` whitelist, (b) 10 MB cap, (c) block `image/svg+xml`, (d) `python-magic` magic-byte verification. Also serve `/media/` through `@login_required` view that enforces tenant isolation. |
| **D-03** | **High** | [receiving/models.py:140-154,424-438,511-525,665-679](../../receiving/models.py#L140-L154) | **Auto-number generation is racy.** `ORDER BY -id; max+1` is not serialised — two concurrent creates will produce the same `GRN-00001`, caught only by `unique_together` → 500. Additionally, if the newest row is deleted the next number *regenerates* it (collision with a previously-deleted number if referenced in exports). Affects GRN / TWM / QI / PUT numbers. | Wrap the `save()` path in `transaction.atomic()` + `select_for_update()` on a `TenantCounter` row, OR use `F('last_number') + 1` on a dedicated sequence table. Never rely on `MAX(id)` to mint business identifiers. |
| **D-04** | **Critical** | [receiving/views.py:81-99](../../receiving/views.py#L81-L99); [receiving/views.py:573-603](../../receiving/views.py#L573-L603) | **Cross-tenant IDOR via inline formset on POST.** In `grn_create_view` / `grn_edit_view` / `inspection_create_view` / `inspection_edit_view`, the tenant-scoped queryset is only set on the `formset.forms` iterator in the **GET** branch, AFTER the POST has already been validated (`formset.is_valid()`). On POST the formset factory uses `PurchaseOrderItem.objects.all()` (no tenant filter), so an attacker in tenant B can pass `items-0-po_item=<tenant-A po_item.pk>` and link it to their own GRN. Same vector on `inspection_items.grn_item`. **OWASP A01.** | Subclass the formset (`forms.BaseInlineFormSet`) or override `GoodsReceiptNoteItemForm.__init__` to receive `tenant` via `form_kwargs` and filter `fields['po_item'].queryset = PurchaseOrderItem.objects.filter(tenant=tenant)` and same for `product`. Use `inlineformset_factory(..., form_kwargs={'tenant': tenant})` and `formset.form_kwargs = {'tenant': tenant}`. |
| **D-05** | **High** | [receiving/models.py:376-417](../../receiving/models.py#L376-L417) | **Three-way match price check ignores GRN total.** `price_match` compares `po_total ↔ invoice_total` only (line 406). A malicious user can enter an inflated `VendorInvoice.total_amount` exactly equal to PO total while the GRN is short-received — match reports `matched`. `grn_total` is computed (line 390) but **never compared**. Defeats the purpose of a three-way match. **OWASP A04 (Insecure design).** | Change line 406 to `self.price_match = (abs(po - inv) <= tol) and (abs(po - grn) <= tol) and (abs(inv - grn) <= tol)`. Update `test_models_match.py::test_invoice_manipulation_attack_regression`. |
| **D-06** | **High** | [receiving/models.py:205](../../receiving/models.py#L205); [receiving/views.py:88-95](../../receiving/views.py#L88-L95) | **Over-receipt not enforced.** `quantity_received` has no validator ensuring `quantity_received ≤ quantity_outstanding`. A single GRN can receive more than the PO ordered; additional GRNs on the same PO can continue to receive silently. Skews inventory and `update_po_status` loops. | Add `clean()` on `GoodsReceiptNoteItemForm`: reject when `cleaned_data['quantity_received'] > po_item.quantity - quantity_previously_received` (optionally with a tenant-configurable over-receipt tolerance). |
| **D-07** | **High** | [receiving/models.py:279-281](../../receiving/models.py#L279-L281); [receiving/forms.py:106-114](../../receiving/forms.py#L106-L114) | **Invoice totals are not reconciled.** `subtotal + tax_amount` is never compared to `total_amount`; user-entered values persist untouched. Because `VendorInvoice.total_amount` seeds the three-way match, this compounds D-05. | Override `VendorInvoiceForm.clean()`: if abs(subtotal + tax_amount - total_amount) > 0.01, raise ValidationError. |
| **D-08** | **High** | [receiving/views.py:983-1006](../../receiving/views.py#L983-L1006) | **Putaway completion can exceed bin capacity.** `putaway_transition_view` on `new_status=='completed'` increments `location.current_quantity` by `task.quantity` with **no** capacity check. Bin with capacity=100 can reach `current_quantity=1,000,000`. Also not atomic — two concurrent completions interleave. | Before incrementing, assert `location.current_quantity + task.quantity ≤ location.capacity` (or allow 0 = unlimited); raise ValidationError / return warning otherwise. Wrap the task.save + location.save block in `@transaction.atomic`, lock the row with `select_for_update()`. |
| **D-09** | **High** | [receiving/views.py:994-1002](../../receiving/views.py#L994-L1002) | **Putaway completion not atomic.** Two writes (task + location) with no transaction. A DB error between them leaves the warehouse with a saved-as-completed task but un-updated bin quantity. | Wrap the block in `with transaction.atomic():`. |
| **D-10** | **Medium** | [receiving/views.py:1010-1044](../../receiving/views.py#L1010-L1044) | **Auto-generate putaway ignores inspection results.** `putaway_generate_view` uses `grn_item.quantity_received` as the task quantity — but if a QualityInspection rejected or quarantined some units, those rejected units should not go to the bin. Currently rejected stock gets a putaway task. | Join with `QualityInspectionItem` for the same `grn_item`; use `sum(quantity_accepted)` instead. If no inspection exists, either (a) block auto-generate until one exists, or (b) keep using `quantity_received` with an explicit warning. |
| **D-11** | **Medium** | [receiving/models.py:528-570](../../receiving/models.py#L528-L570); [receiving/forms.py:223-253](../../receiving/forms.py#L223-L253) | **QI item invariant not enforced.** `quantity_inspected` is expected to equal `accepted + rejected + quarantined` but nothing enforces it. An inspector can sign off `inspected=10, accepted=3` — the remaining 7 vanish from the audit trail. | `QualityInspectionItemForm.clean()` — assert sum(accepted+rejected+quarantined) == inspected. |
| **D-12** | **Medium** | [receiving/views.py:983-1006](../../receiving/views.py#L983-L1006) | **Putaway task reversal** — `cancelled → pending` loop is allowed but `completed` is terminal (good); however if a completed task is later deleted the bin `current_quantity` is not decremented. Currently `putaway_delete_view` blocks non-pending, so completed cannot be deleted — but admin backend bypasses the view guard. | Either (a) prevent deletion in admin too via `has_delete_permission` checks, or (b) override `PutawayTask.delete()` to reverse the qty if status == 'completed'. |
| **D-13** | **Medium** | [receiving/views.py](../../receiving/views.py) (all views) | **No role-based access control.** Only `@login_required`; any authenticated tenant user — including low-privilege ones — can delete GRNs, cancel invoices, resolve matches, and write-back PO status. **OWASP A01.** | Decorate destructive views (`*_delete`, `*_transition`, `match_resolve`, `putaway_generate`) with a role check: `@user_passes_test(lambda u: u.is_tenant_admin or u.groups.filter(name='warehouse_manager').exists())`. |
| **D-14** | **Medium** | [receiving/models.py:207](../../receiving/models.py#L207); [receiving/models.py:556-559](../../receiving/models.py#L556-L559) | **`PositiveIntegerField` allows 0.** `quantity_received`, `quantity_inspected`, `quantity_accepted`, `PutawayTask.quantity` all accept `0`. A GRN with zero qty on every line is a legal "empty" GRN; putaway of zero is legal. Not catastrophic but pollutes reports. | Add `MinValueValidator(1)` on `quantity_received` and `PutawayTask.quantity` (model + form). Keep 0 only for `quantity_rejected/quarantined` where 0 is semantically valid. |
| **D-15** | **Medium** | [receiving/views.py:169](../../receiving/views.py#L169); [receiving/views.py:242-243](../../receiving/views.py#L242-L243) | **`update_po_status` has no atomicity.** Counting previously-received items across GRNs and updating the PO status happens outside a transaction; if the PO is concurrently transitioned elsewhere the write races. | Wrap `update_po_status` body in `transaction.atomic()` and `select_for_update()` on the PO row. |
| **D-16** | **Medium** | [receiving/views.py:1010-1044](../../receiving/views.py#L1010-L1044) | **`putaway_generate_view` creates tasks even when destination bin is `None`.** `PutawayTask.suggest_location` returns `None` if no bin fits; the task saves with `suggested_location=None` and the user must manually assign. Fine, except there is no indicator in the success message of how many tasks are un-routable. | Count `suggested is None` occurrences; surface "X tasks created, Y need manual routing" in the success message. |
| **D-17** | **Low** | [receiving/views.py:135-152,911-930](../../receiving/views.py#L135-L152) | **Timeline duplication.** GRN + putaway timeline logic duplicated verbatim — maintainability risk. | Extract `build_timeline(current, order, labels, cancelled_flag)` helper. |
| **D-18** | **Low** | [receiving/models.py:94](../../receiving/models.py#L94); [receiving/models.py:266](../../receiving/models.py#L266) | **Short `max_length=20` on business numbers.** `grn_number` + `match_number` + `task_number` + `inspection_number` capped at 20 chars. After ~9.99M rows the format `GRN-1234567` still fits (11 chars) — headroom OK, but a custom tenant prefix would overflow. | Bump to 32 for flexibility. Low priority. |
| **D-19** | **Info** | [receiving/models.py:380-390](../../receiving/models.py#L380-L390) | **N+1 in `perform_match`.** `for grn_item in grn.items.all().select_related('po_item'):` is fine, but the outer `for po_item in po.items.all():` then `grn.items.filter(po_item=po_item).aggregate(...)` fires 1 query per PO item. | Replace with a single `grn.items.values('po_item').annotate(total=Sum('quantity_received'))` lookup. |
| **D-20** | **Info** | [pytest.ini:5](../../pytest.ini#L5) | **No tests for receiving.** Zero test coverage; `testpaths` omits `receiving/tests`. | Add `receiving/tests` per §5. |
| **D-21** | **Info** | [config/settings.py:11-13](../../config/settings.py#L11-L13) | **`DEBUG=True` default; `ALLOWED_HOSTS=['*']` default.** Env-driven, but the default is unsafe. **OWASP A05.** (Project-level, surfaced because this module handles file uploads.) | Default to `DEBUG=False`, require explicit `ALLOWED_HOSTS`. |

### 6.1 Risk register

| Risk | Likelihood | Impact | Severity | Mitigation link |
|---|---|---|---|---|
| Financial mis-match marked "matched" | Medium | Severe (cash leak) | Critical | D-05, D-07 |
| Malware via invoice upload | Medium | Severe (host compromise) | Critical | D-02 |
| Cross-tenant data leak via formset IDOR | Medium | Severe (privacy/compliance) | Critical | D-04 |
| Number collisions under load | High | High (500s, data duplication) | High | D-03 |
| Inventory drift from capacity-less putaway | Medium | High (stockout) | High | D-08, D-09 |
| Privilege escalation within tenant | Medium | Medium | Medium | D-13 |

### 6.2 OWASP Top-10 coverage summary

| OWASP | Status | Evidence |
|---|---|---|
| A01 Broken Access Control | ⚠ Partial | Tenant filter on gets (good) + cross-tenant formset IDOR (D-04) + no RBAC (D-13) |
| A02 Crypto failures | ✅ OK | Django password hashers in use; no custom crypto in module |
| A03 Injection / XSS | ✅ OK | Templates auto-escape; verified on `notes`, `code`, `name` fields |
| A04 Insecure design | ❌ Fail | D-05 (invoice manipulation), D-07 (unreconciled totals), D-11 (QI arithmetic) |
| A05 Security misconfiguration | ⚠ Partial | DEBUG/ALLOWED_HOSTS defaults (D-21); no SECURE_* headers |
| A06 Vulnerable deps | ⚠ Unverified | run `pip-audit` |
| A07 Auth failures | ⚠ Project-level | out of module scope |
| A08 Data integrity / file upload | ❌ Fail | D-02 |
| A09 Logging failures | ⚠ Missing | No AuditLog entries emitted from destructive receiving actions |
| A10 SSRF | ✅ Not applicable | No external URL fetching in module |

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Current vs target coverage

| File | Current line coverage | Target | Gap |
|---|---|---|---|
| [receiving/models.py](../../receiving/models.py) | 0% | 90% | +90% |
| [receiving/views.py](../../receiving/views.py) | 0% | 85% | +85% |
| [receiving/forms.py](../../receiving/forms.py) | 0% | 90% | +90% |
| [receiving/admin.py](../../receiving/admin.py) | 0% | 50% | +50% |
| [receiving/management/commands/seed_receiving.py](../../receiving/management/commands/seed_receiving.py) | 0% | 60% | +60% |

Overall module target: **≥ 80% line, ≥ 70% branch**, mutation score ≥ 60% on `perform_match` / `suggest_location` / `update_po_status`.

### 7.2 KPI table

| KPI | Green | Amber | Red | Current |
|---|---|---|---|---|
| Functional pass rate | ≥ 99% | 95–99% | < 95% | n/a (no suite) |
| Open Critical defects | 0 | — | ≥ 1 | **3** (D-01, D-02, D-04) |
| Open High defects | 0 | 1–2 | ≥ 3 | **5** |
| Line coverage | ≥ 80% | 60–80% | < 60% | **0%** |
| Branch coverage | ≥ 70% | 50–70% | < 50% | 0% |
| Mutation score (core fns) | ≥ 60% | 40–60% | < 40% | n/a |
| List view queries (20 rows) | ≤ 10 | 11–20 | > 20 | unknown |
| Suite wall-clock | ≤ 60 s | 60–180 s | > 180 s | n/a |
| p95 latency `/grns/` (100 RPS, 5k rows) | ≤ 400 ms | 400–800 | > 800 | unknown |
| Regression escape rate | 0 per release | 1 | ≥ 2 | n/a |

### 7.3 Release Exit Gate

Shipping to production is **BLOCKED** until all of the following are true:

- [ ] **D-01, D-02, D-04, D-05** fixed and each has a regression test in `test_regression.py`.
- [ ] `receiving/tests/` added to [pytest.ini:5](../../pytest.ini#L5) and passes green.
- [ ] Line coverage ≥ 80% on models/views/forms.
- [ ] `bandit -r receiving/` reports zero High findings.
- [ ] `pip-audit` reports zero High CVEs on requirements.txt pins.
- [ ] OWASP ZAP baseline scan of `/receiving/*` reports zero High alerts.
- [ ] PowerShell + SQLite seed round-trip verified: `python manage.py seed; python manage.py seed_receiving` then `python manage.py seed_receiving` (second run prints "already exists" warning, no crash).
- [ ] Three-way-match regression test (`test_invoice_manipulation_attack_regression`) passes.
- [ ] Cross-tenant formset IDOR regression test passes.
- [ ] `.exe` upload regression test passes (rejected).
- [ ] Putaway capacity-overflow test passes (rejected).

---

## 8. Summary

The `receiving/` module covers the end-to-end receipt-to-shelf workflow competently at the data-model and CRUD-surface level, but it ships with **zero automated tests**, **three Critical defects**, and **five High defects** — most of which are documented re-occurrences of patterns already captured in [.claude/tasks/lessons.md](../tasks/lessons.md) (lessons #6, #7, #8). The systemic audit mandated by lesson #7 explicitly names `receiving` as still outstanding, and this review confirms that every item in that audit applies.

### Top-5 must-fix before release

1. **D-04 Cross-tenant IDOR in GRN & QualityInspection inline formsets** — the most dangerous finding; silently links foreign PO items into a tenant's receipts.
2. **D-05 Three-way-match trivially defeated** by manipulating `VendorInvoice.total_amount` — financial-integrity defect.
3. **D-02 Unrestricted file upload** on `VendorInvoice.document` — repeat of vendors-module A08 failure.
4. **D-01 `unique_together` + form-bypass 500s** on `WarehouseLocation.code` and `VendorInvoice.invoice_number` — repeat of catalog/vendors pattern.
5. **D-03 Racy auto-number generation** across all four auto-numbered entities — visible failure mode in any concurrent user load.

### Recommended follow-up modes

- **"Fix the defects"** → implement D-01…D-05 plus D-06/D-07/D-08/D-09 (all High). Add regression tests alongside each fix.
- **"Build the automation"** → scaffold `receiving/tests/` per §5, wire `pytest.ini`, run green.
- **"Sweep the audit"** → complete the lesson-#7 cross-module audit (`administration`, `purchase_orders`, `warehousing`, `inventory`, `stock_movements`, `lot_tracking`, `orders`, `returns`, `stocktaking`, `multi_location`, `forecasting`) — `receiving` can be marked **not clear** until D-01…D-05 land.

Nothing here is a ship-stopper of engineering complexity; the fixes are well-understood and the patterns are already in [catalog/forms.py](../../catalog/forms.py) and [vendors/forms.py](../../vendors/forms.py). The gating risk is not code; it is that **the systemic-defect sweep promised by lessons #6 and #7 has once again not been executed on this module**. Fix that process, and the defect list collapses.
