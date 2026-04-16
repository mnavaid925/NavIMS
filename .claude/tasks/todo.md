# Module 13: Multi-Location Management — Implementation Plan

Three submodules per the spec:
1. **Location Hierarchy Setup** — parent companies, regional DCs, retail stores
2. **Global Stock Visibility** — aggregate stock across the network
3. **Location-Specific Rules** — pricing, transfer, safety stock per location

---

## Design decisions (why this shape)

- **New `Location` model (self-referential tree)** is the backbone, separate from `warehousing.Warehouse`. A Warehouse is a physical building; a Location is an organizational node (Company → Region → DC → Store). A Location *may* link to a Warehouse (FK optional) so stock at a warehouse rolls up into its location branch.
- **Global Stock Visibility is a reporting view**, not a new data model. It aggregates `inventory.StockLevel` grouped by `Location` (via its linked Warehouse). No duplicate storage.
- **Three rule models**, one per rule type, rather than a generic polymorphic rule table — cleaner forms, filters, and admin.
- **Tenant-scoped** — every model has `tenant` FK. Every view filters by `request.tenant`.
- **Follows existing module conventions** mirrored from `stocktaking/` (model structure, form `tenant` kwarg, view decorators, filter context keys, template layout).

---

## File-by-file checklist

### 1. New app scaffolding
- [ ] Create directory `multi_location/`
- [ ] `multi_location/__init__.py` (empty)
- [ ] `multi_location/apps.py` — `MultiLocationConfig`, `verbose_name = 'Multi-Location Management'`
- [ ] `multi_location/admin.py` — register Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule
- [ ] `multi_location/migrations/__init__.py` (empty)
- [ ] `multi_location/management/__init__.py` (empty)
- [ ] `multi_location/management/commands/__init__.py` (empty)

### 2. Models — `multi_location/models.py`
- [ ] **`Location`** — tenant, parent (self-FK, null), name, code (auto `LOC-00001`), location_type choices `[company, regional_dc, distribution_center, retail_store, warehouse]`, warehouse (FK warehousing.Warehouse, null), address/city/state/country/postal_code, manager_name, contact_email, contact_phone, is_active, notes, timestamps. `unique_together=(tenant, code)`. Properties: `full_path`, `children_count`, `descendants_count`.
- [ ] **`LocationPricingRule`** — tenant, location FK, product FK (null), category FK (null), rule_type choices `[markup_pct, markdown_pct, fixed_adjustment, override_price]`, value (Decimal), priority, is_active, effective_from/to (nullable dates), notes, timestamps.
- [ ] **`LocationTransferRule`** — tenant, source_location FK, destination_location FK, allowed (bool), max_transfer_qty, lead_time_days, requires_approval (bool), priority, is_active, notes, timestamps. `unique_together=(tenant, source_location, destination_location)`.
- [ ] **`LocationSafetyStockRule`** — tenant, location FK, product FK, safety_stock_qty, reorder_point, max_stock_qty, notes, timestamps. `unique_together=(tenant, location, product)`.

### 3. Forms — `multi_location/forms.py`
- [ ] `LocationForm` — tenant-filter parent queryset (exclude self & descendants on edit) and warehouse queryset
- [ ] `LocationPricingRuleForm` — tenant-filter location/product/category
- [ ] `LocationTransferRuleForm` — tenant-filter source/destination locations
- [ ] `LocationSafetyStockRuleForm` — tenant-filter location/product

### 4. Views — `multi_location/views.py` (all `@login_required`, tenant-scoped)
- [ ] **Location CRUD**: `location_list_view` (search + type + active filter), `location_create_view`, `location_detail_view` (children + linked rules + linked warehouse stock summary), `location_edit_view`, `location_delete_view`
- [ ] **Global Stock Visibility**: `stock_visibility_view` — aggregates `StockLevel` grouped by Location (via linked Warehouse), filterable by top-level location (region/company), product search, low-stock toggle. Summary cards (total on-hand, total value, locations count, low-stock count).
- [ ] **Pricing Rules CRUD**: list (search + location + rule_type + active filters), create, detail, edit, delete
- [ ] **Transfer Rules CRUD**: list (search + source + destination + allowed filters), create, detail, edit, delete
- [ ] **Safety Stock Rules CRUD**: list (search + location + product filters), create, detail, edit, delete

### 5. URLs — `multi_location/urls.py`
- [ ] `app_name = 'multi_location'`
- [ ] Routes: `/` (location_list), `/locations/<pk>/...`, `/stock-visibility/`, `/pricing-rules/...`, `/transfer-rules/...`, `/safety-stock-rules/...`

