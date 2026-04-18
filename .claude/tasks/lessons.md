# Lessons Learned

## 2026-03-21 — Procurement Module Build

### Issue 1: Missing Edit/Delete Actions
**What happened:** Built entire procurement module with only List, Add, and View pages. No Edit or Delete buttons anywhere.
**Root cause:** Focused on models/views/templates for the "happy path" and forgot CRUD completeness.
**Rule:** Every new module MUST include all 5 CRUD operations (list, create, detail, edit, delete) from the start. Added to CLAUDE.md under "CRUD Completeness Rules".

### Issue 2: Seed Command Crashed on Second Run
**What happened:** `python manage.py seed_procurement` worked first time but crashed with `IntegrityError: Duplicate entry` on second run because requisition numbers (PR-00001) have unique_together constraint.
**Root cause:** Used bare `.save()` instead of `get_or_create` or existence checks for models with unique constraints.
**Rule:** All seed commands must be idempotent — check for existing records before creating. Added to CLAUDE.md under "Seed Command Rules".

### Issue 3: Data Not Showing After Seed
**What happened:** User ran seed_procurement successfully but saw empty pages. Was logged in as superuser `admin` which has `tenant=None`.
**Root cause:** Didn't warn user about tenant isolation. All views filter by `request.tenant` which is `None` for superuser.
**Rule:** Always print tenant admin login credentials after seeding and warn that superuser won't see tenant-scoped data. Added to CLAUDE.md under "Multi-Tenancy Rules".

### Issue 4: Missing `__init__.py` in management/commands
**What happened:** Forgot to create `__init__.py` files when creating `management/commands/` directory structure.
**Root cause:** Created directory with `mkdir` but forgot Django requires `__init__.py` for package discovery.
**Rule:** Always create both `management/__init__.py` and `management/commands/__init__.py`. Added to CLAUDE.md under "Seed Command Rules".

## 2026-04-17 — Forecasting Module Build

### Issue 5: Used `&&` in Shell Commands — PowerShell ParserError
**What happened:** When user asked for all git commits in one copy, output used `&&` to chain `git add` + `git commit`. User ran them and got `The token '&&' is not a valid statement separator in this version` because they're on Windows PowerShell 5.x.
**Root cause:** Defaulted to bash/POSIX syntax without considering the user runs commands in PowerShell on Windows. PowerShell 5 requires `;` as statement separator; `&&` only works in PowerShell 7+.
**Rule:** ALWAYS use `;` (not `&&`) when chaining commands for the user to run. Applies to git bulk-commit lists and any other shell snippets. If stop-on-failure is required, put commands on separate lines instead of chaining. Added to CLAUDE.md under "GIT Commit Rule → Shell Compatibility".

## 2026-04-17 — Catalog Module SQA Remediation

### Issue 6: `unique_together(tenant, X)` bypassed at form layer when `tenant` is not a form field
**What happened:** While writing a test for "duplicate SKU in same tenant should be rejected", the view raised a 500 `IntegrityError` instead of a form error. Django's `ModelForm.validate_unique()` calls `_get_validation_exclusions()` which excludes any model field that isn't rendered on the form — so `tenant` was excluded, the partial unique check `(sku,)` found no clash, and the duplicate reached the DB.
**Root cause:** The module pattern of "set `instance.tenant = self.tenant` only inside `save()`" means the form's `_post_clean()` runs with `instance.tenant_id = None`, and Django skips unique_together constraints that involve excluded fields.
**Rule:** For every `ModelForm` backed by a model with `unique_together = ('tenant', <field>)`, either (a) add an explicit `clean_<field>()` that filters by `self.tenant` and raises a `ValidationError` on duplicate, or (b) override `_get_validation_exclusions()` to drop `'tenant'` from the exclusion set. Option (a) is simpler and preserves Django's default exclusion behavior. See `catalog/forms.py:ProductForm.clean_sku` as the reference implementation.
**Scope:** Audit every other module (`administration`, `purchase_orders`, `receiving`, `warehousing`, `inventory`, `stock_movements`, `lot_tracking`, `orders`, `returns`, `stocktaking`, `multi_location`, `forecasting`) for the same bug — any `ModelForm` saving a model with `unique_together` that includes `tenant` is potentially affected.

## 2026-04-17 — Vendors Module SQA Remediation

### Issue 7: Lesson #6 recurred in `vendors/` — module-wide audit was skipped
**What happened:** During the vendors SQA review, Django-shell probes confirmed the same `unique_together(tenant, X)` + missing `clean_<field>` trap on **two** models at once — `Vendor.company_name` and `VendorContract.contract_number`. Duplicate input produced a 500 `IntegrityError` instead of a form error. Lesson #6 explicitly scoped an audit of every other module, but that audit was never carried out, so the bug shipped in vendors the same way it shipped in catalog.
**Root cause:** Lesson #6 was captured as knowledge but not converted into an actionable sweep. A rule in the lessons log does not enforce itself.
**Rule:** When a cross-cutting defect pattern is added to `lessons.md`, the same session (or the next one) MUST run a grep-level sweep across all listed modules and either (a) fix the recurrences immediately, (b) log them as tickets, or (c) update the lesson to note the sweep was completed. Concretely for this pattern: `grep -rn "unique_together" */models.py` across every tenant-scoped app, then for each match confirm the corresponding form has a `clean_<field>` guard.
**Scope still outstanding after this pass:** `administration`, `warehousing`, `inventory`, `stock_movements`, `lot_tracking`, `orders`, `returns`, `stocktaking`, `multi_location`, `forecasting` — still need the same audit. `catalog`, `vendors`, `purchase_orders`, and `receiving` are now clear.

### Issue 8: OWASP-A08 file-upload pattern repeats across modules
**What happened:** `VendorContract.document = FileField(upload_to='…')` accepted arbitrary file types (`.exe`, `.svg`, `.php`, polyglots) with no size cap. This is the A08 failure mode captured in every SQA skill run, but the project has no shared `validate_contract_document` / `validate_safe_upload` utility, so every new module reinvents (or forgets) the guard.
**Root cause:** No shared upload-safety helper. Each module's form has to hand-roll extension whitelist + size cap + MIME check.
**Rule:** Before building any future module with `FileField`, extract the pattern in `vendors/forms.py:clean_document` into `core/validators.py:SafeFileUploadValidator(allowed_extensions, max_size, blocked_content_types)` and reuse it. Until that utility exists, every `FileField` added to a model must be reviewed for (a) extension whitelist, (b) explicit size cap ≤ 10 MB, (c) SVG / executable content-type block, (d) authenticated-only download.

## 2026-04-17 — Receiving Module SQA Remediation

