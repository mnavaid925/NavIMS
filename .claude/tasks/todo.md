# Module 15 — Barcode & RFID Integration (Plan)

**Status:** DRAFT — pending user approval

Date started: 2026-04-19
App label: `barcode_rfid`
Numbering: README lists this as Planned Module #15 (Forecasting is #14, already implemented). User's prompt numbered it "14" — clarified to 15.

---

## Scope

Four submodules from user spec:

| # | Submodule | Purpose |
|---|-----------|---------|
| 1 | Label Generation | Design + print barcode/QR labels for products, bins, pallets, lots, serials |
| 2 | Mobile/Handheld Scanner Integration | Register warehouse scan devices + log scan events |
| 3 | RFID Tag Management | Register RFID tags, readers, and read events (passive/active, UHF/HF/LF) |
| 4 | Batch Scanning | Session-based multi-item scan capture for receiving / counting / transfer |

---

## Data Model (9 models)

### 1. Label Generation
- **LabelTemplate** — `tenant`, `name`, `code` (unique(tenant, code) → uses `core.forms.TenantUniqueCodeMixin`), `label_type` in {barcode, qr, mixed}, `symbology` in {CODE128, CODE39, EAN13, EAN8, UPC_A, QR, DATA_MATRIX, PDF417}, `paper_size`, `width_mm`, `height_mm`, `includes_name`, `includes_price`, `includes_sku`, `includes_date`, `copies_per_label`, `is_active`, timestamps.
- **LabelPrintJob** — `tenant`, `job_number` (auto `LPJ-NNNNN`, `_save_with_number_retry`), `template` FK, `target_type` in {product, bin, pallet, lot, serial}, `target_id`, `target_display` (denorm string), `quantity`, `status` in {draft, queued, printing, printed, failed, cancelled}, `printed_by` FK User, `printed_at`, `notes`, `created_by`, timestamps.
  - State machine: `draft → queued → printing → printed` / `queued → cancelled` / `printing → failed` / `failed → queued` (retry).
  - Uses `core.state_machine.StateMachineMixin`.

### 2. Mobile/Handheld Scanner Integration
- **ScannerDevice** — `tenant`, `device_code` (unique(tenant, device_code) → `TenantUniqueCodeMixin`), `name`, `device_type` in {handheld, fixed, mobile_phone, tablet, wearable}, `manufacturer`, `model_number`, `os_version`, `assigned_to` FK User (nullable), `assigned_warehouse` FK `warehousing.Warehouse` (nullable), `status` in {active, inactive, maintenance, lost, retired}, `last_seen_at`, `battery_level_percent`, `firmware_version`, `is_active`, timestamps.
- **ScanEvent** — `tenant`, `device` FK (nullable — manual entry allowed), `user` FK User, `scan_type` in {receive, putaway, pick, pack, ship, count, transfer, lookup, other}, `barcode_value`, `symbology`, `resolved_object_type` in {product, lot, serial, bin, none}, `resolved_object_id` (nullable), `warehouse` FK (nullable), `scanned_at`, `status` in {success, unmatched, error}, `error_message`, `ip_address`.
  - Ledger-only (no state transitions). Lists / detail / filter views.

### 3. RFID Tag Management
- **RFIDTag** — `tenant`, `epc_code` (unique(tenant, epc_code) → `TenantUniqueCodeMixin`), `tag_type` in {passive, active, semi_active}, `frequency_band` in {LF, HF, UHF, Microwave}, `linked_object_type` in {product, lot, serial, bin, pallet, none}, `linked_object_id` (nullable), `linked_display` (denorm), `status` in {unassigned, active, inactive, lost, damaged, retired}, `first_read_at`, `last_read_at`, `read_count`, `battery_voltage` (active only), `notes`, timestamps.
  - State machine: `unassigned → active → inactive` / `active → lost|damaged|retired` / `inactive → active`.
- **RFIDReader** — `tenant`, `reader_code` (unique(tenant, reader_code) → `TenantUniqueCodeMixin`), `name`, `reader_type` in {fixed_gate, handheld, integrated, vehicle_mount}, `warehouse` FK, `zone` FK `warehousing.Zone` (nullable), `ip_address`, `antenna_count`, `frequency_band`, `status` in {online, offline, maintenance, retired}, `last_seen_at`, `firmware_version`, `is_active`, timestamps.
  - Form-layer zone-vs-warehouse cross-validation (stocktaking-style) — zone must belong to the selected warehouse.