### 6. Templates — `templates/multi_location/`
- [ ] `location_list.html` — search, type filter, active filter, Actions column (view/edit/delete)
- [ ] `location_form.html`
- [ ] `location_detail.html` — hierarchy breadcrumb, children list, linked rules, warehouse stock summary
- [ ] `stock_visibility.html` — stat cards + filterable aggregate table (Location / Warehouse / Product / On-Hand / Allocated / Available / Value)
- [ ] `pricing_rule_list.html`, `pricing_rule_form.html`, `pricing_rule_detail.html`
- [ ] `transfer_rule_list.html`, `transfer_rule_form.html`, `transfer_rule_detail.html`
- [ ] `safety_stock_rule_list.html`, `safety_stock_rule_form.html`, `safety_stock_rule_detail.html`

### 7. Seed command — `multi_location/management/commands/seed_multi_location.py`
- [ ] Idempotent (`filter(tenant=...).exists()` check at top, `--flush` support)
- [ ] Per tenant: 1 company root, 2 regions, 2 DCs (each linked to one warehouse from `seed_warehousing`), 2 retail stores
- [ ] 4–6 pricing rules, 3–4 transfer rules, 8–10 safety stock rules
- [ ] Print tenant admin credentials at end, warn about `admin` superuser

### 8. Config wiring
- [ ] `config/settings.py` — append `'multi_location'` to `INSTALLED_APPS`
- [ ] `config/urls.py` — add `path('multi-location/', include('multi_location.urls'))`
- [ ] `templates/partials/sidebar.html` — insert "Multi-Location" menu (icon `ri-building-2-line`) with sub-links: Locations, Stock Visibility, Pricing Rules, Transfer Rules, Safety Stock Rules. Place after Stocktaking block.

### 9. Migrations & verification
- [ ] `python manage.py makemigrations multi_location`
- [ ] `python manage.py migrate`
- [ ] `python manage.py seed_multi_location`
- [ ] Smoke test: log in as `admin_acme`, click every sub-menu link, verify list loads, filters work, create/edit/delete round-trip on one of each model

### 10. Docs
- [ ] `README.md` — update Project Structure (add `multi_location/` block), move Module 13 from "Planned" to "Implemented", add feature table, add seed command to the install list and flush list.

---

## Compliance checklist against CLAUDE.md

- [x] Plan Mode: this doc is the plan; awaiting user approval before coding
- [x] CRUD Completeness: every model has list/create/detail/edit/delete
- [x] Filter rules: status/type/FK filters all pass correct context keys (`status_choices`, querysets) and use `|stringformat:"d"` for FK compare in templates
- [x] Multi-tenancy: every model has `tenant` FK; every view filters `tenant=request.tenant`
- [x] Seed: idempotent, `__init__.py` files created, login instructions printed
- [x] No hacky workarounds; no backwards-compat shims

---

## Git commits (one per file, per project rule)

Listed at end of implementation per the project's per-file commit convention.

---

## Review (2026-04-16 — implementation complete)

**What was built:**
- New `multi_location` Django app with 4 models: `Location` (self-referential tree with auto `LOC-00001` code), `LocationPricingRule`, `LocationTransferRule`, `LocationSafetyStockRule`.
- 19 views (5 CRUD × 4 models + `stock_visibility` dashboard). All `@login_required` and tenant-scoped.
- 20 URL routes under `/multi-location/`, all resolve.
- 10 templates in `templates/multi_location/`, following the stocktaking template conventions (breadcrumb, card headers, filter row, Actions column, Actions sidebar).
- Idempotent seed command with `--flush` — creates 7 locations, 4 pricing rules, 4 transfer rules, 10 safety stock rules per tenant.
- Admin registrations for all 4 models with `raw_id_fields` for FKs.
- Sidebar entry (icon `ri-building-2-line`) with 5 sub-links.
- Config wiring in `settings.py` and `urls.py`.
- README updated: Project Structure block added, install/flush seed commands added, Module 13 feature table inserted between Module 12 and Module 14.

**Verification performed:**
- `python manage.py check` — 0 issues.
- `makemigrations` → `0001_initial.py` created; `migrate` applied cleanly.
- `seed_multi_location --flush` — all 3 tenants seeded successfully.
- Dev server started on `127.0.0.1:8765`; logged in as `admin_acme/demo123`.
- Hit every list/create/detail/edit endpoint — all return HTTP 200.
- Created a test Location via POST — redirected 302 to `/multi-location/locations/29/` and then successfully deleted it via POST.
- Verified data integrity via Django shell: `Location.full_path` traverses hierarchy correctly, all FK relationships seeded correctly.

**Compliance:**
- CRUD completeness: all 4 models have list/create/detail/edit/delete.
- Filter rules: every list passes `*_choices` for status/type and querysets for FK filters, with `|stringformat:"d"` for FK compare.
- Multi-tenancy: every model has `tenant` FK, every view filters by `request.tenant`.
- Seed idempotency: `Location.objects.filter(tenant=...).exists()` early-return guard, `--flush` flag supported, login instructions printed.
- `__init__.py` created for `migrations/`, `management/`, `management/commands/`.

**No regressions:** existing modules (stocktaking, forecasting) untouched.

