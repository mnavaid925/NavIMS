# Module 16 — Quality Control (QC) & Inspection — Implementation Plan

**Status:** AWAITING USER APPROVAL (do not implement until user confirms)
**Date:** 2026-04-19

**Target app name:** `quality_control`
**URL prefix:** `/quality-control/`
**Placement:** After `barcode_rfid` (Module 15); before planned Module 17 (Alerts & Notifications).

---

## 1. Scope — 4 Submodules

| Submodule | Primary Model(s) | Purpose |
|-----------|------------------|---------|
| **QC Checklists** | `QCChecklist`, `QCChecklistItem` | Define mandatory quality checks per product and/or vendor |
| **Inspection Routing** | `InspectionRoute`, `InspectionRouteRule` | Route received items to a QC zone before they enter main inventory |
| **Quarantine Management** | `QuarantineRecord` | Hold defective/suspicious items in a restricted zone with release workflow |
| **Defect & Scrap Reporting** | `DefectReport`, `DefectPhoto`, `ScrapWriteOff` | Log defects with photos, write off scrapped items with stock adjustment |

> **Reuse decision:** The existing `receiving.QualityInspection` model stays as-is — it is transactional (one inspection per GRN). The new `quality_control` module layers *policy* (checklists, routing, quarantine, defect ledger) on top. `DefectReport` can optionally link to a `QualityInspection` for traceability but does not require it (defects can also be raised post-putaway during stocktaking or from customer returns).

---

## 2. File Tree To Be Created

```
quality_control/
├── __init__.py
├── apps.py
├── models.py
├── forms.py
├── views.py
├── urls.py
├── admin.py
├── migrations/
│   └── __init__.py
└── management/
    ├── __init__.py
    └── commands/
        ├── __init__.py
        └── seed_quality_control.py

templates/quality_control/
├── checklist_list.html / checklist_form.html / checklist_detail.html
├── route_list.html / route_form.html / route_detail.html
├── quarantine_list.html / quarantine_form.html / quarantine_detail.html
├── defect_list.html / defect_form.html / defect_detail.html
└── scrap_list.html / scrap_form.html / scrap_detail.html   (15 templates)
```

**Files edited (not created):**
- `config/settings.py` — add `'quality_control'` to `INSTALLED_APPS`
- `config/urls.py` — add `path('quality-control/', include('quality_control.urls'))`
- `templates/partials/sidebar.html` — add Quality Control submenu after Barcode & RFID
- `README.md` — Module 16 feature table, file-tree entry, seed command, demo-data bullets

**Tests:** Deferred to a follow-up SQA review (matches the pattern used for `barcode_rfid` before it had tests).

---

## 3. Models (detailed)

All models follow codebase conventions:
- `tenant = ForeignKey('core.Tenant', on_delete=CASCADE, related_name=...)` — first field
- `created_at` / `updated_at` timestamps
- `_save_with_number_retry()` + `unique_together('tenant', number_field)` for auto-numbered docs
- `TenantUniqueCodeMixin` used in forms; `StateMachineMixin` on stateful models
- Soft-delete (`deleted_at`) on top-level docs (quarantine, defect, scrap) for audit traceability

### 3.1 QCChecklist (Submodule 1)
| Field | Type | Notes |
|-------|------|-------|
| tenant | FK Tenant | |
| code | CharField(20), unique-per-tenant | auto `QCC-00001` |
| name | CharField(200) | |
| description | TextField(blank=True) | |
| applies_to | choices `product`/`vendor`/`category`/`all` | scope |
| product | FK catalog.Product (null, blank) | required if applies_to='product' |
| vendor | FK vendors.Vendor (null, blank) | required if applies_to='vendor' |
| category | FK catalog.Category (null, blank) | required if applies_to='category' |
| is_mandatory | Boolean default True | |
| is_active | Boolean default True | |
| created_by | FK User | |

### 3.2 QCChecklistItem
| Field | Type | Notes |
|-------|------|-------|
| checklist | FK QCChecklist related_name='items' | |
| sequence | PositiveInteger | ordering |
| check_name | CharField(200) | e.g., "Visual inspection — no cracks" |
| check_type | choices `visual`/`measurement`/`boolean`/`text`/`photo` | |
| expected_value | CharField(200, blank=True) | e.g., "> 10kg", "Yes" |
| is_critical | Boolean | failing a critical item auto-quarantines |

