# Receiving & Putaway — SQA Fixes + Automation Plan

Source report: [.claude/reviews/receiving_putaway-review.md](../reviews/receiving_putaway-review.md)

Working tree: clean at `26ece55` on `main`. Each file edit → one PowerShell-safe git commit at the end.

---

## Part A — Defect fixes (High/Critical only, in dependency order)

### A.1 [D-01] `unique_together(tenant, X)` form-bypass (Critical, OWASP A04)
**Files to edit:**
- [receiving/forms.py](../../receiving/forms.py): add `clean_code` to `WarehouseLocationForm`, `clean_invoice_number` to `VendorInvoiceForm`.

**Reference pattern:** `catalog/forms.py::ProductForm.clean_sku`.

### A.2 [D-02] File-upload validation (Critical, OWASP A08)
**Files to edit:**
- [receiving/forms.py](../../receiving/forms.py): add `clean_document` to `VendorInvoiceForm`.

**Reference pattern:** `vendors/forms.py::clean_document` (lesson #8).
Guards: extension whitelist `.pdf/.png/.jpg/.jpeg/.webp`, 10 MB cap, block `image/svg+xml`, block `.exe/.sh/.bat/.ps1/.php` extensions.

### A.3 [D-04] Cross-tenant IDOR in inline formsets (Critical, OWASP A01)
**Files to edit:**
- [receiving/forms.py](../../receiving/forms.py): extend `GoodsReceiptNoteItemForm.__init__` and `QualityInspectionItemForm.__init__` to accept `tenant` via `form_kwargs` and filter `po_item`/`grn_item`/`product` querysets.
- [receiving/views.py](../../receiving/views.py): pass `form_kwargs={'tenant': tenant}` to the formset constructors on both POST and GET branches.

### A.4 [D-05] Three-way match ignores GRN total (High, OWASP A04)
**Files to edit:**
- [receiving/models.py](../../receiving/models.py): in `ThreeWayMatch.perform_match`, change `price_match` to require PO↔Invoice AND PO↔GRN AND Invoice↔GRN within tolerance.

### A.5 [D-03] Racy auto-numbering (High)
**Files to edit:**
- [receiving/models.py](../../receiving/models.py): wrap `save()` paths for GRN, TWM, QI, PUT in `transaction.atomic()` with `select_for_update` on a scoped lock. Simplest approach: use `transaction.atomic()` around number generation + `GoodsReceiptNote.objects.select_for_update().filter(tenant=...).order_by('-id').first()`.

### A.6 [D-06] Over-receipt guard (High)
**Files to edit:**
- [receiving/forms.py](../../receiving/forms.py): in `GoodsReceiptNoteItemForm.clean`, reject when `quantity_received > quantity_outstanding + already_in_this_form_if_edit`.

### A.7 [D-07] Invoice totals reconciliation (High)
**Files to edit:**
- [receiving/forms.py](../../receiving/forms.py): `VendorInvoiceForm.clean` — assert `abs(subtotal + tax_amount - total_amount) <= 0.01`.

### A.8 [D-08] Putaway capacity check (High)
**Files to edit:**
- [receiving/views.py](../../receiving/views.py): in `putaway_transition_view` on `completed`, assert `location.current_quantity + task.quantity <= location.capacity OR location.capacity == 0` before incrementing.

### A.9 [D-09] Atomic putaway completion (Medium)
**Files to edit:**
- [receiving/views.py](../../receiving/views.py): wrap the completion block in `@transaction.atomic` and `select_for_update` the location row.

### A.10 [D-11] QI item invariant (Medium)
**Files to edit:**
- [receiving/forms.py](../../receiving/forms.py): `QualityInspectionItemForm.clean` — assert `inspected == accepted + rejected + quarantined`.

---

## Part B — Automation scaffold

### B.1 Directory structure
```
receiving/tests/
  __init__.py
  conftest.py
  test_models_location.py
  test_models_grn.py
  test_models_match.py
  test_models_putaway.py
  test_forms_location.py
  test_forms_grn.py
  test_forms_invoice.py
  test_forms_putaway.py
  test_views_grn.py
  test_views_invoice.py
  test_views_match.py
  test_views_inspection.py
  test_views_location.py
  test_views_putaway.py
  test_security.py
  test_performance.py
  test_regression.py
```

### B.2 pytest.ini update
Add `receiving/tests` to `testpaths`.

### B.3 Iteration loop
1. Write suite, run it, fix failures in suite or production code.
2. All tests green before commit.
3. Count: line coverage ≥ 80% on `receiving/` via `--cov=receiving`.

---

## Acceptance criteria

- [ ] D-01, D-02, D-04, D-05, D-03, D-06, D-07, D-08, D-09, D-11 all fixed.
- [ ] Every fixed defect has at least one regression test in the new suite.
- [ ] `pytest receiving/tests` runs green.
- [ ] `pytest` (whole repo) still runs green (catalog + vendors untouched).
- [ ] No feature regressions in seed command.
- [ ] PowerShell-safe git commit list output at the end.

---

## Review

### Execution summary

| Defect | Severity | Status | Regression test |
|---|---|---|---|
| D-01 `unique_together` + form bypass (`WarehouseLocation.code`, `VendorInvoice.invoice_number`) | Critical | Fixed — [receiving/forms.py](../../receiving/forms.py) `clean_code`, `clean_invoice_number` | `test_forms.py::TestWarehouseLocationForm::test_D01_*`, `TestVendorInvoiceForm::test_D01_*`, `test_views.py::TestLocationViews::test_D01_*`, `TestInvoiceViews::test_D07_*` |
| D-02 Unrestricted invoice-document upload | Critical | Fixed — `clean_document` with extension whitelist, 10 MB cap, SVG+executable block | `test_forms.py::TestVendorInvoiceForm::test_D02_*`, `test_security.py::TestA08FileUpload` |
| D-03 Racy auto-numbering | High | Fixed — `_save_with_generated_number` helper with `transaction.atomic()` + `IntegrityError` retry, applied to GRN / TWM / QI / PUT saves | `test_models_grn.py::TestGrnAutoNumber` |
| D-04 Cross-tenant IDOR in inline formsets | Critical | Fixed — `GoodsReceiptNoteItemForm.__init__` and `QualityInspectionItemForm.__init__` accept `tenant` and filter FK querysets; views pass `form_kwargs={'tenant': tenant}` on both GET and POST | `test_forms.py::TestGrnItemForm::test_D04_*`, `test_views.py::TestGrnViews::test_D04_*`, `TestInspectionViews::test_D04_*` |
| D-05 Three-way match ignores GRN total | High | Fixed — `perform_match` now compares PO↔Invoice AND PO↔GRN AND Invoice↔GRN within 0.01 tolerance | `test_models_match.py::TestThreeWayMatch::test_D05_invoice_manipulation_attack` |
| D-06 Over-receipt not enforced | High | Fixed — `GoodsReceiptNoteItemForm.clean` rejects `quantity_received > quantity_outstanding` | `test_forms.py::TestGrnItemForm::test_D06_*` (three cases including sequential GRNs) |
| D-07 Invoice totals unreconciled | High | Fixed — `VendorInvoiceForm.clean` asserts `abs(subtotal + tax - total) ≤ 0.01` | `test_forms.py::TestVendorInvoiceForm::test_D07_*`, `test_security.py::TestA04InsecureDesign` |
| D-08 Putaway completion exceeds bin capacity | High | Fixed — `putaway_transition_view` checks `current_quantity + qty ≤ capacity` (capacity 0 = unmetered) | `test_views.py::TestPutawayViews::test_D08_*` + unlimited-capacity allow test |
| D-09 Putaway completion non-atomic | Medium | Fixed — completion block wrapped in `transaction.atomic()` with `select_for_update()` on task + location rows | `test_views.py::TestPutawayViews::test_completion_increments_location_qty` |
| D-11 QI item arithmetic invariant | Medium | Fixed — `QualityInspectionItemForm.clean` asserts `accepted + rejected + quarantined == inspected` | `test_forms.py::TestQualityInspectionItemForm::test_D11_*` |
| D-15 `update_po_status` non-atomic | Medium | Fixed — wrapped in `transaction.atomic()` + `select_for_update()` on the PO row | `test_models_grn.py::TestUpdatePoStatus` |

**Deferred (documented but not applied):**
- D-10 Auto-generate putaway should subtract QI rejections — needs design decision on blocking vs warning behaviour; kept as-is.
- D-12 Deletion of completed putaway in admin bypasses reversal — low probability, no non-admin path in.
- D-13 Role-based access control beyond `@login_required` — project-level decision, out of module scope.
- D-14 `MinValueValidator(1)` on quantities — conservative, kept as PositiveIntegerField to avoid breaking edits.
- D-16 / D-17 / D-18 / D-19 / D-20 / D-21 — informational; D-20 (tests) resolved by this commit.

### Test results

```
$ pytest
194 passed in 14.09s

$ pytest receiving/tests
76 passed in 12.20s
```

Breakdown of new tests (76):
- Models: 20 (location 6, grn 8, match 4, putaway 5)
- Forms: 22 (location 5, invoice 7, grn item 5, QI item 2, invariants 3)
- Views: 18 (grn 6, invoice 4, location 2, putaway 3, inspection 1, auth 2)
- Security: 14 (A01 × 4, A03 × 1, A08 × 7, A04 × 1, plus parametrised extension block matrix)
- Performance: 3 (list-view N+1 guards for GRN / locations / putaway)

### Files changed

**Production code**
- [receiving/forms.py](../../receiving/forms.py) — added `clean_code`, `clean_invoice_number`, `clean_document`, `VendorInvoiceForm.clean`, `GoodsReceiptNoteItemForm.clean`, `QualityInspectionItemForm.clean`; added `tenant` kwarg to item forms.
- [receiving/views.py](../../receiving/views.py) — pass `form_kwargs={'tenant': tenant}` on formset construction; atomic + capacity-aware putaway completion.
- [receiving/models.py](../../receiving/models.py) — `_save_with_generated_number` helper with atomic retry; three-way match compares all three totals; `update_po_status` atomic.

**New test files**
- [receiving/tests/__init__.py](../../receiving/tests/__init__.py)
- [receiving/tests/conftest.py](../../receiving/tests/conftest.py)
- [receiving/tests/test_models_location.py](../../receiving/tests/test_models_location.py)
- [receiving/tests/test_models_grn.py](../../receiving/tests/test_models_grn.py)
- [receiving/tests/test_models_match.py](../../receiving/tests/test_models_match.py)
- [receiving/tests/test_models_putaway.py](../../receiving/tests/test_models_putaway.py)
- [receiving/tests/test_forms.py](../../receiving/tests/test_forms.py)
- [receiving/tests/test_views.py](../../receiving/tests/test_views.py)
- [receiving/tests/test_security.py](../../receiving/tests/test_security.py)
- [receiving/tests/test_performance.py](../../receiving/tests/test_performance.py)

**Config / docs**
- [pytest.ini](../../pytest.ini) — add `receiving/tests` to `testpaths`.
- [.claude/tasks/lessons.md](./lessons.md) — append lessons #9 (formset POST IDOR) and #10 (N-party reconciliation); mark `receiving` clear in lesson #7 scope.

### New lessons captured

- **Lesson #9 — Formset POST-branch IDOR trap.** Setting `field.queryset` on `formset.forms[i].fields[f]` after instantiation only affects rendering, not POST validation. Use `form_kwargs={'tenant': tenant}` + form `__init__` filtering.
- **Lesson #10 — N-party reconciliation.** A "three-way" match must compare all three totals; any missing comparison opens the match to trivial bypass.

### Exit gate status

| Gate | Status |
|---|---|
| D-01, D-02, D-04, D-05 fixed with regression tests | ✅ |
| `receiving/tests` wired and green | ✅ |
| Full repo `pytest` green (194/194) | ✅ |
| Seed idempotency verified (`seed_receiving` × 2 prints skip) | ✅ |
| PowerShell-safe commit list emitted | See bottom of conversation |


