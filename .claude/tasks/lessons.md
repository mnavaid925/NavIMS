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