### 3.3 InspectionRoute (Submodule 2)
| Field | Type | Notes |
|-------|------|-------|
| tenant | FK Tenant | |
| code | auto `IR-00001` | |
| name | CharField(200) | |
| source_warehouse | FK warehousing.Warehouse | |
| qc_zone | FK warehousing.Zone | hold zone pending QC |
| putaway_zone | FK warehousing.Zone (null) | destination after QC pass |
| priority | PositiveInteger default 100 | lower = higher priority |
| is_active | Boolean default True | |

### 3.4 InspectionRouteRule
| Field | Type | Notes |
|-------|------|-------|
| route | FK InspectionRoute related_name='rules' | |
| applies_to | choices `all`/`product`/`vendor`/`category` | |
| product / vendor / category | FKs (all null/blank) | matches applies_to |
| checklist | FK QCChecklist (null) | auto-attached when rule matches |

### 3.5 QuarantineRecord (Submodule 3) — StateMachineMixin
| Field | Type | Notes |
|-------|------|-------|
| tenant | FK Tenant | |
| quarantine_number | auto `QR-00001` | |
| product | FK catalog.Product | |
| warehouse | FK warehousing.Warehouse | |
| zone | FK warehousing.Zone | quarantine zone |
| quantity | Decimal(12,2) | |
| reason | choices `defect`/`expiry`/`contamination`/`damage`/`vendor_issue`/`other` | |
| reason_notes | TextField(blank=True) | |
| grn | FK receiving.GoodsReceiptNote (null, blank) | source (optional) |
| lot | FK lot_tracking.LotBatch (null, blank) | |
| status | choices `active`/`under_review`/`released`/`scrapped` default `active` | |
| held_by | FK User | |
| released_by | FK User (null, blank) | |
| released_at | DateTime (null, blank) | |
| release_disposition | choices `return_to_stock`/`rework`/`scrap`/`return_to_vendor` (null) | |
| deleted_at | DateTime (null) — soft-delete | |
| VALID_TRANSITIONS | `active→under_review,released,scrapped`; `under_review→released,scrapped` | |

### 3.6 DefectReport (Submodule 4) — StateMachineMixin
| Field | Type | Notes |
|-------|------|-------|
| tenant | FK Tenant | |
| defect_number | auto `DEF-00001` | |
| product | FK catalog.Product | |
| lot | FK lot_tracking.LotBatch (null, blank) | |
| serial | FK lot_tracking.SerialNumber (null, blank) | |
| warehouse | FK warehousing.Warehouse | |
| quantity_affected | Decimal(12,2) | |
| defect_type | choices `visual`/`functional`/`packaging`/`labeling`/`expiry`/`contamination`/`other` | |
| severity | choices `minor`/`major`/`critical` | |
| description | TextField | |
| source | choices `receiving`/`stocktaking`/`customer_return`/`production`/`other` | |
| grn | FK receiving.GoodsReceiptNote (null, blank) | |
| quarantine_record | FK QuarantineRecord (null, blank) | optional link |
| status | choices `open`/`investigating`/`resolved`/`scrapped` | |
| reported_by | FK User | |
| resolved_by | FK User (null, blank) | |
| resolution_notes | TextField(blank=True) | |
| deleted_at | DateTime (null) | |

### 3.7 DefectPhoto
| Field | Type | Notes |
|-------|------|-------|
| defect_report | FK DefectReport related_name='photos' | |
| image | ImageField(upload_to='quality_control/defect_photos/') | |
| caption | CharField(200, blank=True) | |
| uploaded_at | DateTime auto_now_add | |

### 3.8 ScrapWriteOff
| Field | Type | Notes |
|-------|------|-------|
| tenant | FK Tenant | |
| scrap_number | auto `SCR-00001` | |
| defect_report | FK DefectReport (null, blank) | optional source |
| quarantine_record | FK QuarantineRecord (null, blank) | optional source |
| product | FK catalog.Product | |
| warehouse | FK warehousing.Warehouse | |
| quantity | Decimal(12,2) | |
| unit_cost | Decimal(14,4) | |
| total_value | Decimal(14,2) computed in save() | |
| reason | CharField(200) | |
| approval_status | choices `pending`/`approved`/`rejected`/`posted` | |
| approved_by | FK User (null, blank) | |
| posted_at | DateTime (null, blank) | set when stock adjustment is written |
| deleted_at | DateTime (null) | |

**Stock integration:** On `post` transition, `ScrapWriteOff` creates a negative `inventory.StockAdjustment` (adjustment_type='write_off') inside `transaction.atomic()` + `select_for_update()` on the `StockLevel` row — mirrors patterns in `returns/` and `stocktaking/`. Quarantine is a *logical* hold, not a physical stock move; releasing with disposition `scrap` auto-creates a `ScrapWriteOff`.