### Issue 9: Inline formset cross-tenant IDOR (repeat of systemic "forms filter only in GET" trap)
**What happened:** `receiving/views.py` GRN create/edit and QualityInspection create/edit passed tenant-filtered querysets onto `formset.forms[*].fields[*].queryset` **only inside the GET branch** (and only to the pre-rendered forms). On POST the inline formset rebuilt forms from `request.POST` and validated against the default (unfiltered) querysets, so a tenant-B user could POST `items-0-po_item=<tenant-A po_item.pk>` and link a foreign PO item to their own GRN. Auto-caught by `get_object_or_404(..., tenant=request.tenant)` on GETs but invisible on the POST path.
**Root cause:** The idiom "set `field.queryset = filtered` on the bound form at render time" works for GET but **does not** re-apply during POST validation because Django rebuilds the forms. Needs `form_kwargs={'tenant': tenant}` + form `__init__` filtering.
**Rule:** For any `inlineformset_factory(..., form=X)` where the child rows reference tenant-scoped foreign keys, the child form MUST accept `tenant` in `__init__`, filter ALL FK `querysets` there, and be instantiated via `formset_factory(..., form_kwargs={'tenant': tenant})` on BOTH the GET and POST branches. Do not rely on post-construction monkey-patching of `field.queryset` — it does not survive formset revalidation. Reference: `receiving/forms.py:GoodsReceiptNoteItemForm` and `receiving/views.py:grn_create_view` after D-04 fix.
**Scope:** Audit every other module with inline formsets — `purchase_orders`, `orders`, `returns`, `stocktaking`, `stock_movements`, `warehousing` — for the same POST-branch IDOR.

## 2026-04-17 — Warehousing Module SQA Remediation

### Issue 11: Lesson #6 recurred a **third time** — `unique_together + tenant` trap now hit three modules
**What happened:** The warehousing SQA review shell-probed `ZoneForm` with a duplicate code within a tenant — `form.is_valid()` returned `True`, `form.save()` raised `IntegrityError (1062 Duplicate entry)` → 500. The same class of bug landed on four forms this time: `ZoneForm`, `AisleForm`, `RackForm`, `BinForm`. This is the same failure mode captured in lesson #6 (catalog/Product) and lesson #7 (vendors/Vendor + VendorContract).
**Root cause:** The audit scoped in lesson #7 ("administration, warehousing, inventory, stock_movements, lot_tracking, orders, returns, stocktaking, multi_location, forecasting — still need the same audit") was again not performed proactively. The trap was only found when someone ran a fresh SQA review on the module. **Pattern:** adding a lesson to the log has zero enforcement power; only a grep-level sweep closes the issue module-wide.
**Rule (elevated):** This pattern must now be handled **on the first line of every new module review**, not at the end of the review. Specifically: for the target module, run `grep -rn "unique_together" <module>/models.py` and for each match verify the corresponding `ModelForm` has a `clean_<field>` guard. If `tenant` is in the tuple and isn't a form field, that guard is **mandatory** and the review must list it as at least a High defect.
**Structural fix adopted in warehousing:** Rather than repeating the identical `clean_code` four times, [warehousing/forms.py](../../warehousing/forms.py) defines a reusable `TenantUniqueCodeMixin` and mixes it into `ZoneForm`, `AisleForm`, `RackForm`, `BinForm`. Future modules with a `(tenant, code)` unique pair should lift this mixin (or promote it to `core/forms.py` after the next module shows it again, which is probable).
**Scope still outstanding:** `administration`, `inventory`, `lot_tracking`, `orders`, `returns`, `stocktaking`, `multi_location`, `forecasting`. Clear after this pass: `catalog`, `vendors`, `purchase_orders`, `receiving`, `warehousing`, `stock_movements` (no `unique_together(tenant, X)` tuples in `stock_movements/models.py` — module is inherently out of scope for this lesson).

### Issue 12: Status-transition views shipped without audit + RBAC (pattern repeats)
**What happened:** `warehousing/views.py:crossdock_status_view` and `crossdock_reopen_view` were plain `@login_required`. Any tenant user could reopen a cancelled cross-dock order or cancel a live one. No `core.AuditLog` row was written either — the same pairing as vendors D-09/D-10 and receiving. The defect is predictable enough that it should be covered by module-scaffolding templates.
**Rule:** Any view that mutates a model's `status` (or equivalent state-machine field) must satisfy THREE guards: (1) `@tenant_admin_required` — read is OK for all tenant users, but writes gate on role. (2) `can_transition_to(new_status)` check — the model owns the transition table. (3) `emit_audit(request, 'transition', obj, changes=f'{old}->{new}')` on the success branch. Missing any one is a defect. This triad is the shape of every state-transition view in vendors/receiving/warehousing after remediation — codify it as `core.views.transition_view(model, decorator, audit_action)` helper in a future pass.

