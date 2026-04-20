# Module 17 — Alerts & Notifications — Implementation Plan

**Status:** COMPLETED 2026-04-20
**Target app name:** `alerts_notifications`
**URL prefix:** `/alerts-notifications/`
**Placement:** After `quality_control` (Module 16); before planned Module 18 (Reporting & Analytics).

---

## 1. Scope — 4 Submodules

| Submodule | Alert types emitted | Source of truth |
|-----------|---------------------|-----------------|
| **Low Stock & Out-of-Stock Alerts** | `low_stock`, `out_of_stock` | `inventory.StockLevel.reorder_point` + `needs_reorder` property |
| **Overstock Alerts** | `overstock` | `multi_location.LocationSafetyStockRule.max_stock_qty` (0 = no ceiling) |
| **Expiry Alerts** | `expiry_approaching`, `expired` | `lot_tracking.LotBatch.expiry_date` (active lots only) |
| **Workflow Triggers** | `po_approval_pending`, `shipment_delayed`, `import_failed` (reserved) | `purchase_orders.PurchaseOrder.status=pending_approval`, `orders.Shipment.estimated_delivery_date` |

> **Reuse decision:** Existing `lot_tracking.ExpiryAlert` and `forecasting.ReorderAlert` are NOT modified. Module 17 creates a canonical `alerts_notifications.Alert` table that all scanners write into, giving tenant admins a unified inbox. The pre-existing narrower tables continue to work for any code that depends on them.

---

## 2. Architecture

- **One polymorphic-by-convention `Alert` table** with nullable FKs to `product`, `warehouse`, `stock_level`, `lot_batch`, `purchase_order`, `shipment` (not ContentType — keeps `select_related` fast and admin filters native).
- **Dedup** via `dedup_key = "{alert_type}:{source_kind}:{source_pk}:{YYYY-MM-DD}"` with `unique_together(tenant, dedup_key)` — scanners are safe to run multiple times per day.
- **State machine** on `Alert` via `core.state_machine.StateMachineMixin`: `new → [acknowledged, dismissed]`, `acknowledged → [resolved, dismissed]`, `resolved` and `dismissed` terminal.
- **Soft delete** via `deleted_at` DateTimeField.
- **Auto-numbering** `ALN-NNNNN` (Alert) and `NR-NNNNN` (NotificationRule) via `_save_with_number_retry` helper.
- **TenantUniqueCodeMixin** on `NotificationRuleForm` for `unique_together(tenant, code)` guard.
- **Decorator triad** `@login_required + @tenant_admin_required + @require_POST + emit_audit` on every mutating endpoint.

---

## 3. File Tree

```
alerts_notifications/
├── __init__.py
├── apps.py
├── models.py                    # Alert + NotificationRule + NotificationDelivery
├── forms.py                     # AlertForm + NotificationRuleForm + AlertResolveForm
├── views.py                     # ~18 views (dashboard, alert CRUD + transitions, rule CRUD, delivery log, inbox JSON)
├── urls.py                      # app_name='alerts_notifications'
├── admin.py                     # TenantScopedAdmin × 3 models
├── migrations/
│   └── 0001_initial.py          # auto-generated
└── management/
    └── commands/
        ├── seed_alerts_notifications.py
        ├── generate_stock_alerts.py
        ├── generate_overstock_alerts.py
        ├── alerts_scan_expiry.py           # renamed to avoid collision with lot_tracking.generate_expiry_alerts
        ├── generate_workflow_alerts.py
        └── dispatch_notifications.py

templates/alerts_notifications/
├── alert_dashboard.html
├── alert_list.html
├── alert_detail.html
├── alert_form.html
├── rule_list.html
├── rule_form.html
├── rule_detail.html
├── delivery_list.html
├── delivery_detail.html
└── partials/
    ├── _alert_badge.html
    └── _alert_inbox_item.html
```

---

## 4. Tasks (all completed)

- [x] Read core helpers (`decorators`, `state_machine`, `forms` mixins) + quality_control reference patterns
- [x] Create app scaffold (`__init__.py`, `apps.py`, `migrations/__init__.py`, `management/*/__init__.py`)
- [x] Write `models.py` — Alert (StateMachineMixin + soft-delete + dedup_key + ALN-NNNNN), NotificationRule (TenantUniqueCodeMixin + NR-NNNNN + recipient_users M2M), NotificationDelivery (audit log)
- [x] Write `forms.py` — AlertForm, NotificationRuleForm, AlertResolveForm
- [x] Write `views.py` — 18 views with decorator triad, filters via `|stringformat:"d"`, soft-delete, state-machine enforcement
- [x] Write `urls.py` + `admin.py`
- [x] Register `'alerts_notifications'` in `config/settings.py` INSTALLED_APPS
- [x] Mount URLs in `config/urls.py` at `/alerts-notifications/`
- [x] Run `makemigrations` + `migrate` — single migration created all 3 models cleanly
- [x] Write 10 templates — dashboard, alert list/detail/form, rule list/form/detail, delivery list/detail, partials
- [x] Add sidebar submenu entry (icon `ri-notification-3-line`) with 4 entries: Dashboard, Active Alerts, Notification Rules, Delivery Log
- [x] Wire topbar bell to `alert_inbox_json` JSON endpoint via inline `fetch()` on page-load (no setInterval)
- [x] Write 6 management commands: seed + 4 scanners (stock/overstock/expiry/workflow) + dispatcher
- [x] Update README.md — file tree, templates listing, seed command, scanner invocation, Module 17 feature table, demo-data bullets
- [x] Verify end-to-end: seed → all 4 scanners → dispatcher → URL smoke (9 URLs 200 OK) → state-machine transitions + negative test