---

## 4. Forms

All forms accept `tenant=None` in `__init__`, filter FK querysets by tenant, and inject tenant in `save(commit=False)` before final save.

- `QCChecklistForm` (uses `TenantUniqueCodeMixin`, `tenant_unique_field='code'`)
- `QCChecklistItemFormSet` (inline, tenant-aware form_kwargs)
- `InspectionRouteForm` (clean: `qc_zone.warehouse_id == source_warehouse_id` guard)
- `InspectionRouteRuleFormSet` (inline)
- `QuarantineRecordForm` (clean: `zone` belongs to `warehouse`; quantity > 0)
- `QuarantineReleaseForm` (disposition + release notes; POST-only release endpoint)
- `DefectReportForm` + `DefectPhotoFormSet` (inline, extra=3)
- `ScrapWriteOffForm` (clean: quantity > 0, unit_cost ≥ 0; compute `total_value`)

---

## 5. Views

All views `@login_required`. Mutations (`create` / `edit` / `delete` / transition) add `@tenant_admin_required` + `@require_POST` (where applicable) + `emit_audit(...)` on success.

Per submodule (mirrors barcode_rfid pattern):

| Submodule | Views |
|-----------|-------|
| **Checklists** (6) | list, create, detail, edit, delete, toggle_active |
| **Routes** (7) | list, create, detail, edit, delete, rule_add, rule_delete |
| **Quarantine** (7) | list, create, detail, edit, delete (while `active`), release (POST), review (POST) |
| **Defects** (7) | list, create, detail, edit, delete (while `open`), resolve (POST), photo_delete (POST) |
| **Scrap** (7) | list, create, detail, edit, delete (while `pending`), approve (POST), post (POST — atomic StockAdjustment), reject (POST) |

**Total: ~34 views.** All list views: `Paginator(qs, 20)` + search (`request.GET.get('q')`) + status/type filters; views pass ALL `choices` tuples + FK querysets into context (per CLAUDE.md filter rules).

---

## 6. URLs (`quality_control/urls.py`)

```python
app_name = 'quality_control'

# ── Submodule 1: QC Checklists ──
# ── Submodule 2: Inspection Routing ──
# ── Submodule 3: Quarantine Management ──
# ── Submodule 4: Defect & Scrap Reporting ──
```

Each entity follows `checklists/`, `checklists/new/`, `checklists/<int:pk>/`, `checklists/<int:pk>/edit/`, `checklists/<int:pk>/delete/`, plus transition endpoints (`/release/`, `/approve/`, `/post/`, etc.).

---

## 7. Admin

`quality_control/admin.py` registers all 8 models with `TenantScopedAdmin` mixin (copied from `returns/admin.py` — 11-line pattern). Inlines: `QCChecklistItemInline`, `InspectionRouteRuleInline`, `DefectPhotoInline`.

---

## 8. Seeder

`quality_control/management/commands/seed_quality_control.py`:
- Idempotent: `if QCChecklist.objects.filter(tenant=tenant).exists(): skip`
- Per tenant creates:
  - 3 QCChecklists (1 product-scoped, 1 vendor-scoped, 1 global) — 3-5 items each
  - 2 InspectionRoutes (standard + express) with 2 rules each
  - 4 QuarantineRecords (active/under_review/released/scrapped)
  - 5 DefectReports across severities + sources (photos skipped — needs real files)
  - 2 ScrapWriteOffs (pending + posted) — posted one creates real StockAdjustment
- `--flush` flag tears down in reverse FK order
- Prints tenant-admin credentials + the "superuser has no tenant" warning at end

---

## 9. Templates

All templates extend `base.html`, follow conventions in `templates/barcode_rfid/`. Filter dropdowns:
- Pass `status_choices`, `severity_choices`, `type_choices` from view context
- Use `|stringformat:"d"` for FK pk comparison (CLAUDE.md rule)
- Include `{% else %}` fallback `{{ obj.get_field_display }}` on badges
- Every list has Actions column (View / Edit / Delete with CSRF + confirm)
- Every detail has Actions sidebar (Edit / Delete / state transitions — conditional on status)

---

## 10. Wiring Changes

1. `config/settings.py` — append `'quality_control',` to `INSTALLED_APPS`
2. `config/urls.py` — add `path('quality-control/', include('quality_control.urls'))`
3. `templates/partials/sidebar.html` — new `has-submenu` block after Barcode & RFID with icon `ri-shield-check-line` and 4 child links
4. `README.md` — append Module 16 section (feature table), file-tree entry, seed command, demo-data bullets

---

## 11. Migration

