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
**Scope still outstanding after this pass:** `administration`, `purchase_orders`, `receiving`, `warehousing`, `inventory`, `stock_movements`, `lot_tracking`, `orders`, `returns`, `stocktaking`, `multi_location`, `forecasting` — still need the same audit. `catalog` and `vendors` are now clear.

### Issue 8: OWASP-A08 file-upload pattern repeats across modules
**What happened:** `VendorContract.document = FileField(upload_to='…')` accepted arbitrary file types (`.exe`, `.svg`, `.php`, polyglots) with no size cap. This is the A08 failure mode captured in every SQA skill run, but the project has no shared `validate_contract_document` / `validate_safe_upload` utility, so every new module reinvents (or forgets) the guard.
**Root cause:** No shared upload-safety helper. Each module's form has to hand-roll extension whitelist + size cap + MIME check.
**Rule:** Before building any future module with `FileField`, extract the pattern in `vendors/forms.py:clean_document` into `core/validators.py:SafeFileUploadValidator(allowed_extensions, max_size, blocked_content_types)` and reuse it. Until that utility exists, every `FileField` added to a model must be reviewed for (a) extension whitelist, (b) explicit size cap ≤ 10 MB, (c) SVG / executable content-type block, (d) authenticated-only download.