### Issue 13: Template badge conditions drift silently when model choices are renamed
**What happened:** `templates/warehousing/bin_list.html` was checking `bin_type == 'picking'`, `'reserve'`, `'staging'`, `'receiving'`, `'shipping'` — but the model's `Bin.BIN_TYPE_CHOICES` were `'standard'`, `'bulk'`, `'pick'`, `'pallet'`, `'cold'`, `'hazmat'`. Five branches were dead code; only `'bulk'` matched; the rest silently rendered a grey generic badge. This is the second variant of the pattern already captured in CLAUDE.md "Badge values must match model CHOICES" — but the rule there only covers the case where badge conditions exist; it does not defend against the choices being **renamed after the template was written**.
**Rule:** When renaming a value in a `CHOICES` constant, search the template tree for every literal match before committing: `grep -rn "'<old_value>'" templates/` and rewrite the branches. Better still: replace `{% if obj.field == 'x' %}...` badge blocks with a template filter driven by a dict keyed on choice value, so a rename at the model level automatically invalidates the lookup and is caught by tests. Reference fix: [templates/warehousing/bin_list.html:126-140](../../templates/warehousing/bin_list.html#L126-L140).

## 2026-04-17 — Stock Movements Module SQA Remediation

### Issue 14: Raw POST parallel-array IDOR — third variant of the formset-IDOR family
**What happened:** `stock_movements/views.py:transfer_create_view` and `transfer_edit_view` were building child rows from `request.POST.getlist('item_product')` + `getlist('item_quantity')` — **not** via a Django formset — and then calling `StockTransferItem.objects.create(..., product_id=int(product_ids[i]))` with no tenant verification. A tenant-A user could POST `item_product=<tenant-B product.pk>` and link a foreign product into their own transfer. Verified in Django shell: item saved with `item.product.tenant_id != transfer.tenant_id`. This is the third variant of the same cross-tenant FK-injection family:
- **Variant 1** (lesson #6/#7/#11): `unique_together(tenant, X)` + `ModelForm.clean_<field>` missing.
- **Variant 2** (lesson #9): `inlineformset_factory` + tenant filter only applied in GET branch.
- **Variant 3** (this lesson): raw `request.POST.getlist(...)` parallel arrays, no Django form at all.

**Root cause:** Every new child-row pattern someone invents has to re-discover tenant filtering. The fix has been repeated four times now under three different shapes; the project still doesn't have a shared "resolve IDs against a tenant-scoped queryset" helper.

**Rule:** Any view that constructs child rows from raw POST — regardless of whether a ModelForm / Formset is involved — MUST resolve every foreign-key ID against a tenant-scoped queryset BEFORE `.objects.create(...)`. Pattern to copy: `stock_movements/views.py:_parse_transfer_items` after the D-01 fix. The helper should (a) collect all valid PKs in one query, (b) reject IDs not present in that set, (c) aggregate field-level errors, (d) return `(items, errors)` so the view can branch cleanly.

**Meta-rule:** When a defect class reaches three variants, extract the shared contract. Ticket: create `core/views.py:resolve_tenant_ids(request, tenant, field, model, qs_filters=None)` and retrofit `stock_movements`, `receiving` (already on formsets), `warehousing`, plus the next module that shows the pattern. Until that helper ships, every new module doing raw POST parsing is a likely defect.

**Scope:** Audit `orders`, `returns`, `stocktaking`, `purchase_orders` (line items), `lot_tracking` for raw POST `getlist` + `.create(product_id=int(...))` patterns.

### Issue 10: Three-way match price check that only considers two parties
**What happened:** `ThreeWayMatch.perform_match` compared PO total vs Invoice total for the price check. A user-entered `VendorInvoice.total_amount` that equals `PO.grand_total` while the GRN was short-received passed as "matched". The `grn_total` property was computed but never read. Invoice manipulation → financial integrity hole.
**Rule:** Any comparison that purports to be a "three-way" check MUST compare all three totals (PO↔Invoice AND PO↔GRN AND Invoice↔GRN) within tolerance. If a module claims to reconcile N entities, enforce N comparisons, not N-1. More generally: every user-entered money field that feeds into a downstream correctness check must be validated against its peers (`clean()` reconciliation) before it can influence business logic. Reference: `receiving/models.py:ThreeWayMatch.perform_match` and `receiving/forms.py:VendorInvoiceForm.clean` after D-05/D-07 fix.


## 2026-04-17 — Lot & Serial Tracking SQA Remediation

### Issue 14: `unique_together + tenant` hit a **fourth** module — trigger helpers promoted to `core/`
**What happened:** Lot/Serial Number Tracking review probed a duplicate `SerialNumber` and got the same `IntegrityError (1062 Duplicate entry)` → 500 seen in catalog (lesson #6), vendors (#7), and warehousing. Four modules is past the point where "audit every module on touch" works as a mitigation — the pattern now needs a shared implementation that gets picked up by default.
**Root cause:** The `TenantUniqueCodeMixin` written for warehousing (D-01 fix of that review) and the `tenant_admin_required` + `emit_audit` helpers written for vendors/warehousing were byte-identical copies sitting in `vendors/decorators.py` and `warehousing/decorators.py`. Nothing encouraged a new module author to reach for them; lot_tracking reinvented none of it and shipped none of it.
**Rule (structural fix):** When the same helper lands in a second module byte-identical, it should stay co-located for one more review cycle. When it lands in a **third** module, it MUST be promoted to `core/` in the same PR. lot_tracking triggered this: on 2026-04-17 `tenant_admin_required`, `emit_audit` went to [core/decorators.py](../../core/decorators.py); `TenantUniqueCodeMixin` (generalised with a `tenant_unique_field` attribute so it handles any `(tenant, X)` unique pair, not only `(tenant, code)`) went to [core/forms.py](../../core/forms.py). New modules must import from `core.*` first.
**Scope still outstanding:** `administration`, `orders`, `returns`, `stocktaking`, `multi_location`, `forecasting` still need the same SQA audit (catalog, vendors, purchase_orders, receiving, warehousing, inventory, stock_movements, lot_tracking are now clear). Existing `vendors/decorators.py` and `warehousing/decorators.py` can be converted to thin re-exports of `core.decorators` in a follow-up sweep — low-priority since the tests are green and the copies are still byte-identical to the new canonical home.

### Issue 15: `timezone.now().date()` vs `date.today()` midnight-boundary test flakes
**What happened:** `LotBatch.is_expired` and `SerialNumber.is_warranty_expired` compute their reference day via `timezone.now().date()` — which is UTC when `USE_TZ=True`. The first `pytest` run produced three failures because the test file used `date.today()` (local time). Local time was `2026-04-18`, but UTC was still `2026-04-17`, so `expiry_date = date.today() - 1day = 2026-04-17` was not less-than `timezone.now().date() = 2026-04-17`, and `is_expired` returned `False` against the test expectation.
**Root cause:** The model speaks tenant-wall-clock time (or UTC); the test wrote local-wall-clock time. On most days they are equal and the bug is invisible; on a day when the developer is running tests across midnight UTC-vs-local, three tests flake simultaneously.
**Rule:** Any test asserting a timezone-aware model property that uses `timezone.now()` internally MUST derive its reference day from `timezone.now().date()` too — never from `datetime.date.today()`. Helper pattern adopted in `lot_tracking/tests/test_models.py`: `def today(): return timezone.now().date()` and use it everywhere. Lint-worthy but low enough priority to stay a convention for now.


## 2026-04-18 — Orders Module SQA Remediation

### Issue 16: Auto-progress state-machine bypass (orders D-08/D-09)
**What happened:** `shipment_dispatch_view` unconditionally set `so.status = 'shipped'` when the SO was in `packed`/`in_fulfillment`/`picked` — but `in_fulfillment→shipped` and `picked→shipped` are NOT in `SalesOrder.VALID_TRANSITIONS`. The view wrote state the model explicitly forbade. Same class on `so_resume_view`: smart-picked `resume_to='shipped'` from `on_hold`, which is not in `VALID_TRANSITIONS['on_hold']`. Both paths silently corrupted the state machine.
**Root cause:** "Auto-progress" branches in auxiliary views (shipment/pick/pack completion) bypass the `can_transition_to` guard they rely on elsewhere. When a module declares a `VALID_TRANSITIONS` table, every state write in every view — including auto-progress cascades — must go through that gate.
**Rule:** For every module with a `VALID_TRANSITIONS` table, grep `<module>/views.py` for literal `\.status = '[^']*'` and, for each match, verify the immediately preceding line calls `.can_transition_to(...)`. If auto-progress is legitimate, refuse the whole upstream action when the downstream transition would be invalid; do not silently downgrade to a "skip the SO update" fallback (which is what the reviewer will notice as a correctness bug, not a UX bug). Reference fix: [orders/views.py:shipment_dispatch_view](../../orders/views.py) refuses to dispatch when `so.status != 'packed'`.

### Issue 17: Inventory deduction used reservation qty instead of picked qty (orders D-10)
**What happened:** `shipment_delivered_view` decremented `StockLevel.on_hand` by `InventoryReservation.quantity` — which is the originally-reserved amount, not what pickers actually picked. When `PickListItem.picked_quantity < ordered_quantity` (short-pick / shrinkage), the view over-deducted `on_hand` by the missing delta, making stock records drift vs physical.
**Root cause:** `on_hand` and `allocated` are semantically different: `allocated` tracks commitment (released by reservation qty); `on_hand` tracks physical stock (deducted by what left the shelf). Conflating them is easy because they share the reservation record.
**Rule:** When a fulfillment event closes a reservation, the two decrements must be driven by different sources: `allocated -= reservation.quantity`, `on_hand -= SUM(PickListItem.picked_quantity)` grouped by `(product, warehouse)`. Any shortfall (reservation > picked) becomes a stock adjustment for shrinkage tracking, not an `on_hand` under-count. Audit any other module that decrements `StockLevel.on_hand` inside a status-change view (`inventory`, `returns`, `stock_movements`) for the same conflation.

### Issue 18: `unique_together + tenant` trap sweep — now clear for 8 modules, `TenantUniqueCodeMixin` import density check is viable
**What happened:** Orders became the 5th module to hit the same trap (`Carrier.code` + `unique_together(tenant, code)` with no form guard). Fixed in one line by mixing `core.forms.TenantUniqueCodeMixin` into `CarrierForm` — the helper was already centralised by lesson #14.
**Observation (worth codifying):** Since `TenantUniqueCodeMixin` is now in `core/forms.py` and byte-stable, the audit can be compressed from "inspect every ModelForm that backs a model with `unique_together` that contains `tenant`" to the much cheaper grep:
```
# any form backing a model with unique_together that contains 'tenant' MUST either import TenantUniqueCodeMixin or define a clean_<field>() for the unique field.
grep -L "TenantUniqueCodeMixin\|clean_code\|clean_sku\|clean_serial_number\|clean_company_name\|clean_contract_number" <module>/forms.py
```
If the forms file matches `unique_together.*tenant` in models.py but returns non-empty from the grep above, it's the bug.
**Scope still outstanding:** `administration`, `inventory` (re-audit after latest inventory fixes), `returns`, `stocktaking`, `multi_location`, `forecasting`. Clear after this pass: `catalog`, `vendors`, `purchase_orders`, `receiving`, `warehousing`, `lot_tracking`, `stock_movements`, `orders`.

### Issue 19: Inline-formset IDOR scope audit — now clear for 5 modules
**What happened:** Orders is the 3rd module where lesson #9's outstanding audit actually caught a bug in production. Two formsets needed the fix: `SalesOrderItemFormSet` (product FK) and `PickListItemFormSet` (product + bin FKs — the first 2-FK case).
**Reaffirmed rule:** The sweep that closes this class is:
```
grep -rn "inlineformset_factory" <module>/forms.py
# For each match, verify: child form __init__ accepts tenant; every FK queryset is filtered; views use form_kwargs={'tenant': tenant} on BOTH GET and POST.
```
Post-construction `field.queryset = filtered` on pre-rendered forms is a known false positive — it does not survive POST revalidation.
**Scope still outstanding:** `returns`, `stocktaking`, `multi_location`. Clear after this pass: `purchase_orders`, `receiving`, `warehousing`, `stock_movements`, `orders`.


## 2026-04-18 — Returns Management (RMA) Module SQA Remediation

### Issue 20: `@require_POST` hygiene on state-transition endpoints — defect class reaches four modules
**What happened:** Returns shipped 14 state-transition views (rma submit/approve/reject/receive/close/cancel; inspection start/complete; disposition process/cancel; refund process/fail/cancel) guarded only by `@login_required`, with no `@require_POST`. Django-shell probe confirmed `GET /returns/<pk>/submit/` changed status `draft → pending`; worse, `GET /returns/refunds/<pk>/process/` ran the financial write. Because GET requests are not CSRF-protected, any logged-in user loading an `<img src>` or `<a href>` from a hostile page would trigger a drive-by state change. Same family as vendors/receiving/warehousing "status-transition without role gate" captured in lesson #12, plus the GET-vs-POST dimension.
**Root cause:** The triad "require_POST + tenant_admin_required + emit_audit" is now a well-known pattern — but the *missing-require_POST* half of it keeps getting shipped because the module scaffolding starts by copying a plain `@login_required` view. Nothing forces the `@require_POST` decorator onto transition endpoints.
**Rule:** The state-transition triad captured in lesson #12 is now **four decorators**, in this exact order (outside-in: auth first, then method, then view logic):
```python
@tenant_admin_required
@require_POST
def transition_view(request, pk):
    obj = get_object_or_404(Model, pk=pk, tenant=request.tenant)
    if not obj.can_transition_to(new_status):
        messages.error(...); return redirect(...)
    old = obj.status; obj.status = new_status; obj.save()
    emit_audit(request, 'model_transitioned', obj, changes=f'{old}->{new_status}')
    ...
```
Audit sweep going forward: `grep -rn "def [a-z_]*_view.*status" <module>/views.py` then confirm each match has `@require_POST` + `@tenant_admin_required`. Missing either is a defect.
**Scope still outstanding:** `administration`, `stocktaking` (partial), `multi_location`, `forecasting`. Clear after this pass: `catalog`, `vendors`, `purchase_orders`, `receiving`, `warehousing`, `stock_movements`, `orders`, `lot_tracking`, `returns`.

### Issue 21: Stock-ledger asymmetry between increase and decrease paths
**What happened:** `returns/views.py:disposition_process_view` had two code paths — restock (increase) and scrap (decrease). The restock path wrote `StockAdjustment(increase)` AND incremented `StockLevel.on_hand`. The scrap path wrote `StockAdjustment(decrease)` but **did not** decrement `on_hand`. Adjustments are an audit ledger; `on_hand` is the physical balance. Writing only to the ledger but not the balance means the two tables drift apart over time until stock reports no longer match physical counts. Identical shape to lesson #17 (orders D-10): decrement was picked from reservation qty when it should have come from picked qty.
**Root cause:** Whoever writes the decrease branch assumes "StockAdjustment will be applied later by a background job" (it isn't). There's no single helper that writes a paired `StockAdjustment` + `on_hand` update; every module hand-rolls it and forgets half.
**Rule:** Every time a module writes a `StockAdjustment`, the surrounding transaction MUST mutate `StockLevel.on_hand` in the same direction by the same amount, clamped at 0. Audit pattern:
```
grep -rn "StockAdjustment.objects.create" -- */views.py
# For each match, verify the immediately surrounding code also mutates
# StockLevel.on_hand. A `select_for_update()` is required for concurrency.
```
Until a `core.inventory.apply_adjustment(stock_level, adjustment_type, qty, reason, actor)` helper lands, every hand-rolled write is a candidate defect.
**Scope sweep target:** `inventory`, `receiving`, `orders` (shipment_delivered), `stock_movements`, `returns` — already covered. Remaining unreviewed: `stocktaking`, `multi_location`.

### Issue 22: `unique_together + tenant` trap — 5 modules scope closed; returns out of scope
**What happened:** Returns has `unique_together('tenant', 'rma_number')` on four models but the trap does NOT apply here — those fields are internally auto-generated via `_generate_rma_number()` / `_generate_refund_number()` etc., never exposed as form fields. So the form layer never needs a `clean_<field>` guard. Instead the defect shape is "two concurrent writers compute the same next number" — which manifests as a 500 `IntegrityError` under race. Fixed by `_save_with_number_retry()` at [returns/models.py:9-27](../../returns/models.py#L9-L27) — a `transaction.atomic()` + retry-on-IntegrityError loop.
**Rule:** When evaluating lesson #6 / #7 / #11 / #14 against a new module, first determine whether the unique field is **user-visible** or **auto-generated**:
- User-visible field (SKU, code, company_name) → needs `clean_<field>` on the form or `TenantUniqueCodeMixin`.
- Auto-generated number (RMA-00001, PO-00001, SO-00001) → needs `transaction.atomic()` + retry loop in `save()`.
Both are tenant-scoped uniqueness problems, but they surface in different layers and need different fixes. Conflating them costs time.
**Scope for number-generation race:** Audit every `_generate_<X>_number()` method for the same race-and-retry pattern:
```
grep -rn "_generate.*_number" -- */models.py
# For each match, verify the caller's save() wraps the write in a retry loop.
```
Returns is the first module where this was explicitly fixed; `orders`, `purchase_orders`, `receiving`, `lot_tracking` all have auto-generated numbers and are candidates for the same sweep.

## 2026-04-18 — Stocktaking Module SQA Remediation

### Issue 23: State-change views accepting GET are a CSRF hole, not just a convention gap
**What happened:** Stocktaking had **eight** state-mutation views (`freeze_release`, `schedule_run`, `count_start`, `count_review`, `count_cancel`, `adjustment_approve`, `adjustment_reject`, `adjustment_post`) that accepted GET. `adjustment_post_view` in particular rewrote `StockLevel.on_hand`. Any authenticated session visiting a third-party page with `<img src="/stocktaking/adjustments/<pk>/post/">` would mutate stock without any CSRF check.
**Root cause:** The templates *already* used POST forms with `{% csrf_token %}` for all eight — a reviewer reading the HTML would believe the module was safe. But the view itself had no server-side enforcement, so the client was the only line of defence.
**Rule:** Any view that changes state MUST have `@require_POST` (or equivalent method-check) on the view — never rely on templates alone. Reviewing templates to judge CSRF safety is insufficient; the server must enforce. Pair with `emit_audit` for the audit trail.
**How to apply:** When auditing a new module, for every view function grep for state mutations (`.save()`, `.delete()`, `.create()`, `.status =`). If found and the view lacks `@require_POST` / an `if request.method != 'POST'` guard, flag as Critical.

### Issue 24: Non-atomic multi-write "post" flows leak partial state
**What happened:** Stocktaking's `adjustment_post_view` wrote a `StockAdjustment` row, then mutated `StockLevel.on_hand`, inside a `for item in ...` loop. No `@transaction.atomic`. Any exception mid-loop (missing product, concurrent write, validator raise) left half the items posted to stock while the adjustment stayed in `approved` — rerunning would double-apply the first half.
**Root cause:** Pattern copied from receiving/putaway where each line-item write is naturally independent. Stocktaking has a cross-entity invariant (adjustment + ledger + level must all flip together) that demands atomicity.
**Rule:** Any view that performs >1 DB mutation spanning multiple models or multiple rows MUST wrap the block in `with transaction.atomic():`. Use `select_for_update()` on the rows that concurrent writers might touch. The audit log emission belongs inside the same atomic block, so a rolled-back mutation leaves no ghost audit row.
**Verification recipe:** `test_D02_atomic_rollback_on_failure` at [stocktaking/tests/test_views_adjustment.py](../../stocktaking/tests/test_views_adjustment.py) — mock `StockAdjustment.objects.create` to succeed once then raise, then assert `StockLevel.on_hand` is unchanged and `StockAdjustment.objects.count() == 0`.

### Issue 25: Per-parent uniqueness is as important as per-tenant uniqueness
**What happened:** `StockVarianceAdjustment` had no constraint preventing two adjustments on the same `StockCount`. Both could be approved, both could be posted — the second overwrote stock and inflated the audit ledger. The fix wasn't a DB constraint (would have required a migration and broken existing cancelled/rejected adjustments) but an early-return in the post view: `if count.status == 'adjusted': return error`.
**Root cause:** Reviewed uniqueness through the `(tenant, number)` lens (lesson #6/#22) and missed the *parent-child* uniqueness invariant ("one posted adjustment per count").
**Rule:** For every approval/post workflow, ask: "What's the maximum number of successful posts against this parent record?" If the answer is "1", guard the transition — either with a DB constraint (cheapest: add `unique_together` or a partial unique index) or a view-level status check on the *parent*, not just the child.
**How to apply:** When reviewing a new approval workflow, list every `.status = 'posted'` / `.status = 'completed'` transition and ask: "Could this parent get posted again via a sibling child record?" If yes, add a guard.

### Issue 26: `follow=True` with Django test client hides pre-existing template bugs
**What happened:** Multiple stocktaking tests used `r = client.post(url, follow=True)` then `assert b'...' in r.content` to check flash messages. These failed with `VariableDoesNotExist: Failed lookup for key [username] in None` — unrelated to the behaviour being tested — because the redirected detail pages dereference `approved_by.username` even when `approved_by` is None.
**Root cause:** Flash-message assertions against rendered HTML on redirect targets are brittle: they turn every rendering bug in every reachable template into a test failure for an unrelated regression guard.
**Rule:** Prefer `django.contrib.messages.get_messages(response.wsgi_request)` over `follow=True` + `assert b'...' in r.content`. The assertion becomes: `msgs = [str(m) for m in get_messages(r.wsgi_request)]; assert any('expected' in m for m in msgs)`. This verifies the exact behaviour (the view enqueued the message) without coupling the test to template rendering quality.
**Scope:** Retrofit the same pattern when writing new tests; existing green tests don't need backfill.

### Issue 27: `|default` does not short-circuit chained None-attribute lookups
**What happened:** Stocktaking templates rendered `{{ user_fk.get_full_name|default:user_fk.username|default:"—" }}`. When `user_fk` was None, the **default-arg** `user_fk.username` still had to resolve — Django's filter evaluates its argument before the filter runs — and raised `VariableDoesNotExist: Failed lookup for key [username] in None`. The surrounding `|default:"—"` never got a chance to fire. Four templates had this pattern; all four crashed whenever the FK was null.
**Root cause:** Conflating "the primary expression is falsy" with "the primary expression's base is None". `|default` only handles the first. Chained `|default` with an argument that itself requires attribute traversal is a trap.
**Rule:** When a user (or any nullable FK) may be None in a template, wrap the whole expression in `{% if fk %}...{% else %}—{% endif %}` instead of chaining `|default`. Reference fix: [templates/stocktaking/count_detail.html](../../templates/stocktaking/count_detail.html) — `{% if count.assigned_to %}{{ count.assigned_to.get_full_name|default:count.assigned_to.username }}{% else %}—{% endif %}`.
**How to apply:** Grep project-wide for `\.get_full_name\|default:.*\.username` and any `fk\.[a-z_]+\|default:fk\.` patterns; convert to `{% if %}`-wrapped blocks.
**Scope sweep target:** `orders`, `purchase_orders`, `receiving`, `inventory`, `stock_movements`, `lot_tracking`, `returns`, `warehousing`, `vendors` — any detail template that renders a user FK for a "created_by / approved_by / assigned_to" field is a candidate.

### Issue 28: Direct `on_hand` mutation bypasses the canonical ledger write path
**What happened:** `stocktaking/adjustment_post_view` created a `StockAdjustment` row with `adjustment_type='increase'|'decrease'` and `quantity=abs(variance)`, then separately ran `stock.on_hand = item.counted_qty; stock.save()`. The `StockAdjustment.apply_adjustment()` method was **never called**. Net effect: two code paths touched `on_hand` — the ledger row (via its `apply_adjustment`) and the view (manually). Under concurrent writes the two could diverge, and the ledger's `(adjustment_type, quantity)` could not be replayed to reconstruct the exact `on_hand` transition.
**Root cause:** The view was written for "snapshot at count time is authoritative" semantics (set on_hand to the counted value) but created ledger rows labelled with delta semantics ("increase by N"). The two stories disagreed.
**Rule:** Every module that writes to `inventory.StockLevel.on_hand` MUST either (a) call `StockAdjustment.apply_adjustment()` as the canonical write, or (b) document why direct mutation is safe for that specific flow. For variance-posting flows the right pattern is `StockAdjustment(adjustment_type='correction', quantity=<final_value>).apply_adjustment()` — the ledger row's `quantity` equals the resulting `on_hand`, so the two are arithmetically reconcilable by definition.
**How to apply:** When reviewing any `on_hand = ...` assignment in a view, ask: "Is there a matching `StockAdjustment` row emitted? Does its `(type, qty)` reproduce this assignment?" If the ledger row says `increase by 3` but the view sets `on_hand = 12`, the reader has to do arithmetic. Correction-type with `quantity=final` eliminates the mental load.
**Scope sweep target:** `grep -rn "on_hand = " -- */views.py` — every hit is a candidate for this review. Known call sites: `stocktaking/views.py::adjustment_post_view` (fixed), `returns/views.py` disposition processing (already uses StockAdjustment helper), `stock_movements` receive flow (uses `apply_adjustment`).

### Issue 29: `@login_required` alone is not RBAC
**What happened:** All 25 stocktaking views were protected by `@login_required` but nothing else. A non-admin tenant user — a rank-and-file counter, say — could POST to `/stocktaking/adjustments/<pk>/approve/` or `/stocktaking/adjustments/<pk>/post/` and single-handedly alter inventory valuations. `@login_required` confirms "this is a tenant user", not "this user should be approving anything".
**Root cause:** Module built with login gate only; the `@tenant_admin_required` decorator exists in `core.decorators` but was not adopted. Easy to miss because the SQA review's OWASP-A01 checklist ticks "login_required present" without asking whether non-admin-tenant users should also be blocked.
**Rule:** Every destructive view (create, edit, delete) and every state-change view (approve, reject, post, release, run, start, cancel, review) MUST carry `@tenant_admin_required` in addition to `@login_required`. Reads (list, detail, sheet for a counter) stay open to any authenticated tenant user. Same pattern as `lot_tracking/views.py`.
**How to apply:** When auditing a module, grep for `^@login_required\ndef (.*(?:create|edit|delete|approve|reject|post|release|run|start|cancel|review|transition|submit))` — every match without a trailing `@tenant_admin_required` is a gap. For each gap, add a non-admin `test_non_admin_blocked_from_<action>` regression test.
**Scope sweep target:** audit every module's `views.py` for `@login_required` on destructive verbs without the admin gate. Known to be done: `lot_tracking`, `returns`, `stocktaking`. Candidates for audit: `orders`, `purchase_orders`, `receiving`, `inventory`, `stock_movements`, `warehousing`, `catalog`, `vendors`, `administration`, `multi_location`, `forecasting`.

## 2026-04-18 — Returns Module SQA, Follow-up Pass (deferred items)

### Issue 27: "Assert substring not in content" fails for flash-message carry-over
**What happened:** When writing the D-15 soft-delete regression test, the natural assertion was "the soft-deleted RMA number should NOT appear in the list page HTML". It failed — not because the filter was broken, but because the flash-message framework rendered "RMA 'RMA-00001' deleted." on the list page after the POST → GET redirect. The substring `b'RMA-00001'` was in the response content, just not in the table body.
**Root cause:** Same family as lesson #26 but the inverse direction: a success message from an action's flash-queue produces noise in HTML-content assertions for the *next* request.
**Rule:** For list-page "record is hidden" assertions, prefer the paginator count: `assert resp.context['<object_name>'].paginator.count == 0`. This checks the queryset result directly, not HTML substrings. Keep HTML substring assertions for "the label was rendered"-style positive checks where you control the full surface. Paired with lesson #26's `get_messages` rule, the test suite stops depending on HTML rendering for either positive or negative assertions.
**How to apply:** In any test that currently does `assert b'<identifier>' not in resp.content` against a list page, convert to `resp.context['<object_name>'].paginator.count == 0`. Similarly for detail-page negative assertions, use `resp.status_code == 404`.

### Issue 28: Promote a helper to `core/` **before** the third module copies it
**What happened:** While closing D-25 on returns, the `can_transition_to(new_status)` method was sitting byte-identical in 5 modules (vendors, orders, receiving, lot_tracking, returns) and had been for weeks. Lesson #14 already documents the "promote on third repeat" rule, but no one had performed the promotion because state-machine helpers weren't yet a flagged defect — just code duplication. The returns review finally called it out (D-25), the helper moved to `core/state_machine.py`, and the migration cost was trivial (6 lines + one mixin-reference change per model). **But** — this should have happened three modules ago, not five.
**Root cause:** The "third module" rule in lesson #14 requires active policing. When nobody flags the duplication, nothing drives the extraction. The helpers that were promoted in earlier cycles (`tenant_admin_required`, `emit_audit`, `TenantUniqueCodeMixin`) were all driven by a *defect* catching someone's eye — not by proactive duplication detection.
**Rule (structural):** Each SQA review MUST, as its first discovery step, check `grep -l "can_transition_to\|TenantUniqueCodeMixin\|tenant_admin_required\|emit_audit" */models.py */forms.py */views.py`. If the target module re-declares any of these helpers locally, the review defect list MUST include "promote helper usage to `core/`" as at least a Medium defect — *before* the module adds any further local copies. This turns the "third repeat" rule into a 5-second grep that runs automatically every SQA pass.
**Scope sweep outcome:** After returns' D-25, remaining modules still defining their own `can_transition_to`: `vendors`, `orders`, `receiving`, `lot_tracking`, `stocktaking` (if present), `stock_movements`. Each can migrate in ~20 lines. Schedule for next cross-module pass.

### Issue 29: Soft-delete filter discipline is a per-query concern, not a manager concern
**What happened:** For D-15 I considered two implementations: (a) a custom `active()` manager that filters out `deleted_at__isnull=False` by default, (b) explicit `.filter(deleted_at__isnull=True)` at every call site. Option (a) looked cleaner but had hidden costs — Django admin uses `_default_manager`, so admin would silently hide soft-deleted records (contradicting D-23 audit-visibility intent); cascade deletes and FK reverse accessors bypass the default manager in subtle ways; it's harder for a reviewer to spot a query that should have included deleted records. Option (b) chosen: add `deleted_at__isnull=True` at every `get_object_or_404` and every list queryset. 22 call sites, simple `replace_all` per model, every reviewer can see the gate.
**Root cause:** "Smart" default managers look ergonomic until you need to bypass them for audit/admin, then they become load-bearing magic.
**Rule:** When implementing soft-delete, use **explicit filtering at the call site**, not a custom default manager. The extra keyword argument in `filter()` / `get_object_or_404()` is a readable marker that documents the soft-delete contract. If call sites become burdensome (e.g., >50 queries), introduce a `.alive()` queryset method (not a manager override) that stays opt-in.
**Trade-off accepted:** Every new view that queries these models has to remember `deleted_at__isnull=True`. A grep-level lint can catch omissions: `grep -rn "<ModelName>\.objects\." <module>/ | grep -v "deleted_at"` should return near-zero matches (admin is the intended exception).


## 2026-04-19 — Multi-Location Management SQA Remediation

### Issue 30: Raw GET filter params into `.filter(..._id=value)` fail on TWO axes — not just non-numeric strings
**What happened:** Multi-location's D-01 fix initially caught `ValueError` from non-numeric input (`?parent=abc`) via `int(value)` in a try/except. But the pytest sweep that supplied `?parent=9999999999999999999999999` — a valid int — still 500'd with `OverflowError: Python int too large to convert to SQLite INTEGER`. The SQLite / MySQL / Postgres backends all expose signed BIGINT as the ceiling for PK columns, so any int > `2**63 - 1` overflows at the cursor layer even after `int()` succeeds.
**Root cause:** Two failure modes share the same surface: non-numeric strings raise in Python; over-sized numeric strings raise in the DB driver. Catching only `ValueError` fixes the first and silently re-exposes the second. Tests that parametrise over `abc, ../etc/passwd, 1' OR '1'='1` pass; add a 23-digit string and the production crash comes back.
**Rule:** Any helper that coerces a GET / URL segment into a DB PK filter MUST bound the result on BOTH sides:
```python
_MAX_DB_INT = 2**63 - 1          # signed BIGINT upper bound
def _int_or_none(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 0 or n > _MAX_DB_INT:
        return None
    return n
```
**How to apply:** Test parametrisation for input-validation suites MUST include at least one value > `2**63` (e.g. a 25-digit string of 9s) in addition to non-numeric noise. The pattern holds for every list view across every tenant-scoped module. Reference fix: [multi_location/views.py:28-48](../../multi_location/views.py#L28-L48).
**Scope sweep target:** `grep -rn "\.filter.*_id=.*GET\.get" */views.py` across the repo. Every hit that pipes raw GET straight into `.filter(..._id=)` is a dual-mode crash candidate. Ship a shared `core.request.int_param_or_none(request, key)` helper the next time this bug lands in a second module.

### Issue 31: Auto-generated unique codes must scan by regex, not by `-id` ordering
**What happened:** `Location._generate_code()` picked "next number" by taking `Location.objects.filter(tenant=t).order_by('-id').values_list('code', flat=True).first()` and stripping `LOC-`. The very last row's code was used as the anchor. That assumes every row's code follows the `LOC-NNNNN` pattern. In practice users import existing data with prefixes like `STORE-01` / `WH-TOR-02`; the latest-insert-by-id is then a non-LOC code, the regex strip fails silently → num resets to 1 → `LOC-00001` already exists → `IntegrityError` on the very next `create()`. Reproduced in the SQA review shell against an empty tenant in four `create()` calls.
**Root cause:** "Last row's code tells me the next code" works only if every row agrees to one prefix scheme. In a multi-tenant SaaS with mixed imported data, that invariant is violated by minute-one of operations.
**Rule:** Auto-number generators MUST match the intended pattern with a regex and take `max()` of the extracted numeric tail. Never rely on `-id` ordering as a proxy for "highest code in scheme X".
```python
def _generate_code(self):
    max_num = 0
    for code in Model.objects.filter(tenant=self.tenant, code__regex=r'^LOC-\d+$').values_list('code', flat=True):
        m = re.match(r'^LOC-(\d+)$', code)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f'LOC-{max_num + 1:05d}'
```
**How to apply:** Audit every `_generate_<X>` / `_next_<X>_number` method in the repo for the same trap. Specifically look for `.order_by('-id')` + `.first()` as the anchor; replace with the regex-and-max pattern above. Reference fix: [multi_location/models.py:100-118](../../multi_location/models.py#L100-L118).
**Scope:** `purchase_orders`, `orders`, `receiving`, `returns`, `lot_tracking`, `stocktaking` all ship `_generate_<X>_number()` methods — review each for the same `-id`-anchored scan.

### Issue 32: Self-referential FK hierarchies need BOTH a form-layer descendant exclude AND a model-layer cycle guard
**What happened:** `LocationForm.__init__` correctly excluded `self.instance.get_descendant_ids(include_self=True)` from the parent queryset, so the admin UI refuses A→B→A style cycles. But the SQA review's shell repro bypassed the form with `a.parent = b; a.save()` and then `b.parent = a; b.save()` — a direct-ORM path that admin users can exercise via the Django admin console, raw SQL, or a seed script. The next call to `get_descendant_ids()` looped forever (infinite BFS), and `full_path` rendered `A > B > A > B > A > B > A > B > A > B > A` because its guard only capped the chain at 10 — it didn't detect the repeat.
**Root cause:** Defence-in-depth was skipped. The review treated the form-layer exclude as sufficient because "who would save a cycle?" The answer: anyone with a management shell, any seed script that reparents, any future importer.
**Rule:** Any self-referential FK model must carry:
1. A form-layer descendant exclude that prevents cycles through the UI.
2. A `clean()` guard on the model that raises `ValidationError` if a cycle is detected before `save()`.
3. Every graph-walk method (`full_path`, `get_descendant_ids`, etc.) MUST carry a `visited = set()` guard. Walks must terminate even if a cycle escaped to the DB.
**How to apply:** Grep for `on_delete=models.SET_NULL.*to='self'` (or `self`) across `*/models.py`. Each match is a candidate for the three-guard pattern. Reference fix: [multi_location/models.py:63-109](../../multi_location/models.py#L63-L109).
**Scope:** `catalog.Category` has a self-FK (parent category) — audit for the same pattern if not already done. `administration`, `forecasting` — not known to have self-FKs but worth a grep.

### Issue 33: `unique_together` trap hits its SIXTH module — helper needs a composite-key variant
**What happened:** Multi-location has two composite unique tuples — `LocationTransferRule(tenant, source_location, destination_location)` and `LocationSafetyStockRule(tenant, location, product)`. The form layer had no explicit `clean()` guard, so duplicate submissions escaped to the DB as `IntegrityError` → 500. Same family as lessons #6/#7/#11/#14/#18 but the existing `core.forms.TenantUniqueCodeMixin` only handles the single-field `(tenant, code)` case — it does not generalise to composite tuples.
**Root cause:** The helper was generalised once (from `code` to any `tenant_unique_field`) but still encodes the *single-field* assumption. Composite tuples are structurally a different shape and keep getting hand-rolled.
**Rule:** When a form needs to guard `unique_together(tenant, A, B[, C, …])`, write the check explicitly in `clean()`:
```python
if all(cleaned.get(f) is not None for f in unique_fields) and self.tenant is not None:
    qs = Model.objects.filter(tenant=self.tenant, **{f: cleaned[f] for f in unique_fields})
    if self.instance.pk is not None:
        qs = qs.exclude(pk=self.instance.pk)
    if qs.exists():
        raise ValidationError('A record with these fields already exists.')
```
**Structural fix queued:** When the NEXT module shows this pattern, promote a `TenantUniqueCompositeMixin(unique_fields=(...))` to `core/forms.py` alongside the existing mixin. Today's multi-location is #6; one more triggers the extraction.
**How to apply:** `grep -n "unique_together" */models.py` and for every tuple with more than two fields, confirm the corresponding `ModelForm.clean()` has the explicit composite guard above. Reference fix: [multi_location/forms.py:172-195](../../multi_location/forms.py#L172-L195) + [:237-248](../../multi_location/forms.py#L237-L248).
**Scope outstanding:** `administration`, `inventory` (re-audit post-fixes), `forecasting` — still unreviewed for this lesson. Cleared with this pass: `catalog`, `vendors`, `purchase_orders`, `receiving`, `warehousing`, `lot_tracking`, `stock_movements`, `orders`, `returns`, `stocktaking`, `multi_location`.

### Issue 34: `tenant=None` form path is an access-control hole, not an error path
**What happened:** `LocationForm(data=..., tenant=None)` — the exact call a superuser's view would make if `request.tenant is None` (per `core.middleware.TenantMiddleware`) — left every FK queryset unfiltered. The `parent`/`warehouse` fields accepted PKs from **any** tenant as "valid choices". The save then crashed on the not-null `tenant` FK, so no data landed — but `form.is_valid() == True` on cross-tenant input is itself a wrong answer, and any future form with a nullable tenant could ship the corruption.
**Root cause:** The original `if tenant:` gate meant "only filter if we have a tenant"; it should mean "refuse to expose any choice if we don't".
**Rule:** In every `ModelForm` that accepts `tenant=None`:
```python
if tenant is None:
    # Superuser path — offer NO choices; any selection is an access-control breach.
    self.fields['<fk>'].queryset = Model.objects.none()
else:
    self.fields['<fk>'].queryset = Model.objects.filter(tenant=tenant, ...)
```
The `.none()` branch makes `form.is_valid()` → `False` for any non-empty FK input, which is the correct answer for "a form handed a tenant-less request".
**How to apply:** Grep `grep -rn "tenant=None" */forms.py` across the repo. For each form that accepts `tenant` in `__init__`, verify every FK queryset is `.none()`-gated in the None branch. Reference fix: [multi_location/forms.py:51-70](../../multi_location/forms.py#L51-L70).


## 2026-04-19 — Forecasting SQA Remediation

### Issue 35: Side-effect-on-GET views are a silent CSRF bypass — audit every single-action endpoint
**What happened:** Forecasting SQA review (D-05) caught **four** mutating views (`rop_check_alerts`, `alert_mark_ordered`, `alert_close`, `safety_stock_recalc`) that perform state changes on GET. Templates correctly POST to them, but CSRF protection does not cover GETs — a logged-in user loading a crafted `<img src>` or clicking an attacker-supplied link would silently trigger the scan/close/recalc. The views looked "fine" in review because they were short (5-10 lines) and had no `if request.method == 'POST'` gate to forget; the bug lives in the *absence* of a gate.
**Root cause:** When a view has a single mutating action, the natural shape is "just do the thing and redirect" — the `if POST` check feels like ceremony for a 3-line body. The habit is reinforced by the CRUD-completeness pattern, which focuses on `list/create/detail/edit/delete` and implicitly assumes multi-step mutations (create/edit) need the POST check but single-action endpoints (close, scan, recalc, mark-as-X) don't. They do.
**Rule:** Every mutating view **must** be gated by `@require_POST` OR explicit `if request.method != 'POST': return HttpResponseNotAllowed(['POST'])`. No exceptions for "small" or "simple" mutations. If the view is single-action and doesn't render a form, `@require_POST` from `django.views.decorators.http` is the one-liner to reach for, stacked below `@tenant_admin_required`.
**How to apply:** At review time, grep `grep -n "def .*_view" <module>/views.py` → for every view that mutates state (look for `.save()`, `.delete()`, `.create()`, `F(...)`, `qs.update(...)`), confirm a `@require_POST` or method gate exists. For single-action endpoints (suffix `_close`, `_recalc`, `_scan`, `_mark_*`, `_check_*`, `_approve`, etc.) treat the absence of `@require_POST` as a High defect, not a style nit.
**Scope outstanding:** Grep `grep -rn "^def .*_view" */views.py | grep -v "list\|detail\|create\|edit"` → every hit that isn't `@require_POST`-gated in the source is a candidate. Prioritise ROP-scan-style batch mutators (visible, one-click effect) and status-transition endpoints (hidden side effects).

### Issue 36: Template chained attribute access on nullable FKs needs `{% if %}`, not `|default`
**What happened:** `profile_detail.html` had `{{ profile.created_by.get_full_name|default:profile.created_by.username|default:"—" }}`. When `created_by` was `None` (tenant fixture didn't set it — common path for superuser-created or imported rows), Django's `default` filter does NOT short-circuit the intermediate lookup. Template resolution evaluates the second argument (`profile.created_by.username`) eagerly, which raises `VariableDoesNotExist: Failed lookup for key [username] in None`. Result: 500 on what looked like a defensive template.
**Root cause:** `|default:"x"` only guards the final rendered value, not every lookup in the dotted chain. Django templates resolve each segment lazily and throw before the filter runs on a `None`-intermediate. The pattern works for single-segment `{{ foo|default:"—" }}` but is brittle once you chain `{{ foo.bar.baz|default:... }}` — and doubly brittle when a filter argument *also* traverses a nullable chain.
**Rule:** For nullable FK fields in templates, wrap the access in `{% if obj.field %}{{ obj.field.nested }}{% else %}—{% endif %}`, not `{{ obj.field.nested|default:"—" }}`. Reserve `|default` for single-level lookups and already-resolved strings. Applies especially to audit fields (`created_by`, `updated_by`, `deleted_by`, `acknowledged_by`, etc.) which are often `SET_NULL` and therefore nullable by contract.
**How to apply:** Grep `grep -rn "\.created_by\.\|\.updated_by\.\|\.deleted_by\.\|\.acknowledged_by\." templates/` — every hit not wrapped in `{% if %}` is a latent 500 waiting for the first None-valued row (seed data, imports, shell-created records). Reference fix: [templates/forecasting/profile_detail.html:37](../../templates/forecasting/profile_detail.html#L37).