- **RFIDReadEvent** — `tenant`, `tag` FK RFIDTag, `reader` FK RFIDReader, `read_at`, `signal_strength_dbm`, `read_count_at_event`, `direction` in {in, out, unknown}, `antenna_number`.
  - Ledger-only. List + detail views.

### 4. Batch Scanning
- **BatchScanSession** — `tenant`, `session_number` (auto `BSS-NNNNN`, `_save_with_number_retry`), `purpose` in {receiving, counting, picking, putaway, transfer, audit, other}, `device` FK ScannerDevice (nullable), `user` FK User, `warehouse` FK, `zone` FK `warehousing.Zone` (nullable), `started_at`, `completed_at`, `status` in {active, completed, cancelled}, `total_items_scanned` (denorm), `notes`, `created_by`, timestamps.
  - State machine: `active → completed` / `active → cancelled`.
- **BatchScanItem** — `session` FK, `tenant` (denorm for tenant scoping), `scanned_value`, `symbology`, `resolution_type` in {product, lot, serial, bin, rfid, unmatched}, `resolved_object_id` (nullable), `resolved_display` (denorm), `quantity` (default 1, `MinValueValidator(0.01)`), `scanned_at`, `is_resolved`, `error_message`.
  - Inline formset on session edit. Child form uses `__init__(tenant=...)` to filter FK queryset (closes lesson #9 inline-formset IDOR).

---

## File Plan

```
barcode_rfid/
├── __init__.py
├── apps.py                    # default_auto_field + label
├── models.py                  # 9 models above + _save_with_number_retry reuse
├── forms.py                   # 9 ModelForms + BatchScanItem inline formset form
│                              #   - TenantUniqueCodeMixin on template/device/tag/reader/session forms
│                              #   - zone-vs-warehouse cross-validation on RFIDReader + BatchScanSession
│                              #   - inline formset's child form accepts tenant in __init__
├── views.py                   # ~40 views — full CRUD + state transitions + scan logging endpoints
│                              #   - every destructive/transition view: @tenant_admin_required + @require_POST + emit_audit
│                              #   - lists pass status_choices + FK querysets for filters
│                              #   - get_object_or_404 always scoped to tenant
├── urls.py                    # URL routes grouped by submodule
├── admin.py                   # TenantScopedAdmin base for admin visibility
├── migrations/                # auto-generated
└── management/
    ├── __init__.py
    └── commands/
        ├── __init__.py
        └── seed_barcode_rfid.py   # idempotent demo data per tenant

templates/barcode_rfid/
├── label_template_list.html           label_template_form.html        label_template_detail.html
├── label_job_list.html                label_job_form.html             label_job_detail.html
├── device_list.html                   device_form.html                device_detail.html
├── scan_event_list.html               scan_event_detail.html
├── rfid_tag_list.html                 rfid_tag_form.html              rfid_tag_detail.html
├── rfid_reader_list.html              rfid_reader_form.html           rfid_reader_detail.html
├── rfid_read_list.html                rfid_read_detail.html
├── batch_session_list.html            batch_session_form.html         batch_session_detail.html
```

Sidebar entry: add a "Barcode & RFID" group in `templates/partials/sidebar.html` with 4 sub-items (Labels, Scanners, RFID, Batch Scanning).

---

## Lesson-informed Guardrails Baked In Upfront

Every item below is a direct codification of a prior lesson so the module ships clean the first time — no SQA remediation pass needed.

| Lesson | Applied as |
|--------|-----------|
| #6/#7/#11/#14/#18 — `unique_together(tenant, X)` trap | `core.forms.TenantUniqueCodeMixin` on all 5 user-visible unique fields (template.code, device.device_code, tag.epc_code, reader.reader_code). Auto-generated numbers (`LPJ-`, `BSS-`) use `_save_with_number_retry` per lesson #22. |
| #9 — inline-formset POST-path IDOR | BatchScanItem child form accepts `tenant` in `__init__`, filters every FK queryset there; view passes `form_kwargs={'tenant': tenant}` on GET AND POST. |
| #12/#20 — state transition triad | Every state-change view decorated: `@tenant_admin_required` + `@require_POST` + `emit_audit`; `can_transition_to` gated via `core.state_machine.StateMachineMixin`. |
| #13 — badge/choices drift | Template badge blocks always include `{% else %}{{ obj.get_field_display }}{% endif %}` fallback. |
| #16 — auto-progress state bypass | Any cascading state write checks `can_transition_to` before writing. |
| #22 — auto-generated number race | `LPJ-NNNNN`, `BSS-NNNNN` go through `_save_with_number_retry()`. |
| #23 — GET on state-change views = CSRF hole | Every state-transition view has `@require_POST`. |
| #24 — atomic multi-write | Scan session completion wrapped in `transaction.atomic()` if it touches counters + child rows. |
| #26/#27 — test flash-message brittleness | Tests (if included) use `get_messages(r.wsgi_request)` + `resp.context['<obj>'].paginator.count` instead of HTML substring asserts. |
| #27 (None-guard) — `\|default` with chained None attr | Detail templates render nullable FK users via `{% if fk %}…{% else %}—{% endif %}`, never chained `\|default:fk.username`. |
| #29 — `@login_required` alone is not RBAC | Every create/edit/delete/state-change view carries `@tenant_admin_required` in addition to `@login_required`. Reads stay open. |
| Filter Rules (CLAUDE.md) | Views pass `status_choices` + FK querysets to lists. Templates use `\|stringformat:"d"` for FK pk comparison. |
| CRUD Completeness (CLAUDE.md) | All 9 models get list + create + detail + edit + delete from day one. Exceptions: `ScanEvent` and `RFIDReadEvent` are ledger-only (no edit/delete in UI). |
| Seed Rules (CLAUDE.md) | `seed_barcode_rfid` is idempotent, prints tenant admin creds, skips if data exists, uses `get_or_create` / existence checks for unique-constrained rows. Both `__init__.py` files created. |
| Multi-Tenancy Rules | Every `Model.objects` query filtered by `tenant=request.tenant`; every model has `tenant` FK. |

---

## Build Steps (checkable)

### Phase 1 — Scaffolding
- [ ] Create `barcode_rfid/` app with `apps.py`, `__init__.py`, empty `models.py`/`forms.py`/`views.py`/`urls.py`/`admin.py`
- [ ] Register app in `config/settings.py` `INSTALLED_APPS`
- [ ] Register URL include in `config/urls.py`
- [ ] Create `barcode_rfid/management/__init__.py` and `barcode_rfid/management/commands/__init__.py`

### Phase 2 — Models & Migrations
- [ ] Implement 9 models with `tenant` FK, `StateMachineMixin` where applicable, `_save_with_number_retry` helpers
- [ ] `python manage.py makemigrations barcode_rfid`
- [ ] `python manage.py migrate`

### Phase 3 — Forms
- [ ] 9 ModelForms with `TenantUniqueCodeMixin` where applicable
- [ ] BatchScanItem inline formset child form accepting `tenant` in `__init__`
- [ ] Zone-vs-warehouse cross-validation on RFIDReader form + BatchScanSession form

### Phase 4 — Views + URLs
- [ ] Label Generation: 10 views (template CRUD-5, job CRUD-5 + state transitions queue/cancel/retry)
- [ ] Scanner: 6 views (device CRUD-5, scan_event list + detail)
- [ ] RFID: 13 views (tag CRUD-5 + state transitions, reader CRUD-5, read_event list + detail)
- [ ] Batch Scanning: 7 views (session CRUD-5 + item formset inline on edit + complete/cancel transitions)
- [ ] All views filter by `tenant=request.tenant`, lists pass choice/FK context, transitions use the 3-decorator triad

### Phase 5 — Templates
- [ ] 24 templates following existing NavIMS pattern (breadcrumbs + card + table + filter form + actions column)
- [ ] Sidebar nav entry under a "Barcode & RFID" group

### Phase 6 — Admin
- [ ] Register all 9 models with `TenantScopedAdmin` base (tenant admins see only their tenant)

### Phase 7 — Seed Command
- [ ] `seed_barcode_rfid.py` — idempotent, per-tenant demo rows: 3 label templates, 2 print jobs, 3 devices, 10 scan events, 8 RFID tags, 2 readers, 15 read events, 2 batch sessions with 5 items each
- [ ] Prints tenant admin login creds + superuser warning

### Phase 8 — Smoke test
- [ ] `python manage.py check`
- [ ] `python manage.py migrate`
- [ ] `python manage.py seed_barcode_rfid`
- [ ] Log in as `admin_acme` / `demo123`, walk through each of the 4 submodules' list + detail + create pages
- [ ] Verify filters work on list pages; verify state transitions POST-only; verify cross-tenant IDOR probe fails

### Phase 9 — README update
- [ ] Add Module 15 section after Module 14 in README
- [ ] Update Planned Modules table (remove #15 from planned, renumber remaining)
- [ ] Append `seed_barcode_rfid` to installation/seed command list
- [ ] Update Demo Data Includes section

### Phase 10 — Git commits (separate, PowerShell-safe)
- [ ] One-line commit per file per project rules, chained with `;` not `&&`

---

## Verification Before "Done"

- [ ] `python manage.py check` passes
- [ ] `python manage.py makemigrations --check --dry-run` reports no pending
- [ ] Seed runs idempotently twice in a row
- [ ] Manual UI walkthrough: list + detail + create + edit + delete works for each of 9 models
- [ ] Filters return correct results (status + FK)
- [ ] Cross-tenant IDOR probe in shell: `admin_acme` cannot `POST /barcode-rfid/tags/<other_tenant_tag_pk>/edit/` (should 404)
- [ ] State-transition GET returns 405 (require_POST enforcement)
- [ ] Non-tenant-admin user blocked from create/edit/delete (tenant_admin_required)
- [ ] No `|default` chains on nullable FK user renders

Automated tests (module-level `tests/` folder matching the 1011-test pattern in README) are **out of scope for this build** by default — existing modules added tests in follow-up SQA passes. Please confirm if you want them included now.

---

## Open Questions Before I Build

1. **Module number** — confirm **15** (per README Planned Modules), not 14.
2. **Tests** — include a `barcode_rfid/tests/` suite up front, or defer to a later SQA pass like the other modules (catalog, vendors, etc., got tests added later)?
3. **Label rendering** — do you want actual barcode/QR PDF generation, or just the data model + status workflow for now? Real rendering adds a dependency (`python-barcode` + `qrcode` + `reportlab`). Recommendation: **model/workflow only in this build**; rendering becomes a follow-up with a clear dep discussion.
4. **Scan endpoints** — do you want an **API/POST endpoint** for real-time scans from devices (JSON `POST /api/barcode-rfid/scan/` with auth token), or only web UI forms? Recommendation: **web UI forms only** for this build; device API is a separate concern that deserves its own auth model.
5. **Sidebar grouping** — one top-level "Barcode & RFID" parent with 4 sub-items (recommended), or folded under an existing group?

---

## Review

### Delivered

| Phase | Status |
|-------|--------|
| 1. App scaffolding | ✅ `barcode_rfid/` app registered in `INSTALLED_APPS` + `config/urls.py` (web + `/api/barcode-rfid/`) |
| 2. Models + migrations | ✅ 9 models, migration `0001_initial`, applied cleanly |
| 3. Forms + inline formset | ✅ 7 ModelForms + `BatchScanItemFormSet` — TenantUniqueCodeMixin on 5 forms, zone-vs-warehouse cross-validation on 2, formset form accepts tenant in `__init__` |
| 4. Views + URLs | ✅ 36 web views (CRUD + 14 state transitions + PDF render), triad `@tenant_admin_required + @require_POST + emit_audit` on every destructive/transition endpoint |
| 5. Templates + sidebar | ✅ 22 templates (list/form/detail for 7 editable models + ledger list/detail for 2), sidebar entry with 4 sub-items |
| 6. Admin | ✅ `TenantScopedAdmin` registration for all 9 models |
| 7. PDF rendering | ✅ `rendering.py` — reportlab + python-barcode + qrcode, supports CODE128 / EAN13 / UPC-A / QR / mixed layouts |
| 8. Device scan API | ✅ 4 endpoints (`/scan`, `/batch-scan`, `/rfid-read`, `/heartbeat`) — `Authorization: Device <token>` auth, tenant derived from device (never payload) |
| 9. Seed command | ✅ Idempotent; verified two back-to-back runs; skips tenants without warehouses |
| 10. Tests | ✅ 158 tests passing (models 58, forms 16, views 38, security 34, API 12) |
| 11. Smoke test | ✅ `python manage.py check` clean; `seed_barcode_rfid` idempotent; 1419/1420 project tests pass (the one failure is a pre-existing uncommitted `multi_location` test — not this module) |
| 12. README + git list | ✅ README updated (structure tree, Module 15 section, planned-modules row removed, seed commands, demo data); tech stack includes new deps |

### Lesson-informed guardrails verified working

- **`unique_together(tenant, X)` trap** — `TenantUniqueCodeMixin` on `LabelTemplateForm.code`, `ScannerDeviceForm.device_code`, `RFIDTagForm.epc_code`, `RFIDReaderForm.reader_code`. Test: `test_form_rejects_duplicate_code_in_same_tenant_via_clean`.
- **Inline-formset POST-path IDOR** — `BatchScanItemForm.__init__` accepts `tenant`; view passes `form_kwargs={'tenant': tenant}` on GET + POST. Test: `test_batch_item_tenant_injection_forced_to_session_tenant`.
- **Auto-number race** — `_save_with_number_retry` reused for `LPJ-NNNNN` + `BSS-NNNNN`. Test: `test_retry_does_not_corrupt_on_collision`.
- **State transition triad** — every transition view is `@tenant_admin_required + @require_POST + emit_audit` + `can_transition_to` guard. Tests: `test_state_transition_requires_POST_GET_returns_405`, `test_non_admin_user_blocked_from_transition`.
- **CRUD completeness** — 5-view CRUD (list/create/detail/edit/delete) for 7 editable models; `ScanEvent` + `RFIDReadEvent` are intentionally ledger-only (no edit/delete in UI — documented exception).
- **Multi-tenancy** — every `Model.objects.filter(tenant=request.tenant)`; every `get_object_or_404` tenant-scoped. Test: `test_cross_tenant_*_blocked`.
- **None-guard templates** — every nullable FK user/zone/warehouse render uses `{% if fk %}...{% endif %}` instead of `|default` chains.
- **Seed idempotency** — verified; skip-if-exists check gates the per-tenant block.

### Known scope decisions

- **Tests live in `barcode_rfid/tests/`** (158 tests, first run green). Did not backfill regression-style `test_D<NN>_*` naming because this module built defects out from the start rather than finding them.
- **PDF rendering** — synchronous + CPU-bound; fine for label batches in the hundreds. For tens of thousands, a background-worker refactor (Celery / RQ) is needed — out of scope here.
- **Device API token auth** — simple opaque token model (no JWT / OAuth). Tokens live on `ScannerDevice.api_token`, rotatable via the "Rotate Token" UI button. If a compliance audit later requires expiring tokens / refresh flow, that's a follow-up.
- **Scan resolution precedence** — serial → lot → RFID → product.sku → product.barcode → bin.code. Documented in `api_views._resolve_barcode`.

### Pre-existing repo state (NOT touched by this build)

- `forecasting/`, `multi_location/`, `orders/` had uncommitted modifications before this session.
- `multi_location/tests/test_views_stock_visibility.py::test_stats_roll_up_consistent_after_collapse` fails on main as-is — belongs to that separate in-flight work. Confirmed via `git stash` that the failure is not mine.

### Follow-ups (not in scope for this build)

- Background-worker path for massive label batches.
- Device API auth upgrade (JWT / rotating refresh tokens) if compliance demands.
- Product-level deep-link from `LabelPrintJob.target_id` into the actual Product / Lot / Serial / Bin record (currently stored as opaque `target_id` + `target_display`). Would need a generic resolver.
- Real-time RFID read stream ingest (WebSocket / webhook) — current API is poll-one-at-a-time.