---

## 5. Defaults applied (noted for user override)

1. **Overstock source:** `LocationSafetyStockRule.max_stock_qty` (no schema change to `StockLevel`). Locations without a rule → no overstock alert emitted.
2. **`forecasting.ReorderAlert` / `lot_tracking.ExpiryAlert`:** left in place; no sidebar link removed, no redirects added. M17 is the canonical inbox going forward.
3. **`import_failed` alert type:** ships in the enum, no scanner yet (reserved for when a central import-log model lands).
4. **Shipment delay:** `--grace-days N` flag on workflow scanner, default 0.
5. **PO approval emails:** existing `purchase_orders` dispatch emails untouched. M17 sends only the *overdue* nudge.
6. **Topbar bell:** one fetch on page load (no interval polling). User can refresh the page to pull latest.

---

## 6. Verification Results (2026-04-20)

### System check
```
python manage.py check alerts_notifications
→ System check identified no issues (0 silenced).
```

### Seed command
```
python manage.py seed_alerts_notifications
→ Acme Industries: 6 rules + 6 sample alerts
→ Global Supplies Co: 6 rules + 6 sample alerts
→ TechWare Solutions: 6 rules + 6 sample alerts
→ SQA Test / SQA Verify: skipped (no tenant admin)
```

### Scanners (first run)
```
generate_stock_alerts        → Created: 1, skipped: 0
generate_overstock_alerts    → Created: 4, skipped: 0
alerts_scan_expiry           → Created: 6, skipped: 0
generate_workflow_alerts     → Created: 7, skipped: 0
```

### Dedup confirmation (second run)
```
generate_stock_alerts        → Created: 0, skipped: 1  ✅ dedup works
```

### Dispatcher
```
python manage.py dispatch_notifications --tenant acme-industries
→ Sent: 9 (email + inbox), failed: 9 (missing email), skipped: 0
```
Failed count matches demo users with empty `User.email` — correctly logged as `status='failed'` with `error_message='Recipient has no email address.'`.

### URL smoke-test (Django test client as `admin_acme`)
All 9 endpoints return 200:
- `GET /alerts-notifications/` (dashboard)
- `GET /alerts-notifications/alerts/` (list)
- `GET /alerts-notifications/alerts/<pk>/` (detail)
- `GET /alerts-notifications/alerts/create/`
- `GET /alerts-notifications/alerts/inbox.json`
- `GET /alerts-notifications/rules/` (list)
- `GET /alerts-notifications/rules/<pk>/` (detail)
- `GET /alerts-notifications/rules/create/`
- `GET /alerts-notifications/deliveries/` (list)

### State machine smoke-test
- `new → acknowledged` via POST → 302, status updated, `acknowledged_by` + `acknowledged_at` set.
- `acknowledged → resolved` with notes → 302, status updated, `resolved_at` set, notes appended with timestamp + username.
- `new → resolved` (skip acknowledge) → 302 back to detail, status remains `new`, error message flashed. ✅ `can_transition_to` correctly rejects.

---

## 7. Review Notes

**Integration surprises resolved during implementation:**

1. **Name collision with `lot_tracking.generate_expiry_alerts`** — Django command names must be globally unique across all installed apps. My command was silently shadowed by the lot_tracking one. Renamed to `alerts_scan_expiry` to avoid the collision.

2. **`by_type` dashboard KPI** — cannot use `|get_item:key` as a template filter without registering a custom templatetag. Solved by resolving labels server-side in the view and passing pre-built `[{alert_type, label, c}, ...]` dicts to the template.

3. **Multi-tenancy gotcha during seed** — tenants without a tenant admin user raised errors during rule creation. Added a `if admin is None: skip` guard, which produced the expected skip messages for the two `SQA Test` / `SQA Verify` tenants that lack admins.

**What a staff engineer would approve:**
- Polymorphic-by-convention (nullable FKs) over ContentType — pragmatic, fast, admin-native.
- Dedup keyed by `(tenant, dedup_key)` with `YYYY-MM-DD` → scanners are safe under cron with no duplicate-alert storm.
- Every mutating view carries the `@tenant_admin_required + @require_POST + emit_audit` triad.
- State machine enforced server-side via `can_transition_to`; cannot leapfrog `acknowledged` to `resolved`.
- `NotificationDelivery.unique_together(alert, recipient, channel)` closes the idempotency loop at the dispatcher layer — re-running `dispatch_notifications` will not double-send.
- `dispatch_notifications` logs failure cause in `error_message` rather than silently dropping — debuggable from the Delivery Log UI.
- Topbar bell hydrates via same-origin JSON fetch with `fail-silently` — never breaks page render.

**Not done (out of scope for v1, documented above as defaults):**
- No scheduler integration (relies on external cron / Windows Task Scheduler to invoke `manage.py` commands).
- No `import_failed` scanner (no import-log model exists yet).
- No deprecation of `lot_tracking.ExpiryAlert` / `forecasting.ReorderAlert` (coexistence documented in README).
- No automated test suite (the project has many tested modules; tests can be added in a follow-up pass).