Single migration: `python manage.py makemigrations quality_control` → produces `0001_initial.py`.
Then `python manage.py migrate quality_control`.

---

## 12. Out of Scope (for this task)

- **Automated tests** — deferred to follow-up SQA review
- **PDF defect/scrap reports** — would need reportlab templates
- **Auto-trigger routing on GRN creation** — receiving module hook; Phase 2
- **Checklist revision history** — not in requirements

---

## 13. Per-file Git Commit Plan (PowerShell-safe, one per file)

Commits will be supplied at the end of implementation — one `git add` + `git commit` pair per file, `;`-separated for PowerShell. Estimated ~32 files × 1 commit each.

---

## Checklist (to be ticked as work progresses, once approved)

- [ ] `quality_control/__init__.py` + `apps.py`
- [ ] `quality_control/models.py` (8 models)
- [ ] `quality_control/forms.py`
- [ ] `quality_control/views.py` (~34 views)
- [ ] `quality_control/urls.py`
- [ ] `quality_control/admin.py`
- [ ] `quality_control/migrations/0001_initial.py`
- [ ] `quality_control/management/commands/seed_quality_control.py`
- [ ] 15 templates under `templates/quality_control/`
- [ ] `config/settings.py` — INSTALLED_APPS
- [ ] `config/urls.py` — include
- [ ] `templates/partials/sidebar.html` — submenu
- [ ] `README.md` — Module 16 section
- [ ] Migration run clean
- [ ] Seeder runs clean on a fresh tenant
- [ ] Smoke-test: login as `admin_acme`, walk every list/create/detail page
- [ ] Per-file commit list supplied

---

## Review Section — 2026-04-19

### What shipped
- New `quality_control/` Django app (Module 16) with 8 models, 7 forms + 3 inline formsets, ~34 views, 1 migration, 1 idempotent seeder.
- 15 templates under `templates/quality_control/` — all 5 submodule list/form/detail triads.
- Wired into `config/settings.py` (INSTALLED_APPS), `config/urls.py` (`/quality-control/`), and `templates/partials/sidebar.html` (new submenu with 5 links + `ri-shield-check-line` icon).
- `README.md` updated: file-tree, seed commands, demo-data bullets, Module 16 feature table. Module 16 removed from "Planned" list.

### Deviations from plan
- **Stock write path:** Plan listed `StockAdjustment(adjustment_type='write_off')`, but real `inventory.StockAdjustment.ADJUSTMENT_TYPE_CHOICES` only has `increase / decrease / correction`. Posting uses `decrease` + `reason='damage'` and calls `apply_adjustment()` — the canonical helper. Matches the pattern in `returns/` and `stocktaking/`.
- **ScrapWriteOff status field:** Added a shadow `status` field kept in lockstep with `approval_status` in `save()`, so `StateMachineMixin.can_transition_to()` (which reads `self.status`) stays accurate without duplicating choice tuples on each call site.
- **Segregation of duties:** Added on `scrap_approve_view` — requester cannot self-approve (matches `returns.rma_approve_view` pattern).
- **Vendor FK label:** plan called it `vendor.name`; the real model field is `company_name`. Fixed in templates + seeder.

### Smoke-test results
- `python manage.py check` — 0 issues.
- `python manage.py makemigrations quality_control` → clean `0001_initial.py` (8 models).
- `python manage.py migrate quality_control` — applied OK.
- `python manage.py seed_quality_control` — seeded 3 tenants cleanly (3 checklists + 2 routes + 4 quarantines + 5 defects + 2 scrap write-offs each; scrap #2 posted a real `StockAdjustment`).
- Re-running the seeder skipped already-seeded tenants (idempotent).
- Django test client as `admin_acme`: 11/11 QC endpoints (all 5 list pages + 5 detail + 4 create + 1 edit) returned HTTP 200.

### Out of scope (as agreed)
- Automated pytest suite (deferred to follow-up SQA review, matching how `barcode_rfid` shipped).
- PDF rendering for defect / scrap reports.
- Auto-trigger of inspection routing on GRN creation (receiving hook; Phase 2).
- Checklist revision history.

### Files changed / created (32 total)
**Created:**
- `quality_control/__init__.py`, `apps.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`
- `quality_control/migrations/__init__.py`, `0001_initial.py`
- `quality_control/management/__init__.py`, `management/commands/__init__.py`, `management/commands/seed_quality_control.py`
- 15 templates under `templates/quality_control/`

**Modified:**
- `config/settings.py`, `config/urls.py`, `templates/partials/sidebar.html`, `README.md`, `.claude/tasks/todo.md`
