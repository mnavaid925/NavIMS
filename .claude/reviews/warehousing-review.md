# Warehousing & Bin Management — Comprehensive SQA Test Report

**Target:** [warehousing/](warehousing/) Django app (Warehouse → Zone → Aisle → Rack → Bin hierarchy + Cross-Dock orders)
**Scope:** Module review (default)
**Date:** 2026-04-17
**Report file:** [.claude/reviews/warehousing-review.md](.claude/reviews/warehousing-review.md)

---

## 1. Module Analysis

### 1.1 Inventory

| Artefact | Path | LOC | Notes |
|---|---|---|---|
| Models | [warehousing/models.py](warehousing/models.py) | 404 | 7 models: Warehouse, Zone, Aisle, Rack, Bin, CrossDockOrder, CrossDockItem |
| Forms | [warehousing/forms.py](warehousing/forms.py) | 384 | 6 ModelForms + CrossDockItemFormSet |
| Views | [warehousing/views.py](warehousing/views.py) | 867 | 34 views (6 CRUD families + map + status + reopen) |
| Admin | [warehousing/admin.py](warehousing/admin.py) | 85 | All 7 models registered with inlines |
| URLs | [warehousing/urls.py](warehousing/urls.py) | 51 | 35 URL patterns |
| Templates | [templates/warehousing/](templates/warehousing/) | 19 files | list/form/detail per entity + warehouse_map |
| Seed | [warehousing/management/commands/seed_warehousing.py](warehousing/management/commands/seed_warehousing.py) | 355 | Idempotent; 2 WH + 8 zones + bins + 3 cross-dock orders per tenant |
| Tests | [warehousing/tests.py](warehousing/tests.py) | 3 | **Empty — zero coverage** |

### 1.2 Entity hierarchy & domain rules

- **Hierarchy:** `Warehouse → Zone → Aisle → Rack → Bin`. `Bin.rack` is **nullable** (floor bins). `Bin.zone` is **required** — a bin belongs to a zone directly even when it has a rack, which creates an **invariant** that `bin.zone == bin.rack.aisle.zone` (not enforced — see D-04).
- **Auto-generated codes:** `Warehouse.code` (`WH-NNNNN`) and `CrossDockOrder.order_number` (`CD-NNNNN`) are auto-generated per-tenant via max-number-plus-one in `save()` — race-condition-prone ([warehousing/models.py:57-71](warehousing/models.py#L57-L71), [warehousing/models.py:357-371](warehousing/models.py#L357-L371)).
- **Zone/Aisle/Rack/Bin codes:** user-entered; `unique_together = ('tenant', 'code')` enforced at DB level only.
- **Cross-dock state machine:** 7 statuses with explicit `VALID_TRANSITIONS` table at [warehousing/models.py:306-314](warehousing/models.py#L306-L314). Auto-timestamps on `at_dock` / `dispatched` transitions. `cancelled → pending` is permitted (reopen).
- **Computed properties:** `Bin.utilization_percentage` averages weight/volume/quantity percentages (ignores zero caps); `Bin.location_path` concatenates codes for display; `Bin.available_*` clamp to 0.

### 1.3 Multi-tenancy & security posture

- Every model carries `tenant = ForeignKey('core.Tenant', ...)`. Every view correctly uses `login_required` and `get_object_or_404(..., tenant=request.tenant)` or `filter(tenant=request.tenant)` — IDOR guards are in place. Spot-check: [warehousing/views.py:79](warehousing/views.py#L79), [:220](warehousing/views.py#L220), [:589](warehousing/views.py#L589), [:724](warehousing/views.py#L724).
- Forms set `instance.tenant = self.tenant` in `save()`, so tenant injection cannot be overridden via POST data.
- Tenant determined by [core/middleware.py:7](core/middleware.py#L7) from `request.user.tenant` — not from the request — so the superuser (tenant=None) correctly sees empty lists.

### 1.4 Risk profile (pre-test)

| Area | Risk | Reason |
|---|---|---|
| Form uniqueness vs `unique_together` | **HIGH** | No `clean_code()` in Zone/Aisle/Rack/Bin forms — duplicate codes raise `IntegrityError` → 500 (known NavIMS trap, lesson #6). **Verified** in Django shell (D-01). |
| Data integrity (capacity, temperature) | **HIGH** | No validators: negative `max_weight`, `temperature_min > temperature_max`, `rack.zone ≠ bin.zone`. **All three verified** in Django shell (D-02, D-03, D-04). |
| Template / data rendering | **HIGH** | [templates/warehousing/bin_list.html:126-138](templates/warehousing/bin_list.html#L126-L138) badge mapping uses wrong choice values (`picking`, `reserve`, `staging`, `receiving`, `shipping`) vs model `BIN_TYPE_CHOICES` (`standard`, `pick`, `pallet`, `cold`, `hazmat`, `bulk`). Almost every bin falls through to `{% else %}` (D-05). |
| Concurrency | Medium | `_generate_code` / `_generate_order_number` compute max+1 without a lock — two simultaneous POSTs will collide. |
| Auditing | Medium | No `core.AuditLog` emission anywhere in the module despite destructive operations (delete, reopen, status transitions). |
| Performance | Medium | `warehouse_map_view` uses `prefetch_related('aisles__racks__bins', 'bins')` — good. Other list views use `select_related` — good. `Warehouse.bin_count` and `Zone.bin_count` properties run per-row `COUNT(*)` → N+1 when rendered in list templates. |
| Input validation | Medium | `dock_door`, `contact_phone`, address fields accept arbitrary unicode/emoji — fine; but `source`/`destination` allow 255-char free text with no trimming. |
| XSS / CSRF | Low | Django auto-escape on all `{{ var }}` usages inspected. CSRF token present on all POST forms (delete, status, reopen). |
| Authentication / RBAC | Medium | `@login_required` only — no role-based restriction on cross-dock state transitions or warehouse deletion. Any logged-in tenant user can cancel / delete. |

---

## 2. Test Plan

### 2.1 Scope

In scope: all 7 models, 6 forms, 34 views, 19 templates, 35 URLs, seed command, admin registration, state machine, multi-tenant isolation.

### 2.2 Strategy per layer

| Layer | Approach | Tools |
|---|---|---|
| **Unit** | Model `save()`, computed properties (`utilization_percentage`, `location_path`, `available_*`), `can_transition_to`, auto-code generation | pytest + pytest-django |
| **Integration** | View + form + model + DB flow; filter retention across pagination; formset save for cross-dock items | pytest-django `Client` |
| **Functional / E2E** | Full user journey: create warehouse → zone → aisle → rack → bin → map view → cross-dock order → status transitions → delete cascade | Playwright (Python) |
| **Boundary** | `max_length` (20, 255), `DecimalField(max_digits=10, decimal_places=2)`, `PositiveIntegerField` lower bound (0), unicode/emoji | Parametrised pytest |
| **Negative** | Duplicate codes, invalid status transitions, non-empty parent delete, negative capacities, zone/rack mismatch, IDOR | pytest |
| **Security** | OWASP Top 10 mapping (see §2.4) | pytest + bandit + ZAP |
| **Performance** | N+1 guards; p95 latency on 1000-bin dataset | `django_assert_max_num_queries`, Locust |
| **Regression** | Fixtures rebuilding seed data; cross-dock state-transition matrix | pytest fixtures |

### 2.3 Entry / exit criteria

**Entry:** module deploys cleanly; migrations applied; `seed_warehousing` runs without error; all URLs resolve to 200/302 for a logged-in tenant admin.

**Exit (release gate):** see §7.3.

### 2.4 OWASP Top 10 mapping

| OWASP | Covered by |
|---|---|
| A01 Broken Access Control | TC-WH-SEC-001..004 (IDOR cross-tenant, anon access, superuser tenant=None behaviour) |
| A02 Crypto failures | Out of scope for this module (no secrets handled) |
| A03 Injection / XSS | TC-WH-SEC-010..014 (SQL injection via GET, XSS in name/notes, template escape) |
| A04 Insecure design | TC-WH-NEG-020..030 (duplicate codes, temperature inversion, negative capacity, zone/rack mismatch, status-machine bypass) |
| A05 Security misconfig | Verify `DEBUG=False` + `X-Frame-Options` via integration test |
| A06 Vulnerable deps | `bandit` + `pip-audit` in CI (module-agnostic) |
| A07 Auth failures | TC-WH-SEC-020..023 (login required on all 35 URLs, session expiry) |
| A08 Data integrity | TC-WH-NEG-040 — cross-dock item quantity vs source availability (design gap; currently unchecked) |
| A09 Logging failures | TC-WH-SEC-030 — no `AuditLog` emitted on delete / status transitions (D-06) |
| A10 SSRF | N/A — no external URL fetches in module |

---

## 3. Test Scenarios

### 3.1 Warehouse (WH-NN)

| # | Scenario | Type |
|---|---|---|
| WH-01 | Create warehouse — auto-generated code `WH-NNNNN` | Unit |
| WH-02 | Create second warehouse — code increments | Unit |
| WH-03 | Warehouse with duplicate code (manual) — DB rejects | Integration |
| WH-04 | List filters: search, warehouse_type, active/inactive | Integration |
| WH-05 | Filter retention across pagination (all four combos) | Integration |
| WH-06 | Edit warehouse (fields + is_active toggle) | Integration |
| WH-07 | Delete empty warehouse — success | Integration |
| WH-08 | Delete warehouse with zones — blocked with message | Integration |
| WH-09 | IDOR — tenant A reads tenant B's warehouse detail | Security |
| WH-10 | Anonymous user accessing warehouse_list → 302 login | Security |
| WH-11 | Warehouse map shows zones/bins totals correctly | Integration |
| WH-12 | Unicode/emoji in name, address | Edge |
| WH-13 | Concurrent create — two tenant users → race condition on `WH-00001` | Performance |
| WH-14 | List view N+1 — 100 warehouses with bin_count | Performance |

### 3.2 Zone (Z-NN)

| # | Scenario | Type |
|---|---|---|
| Z-01 | Create zone within warehouse — success | Unit |
| Z-02 | Duplicate zone code within tenant — form should reject, currently raises IntegrityError (D-01) | **Negative (HIGH)** |
| Z-03 | Same zone code in different tenants — allowed | Integration |
| Z-04 | Temperature min > max — form should reject (D-02) | **Negative (MED)** |
| Z-05 | Temperature controlled = True, but min/max blank — logically weak; currently allowed | Edge |
| Z-06 | Delete zone with aisles — blocked | Integration |
| Z-07 | Delete zone with floor bins — blocked | Integration |
| Z-08 | Filter by warehouse, zone_type | Integration |
| Z-09 | Zone form accepts `warehouse` of another tenant via raw POST — IDOR attempt | Security |

### 3.3 Aisle (A-NN)

| # | Scenario | Type |
|---|---|---|
| A-01 | Create aisle under zone | Unit |
| A-02 | Duplicate aisle code within tenant — D-01 | **Negative (HIGH)** |
| A-03 | Filter by zone — queryset retention | Integration |
| A-04 | Delete aisle with racks — blocked | Integration |
| A-05 | Prefill `zone` via `?zone=<pk>` query param on create | Integration |

### 3.4 Rack (R-NN)

| # | Scenario | Type |
|---|---|---|
| R-01 | Create rack with levels=1, max_weight_capacity=None | Unit |
| R-02 | Duplicate rack code — D-01 | **Negative (HIGH)** |
| R-03 | Negative `max_weight_capacity` — currently allowed | Boundary |
| R-04 | `levels` = 0 — `PositiveIntegerField` allows 0 | Boundary |
| R-05 | Delete rack with bins — blocked | Integration |

### 3.5 Bin (B-NN)

| # | Scenario | Type |
|---|---|---|
| B-01 | Create floor bin (rack=None) | Unit |
| B-02 | Create rack bin | Unit |
| B-03 | Duplicate bin code — D-01 | **Negative (HIGH)** |
| B-04 | `max_weight < 0`, `max_volume < 0` — form accepts (D-03) | **Negative (MED)** |
| B-05 | `rack.aisle.zone != bin.zone` — form accepts (D-04) | **Negative (HIGH)** |
| B-06 | Badge rendering on bin_list for each BIN_TYPE_CHOICES value (D-05) | **Negative (MED)** |
| B-07 | `utilization_percentage` math — weight 50/100, volume 1/2, qty 10/20 → 50% | Unit |
| B-08 | `utilization_percentage` — all caps 0 → 0 | Edge |
| B-09 | `available_weight` when `current > max` → 0 (clamp) | Edge |
| B-10 | `location_path` with/without rack | Unit |
| B-11 | Delete occupied bin → blocked with message | Integration |
| B-12 | Capacity filter (available/occupied) retention | Integration |
| B-13 | List N+1 guard (zones, racks, select_related hit) | Performance |

### 3.6 Cross-Dock Order (X-NN)

| # | Scenario | Type |
|---|---|---|
| X-01 | Create with auto-number `CD-00001` | Unit |
| X-02 | State transition matrix — all 7×7 cells validated | Unit |
| X-03 | `cancelled → pending` reopen resets actual_arrival/departure | Integration |
| X-04 | Edit only while `status='pending'` | Integration |
| X-05 | Delete only while `status='pending'` | Integration |
| X-06 | `at_dock` transition auto-sets `actual_arrival` if null | Integration |
| X-07 | `dispatched` transition auto-sets `actual_departure` if null | Integration |
| X-08 | Item formset — create with 3 items | Integration |
| X-09 | Item formset — edit, delete one item via `DELETE` checkbox | Integration |
| X-10 | Status POST with invalid `new_status` — warning message, no change | Negative |
| X-11 | Status POST via GET — redirects to detail | Negative |
| X-12 | Scheduled arrival > scheduled departure — currently allowed | Edge |
| X-13 | Item `quantity=0` — `PositiveIntegerField` allows 0 (should be ≥1) | Boundary |
| X-14 | Item with `product=None` and `description=''` → `__str__` returns `'Item x Q'` | Edge |
| X-15 | Search by order_number, source, destination | Integration |
| X-16 | Filter by status + priority retention | Integration |
| X-17 | No audit log on transitions / deletion (D-06) | Security |

### 3.7 Map view (M-NN)

| # | Scenario | Type |
|---|---|---|
| M-01 | Renders zone/aisle/rack/bin tree | Integration |
| M-02 | total / occupied / available bin counts correct | Unit |
| M-03 | Large warehouse (1000 bins) — query count ≤ 15 | Performance |

### 3.8 Seed (S-NN)

| # | Scenario | Type |
|---|---|---|
| S-01 | `seed_warehousing` with no tenants — warns + returns | Integration |
| S-02 | `seed_warehousing` re-run on seeded tenant — skips | Integration |
| S-03 | `seed_warehousing --flush` — deletes then re-creates | Integration |
| S-04 | Seed prints login hint about tenant admin | Integration |

---

## 4. Detailed Test Cases

Only top-priority cases shown (high-severity and coverage-critical). Full suite auto-generated from §3 via parametrisation in §5.

### 4.1 Duplicate code → IntegrityError (Z-02, A-02, R-02, B-03)

| | |
|---|---|
| **ID** | TC-WH-NEG-001 |
| **Description** | Creating a Zone with a code that already exists in the same tenant should return a form error, not a 500 IntegrityError |
| **Pre-conditions** | Tenant T, Warehouse WH, existing `Zone(code='Z-DUP-01')` |
| **Steps** | 1. Log in as tenant admin. 2. POST `/warehousing/zones/create/` with `code=Z-DUP-01`, `warehouse=WH`. |
| **Test Data** | `name='Duplicate'`, `code='Z-DUP-01'`, `zone_type='storage'` |
| **Expected** | Response 200 with form error `"Code already exists for this tenant"`. No IntegrityError. |
| **Post-conditions** | Still exactly one zone with that code; user sees friendly message. |
| **Current behaviour** | **FAILS** — form.is_valid() returns True; IntegrityError raised on save (verified in Django shell 2026-04-17). |

### 4.2 Temperature inversion (Z-04)

| | |
|---|---|
| **ID** | TC-WH-NEG-002 |
| **Description** | ZoneForm must reject `temperature_min > temperature_max` |
| **Pre-conditions** | Tenant, Warehouse |
| **Steps** | POST zone_create with `temperature_controlled=True`, `temperature_min=50`, `temperature_max=-10` |
| **Expected** | Form error on non-field or on `temperature_max` |
| **Current behaviour** | Passes validation (verified 2026-04-17) |

### 4.3 Negative capacity (B-04)

| | |
|---|---|
| **ID** | TC-WH-NEG-003 |
| **Description** | BinForm must reject `max_weight < 0` and `max_volume < 0` |
| **Pre-conditions** | Tenant, Zone |
| **Steps** | POST bin_create with `max_weight=-100`, `max_volume=-1` |
| **Expected** | Form errors on both fields |
| **Current behaviour** | Passes validation. Widget has `min='0'` HTML attr but no server-side validator (verified 2026-04-17) |

### 4.4 Zone/rack mismatch (B-05)

| | |
|---|---|
| **ID** | TC-WH-NEG-004 |
| **Description** | BinForm must reject a bin whose `rack.aisle.zone` differs from the submitted `zone` |
| **Pre-conditions** | Tenant T with Zone Z1 (Rack R1) and Zone Z2 |
| **Steps** | POST bin_create with `zone=Z2`, `rack=R1` |
| **Expected** | Form error: "Rack must belong to the selected zone" |
| **Current behaviour** | Saves successfully. `location_path` renders nonsensical trail `Z2 > R1_aisle > R1 > BIN` (verified 2026-04-17) |

### 4.5 Bin type badge mismatch (B-06)

| | |
|---|---|
| **ID** | TC-WH-UI-001 |
| **Description** | Every value in `Bin.BIN_TYPE_CHOICES` should produce a meaningful, differentiated badge on bin_list.html |
| **Pre-conditions** | 6 bins, one per choice |
| **Steps** | GET `/warehousing/bins/` |
| **Expected** | `standard → Standard`, `bulk → Bulk`, `pick → Pick`, `pallet → Pallet`, `cold → Cold`, `hazmat → Hazmat` |
| **Current behaviour** | Only `bulk` renders its own colour; `pick/pallet/cold/hazmat/standard` fall through to the generic grey `{% else %}` badge. The template's `picking`/`reserve`/`staging`/`receiving`/`shipping` branches are unreachable (template-model drift). |

### 4.6 Cross-dock state machine (X-02)

| | |
|---|---|
| **ID** | TC-WH-CD-001 |
| **Description** | `CrossDockOrder.can_transition_to` must match `VALID_TRANSITIONS` for all 49 (from, to) pairs |
| **Pre-conditions** | Fresh CrossDockOrder |
| **Steps** | Parametrise over 7×7 status pairs |
| **Expected** | `True` for pairs listed in VALID_TRANSITIONS, `False` otherwise |
| **Current behaviour** | Correct (unit verified). Note: `cancelled → pending` is permitted (by design — reopen flow). |

### 4.7 IDOR cross-tenant (WH-09)

| | |
|---|---|
| **ID** | TC-WH-SEC-001 |
| **Description** | Tenant A must not be able to GET warehouse detail of Tenant B |
| **Pre-conditions** | Tenant A (user A), Tenant B (warehouse B_WH) |
| **Steps** | Login as user A → GET `/warehousing/<B_WH.pk>/` |
| **Expected** | 404 |
| **Current behaviour** | Correct — `get_object_or_404(Warehouse, pk=pk, tenant=request.tenant)` protects ([warehousing/views.py:79](warehousing/views.py#L79)) |

### 4.8 Delete non-empty (WH-08, Z-06, A-04, R-05)

| | |
|---|---|
| **ID** | TC-WH-DEL-001 |
| **Description** | Deleting a container with children must be refused with a flash message |
| **Pre-conditions** | Warehouse with ≥1 zone |
| **Steps** | POST `/warehousing/<pk>/delete/` |
| **Expected** | Redirect to detail, message `"Cannot delete ... it has N zones"`. Warehouse NOT deleted. |
| **Current behaviour** | Correct ([warehousing/views.py:120-127](warehousing/views.py#L120-L127)) |

### 4.9 Delete occupied bin (B-11)

| | |
|---|---|
| **ID** | TC-WH-DEL-002 |
| **Description** | Deleting a bin with `is_occupied=True` must be refused |
| **Pre-conditions** | Bin with `is_occupied=True` |
| **Steps** | POST `/warehousing/bins/<pk>/delete/` |
| **Expected** | Redirect to detail, flash message. Bin NOT deleted. |
| **Current behaviour** | Correct ([warehousing/views.py:631-637](warehousing/views.py#L631-L637)) |

### 4.10 Filter retention + pagination (WH-05, X-16)

| | |
|---|---|
| **ID** | TC-WH-UI-002 |
| **Description** | Applying search + type + active filters, then paginating, preserves all three |
| **Pre-conditions** | 25 warehouses in tenant |
| **Steps** | GET `?q=main&type=distribution_center&active=active&page=2` |
| **Expected** | Page 2 of filtered result; all three filters marked in the dropdowns/inputs |
| **Current behaviour** | Correct — hidden inputs are emitted for each filter form, and pagination links preserve query string ([templates/warehousing/warehouse_list.html:41-66](templates/warehousing/warehouse_list.html#L41-L66), [:149-165](templates/warehousing/warehouse_list.html#L149-L165)) |

### 4.11 CrossDock edit blocked post-pending (X-04)

| | |
|---|---|
| **ID** | TC-WH-CD-002 |
| **Description** | Edit view of a CrossDockOrder with status != pending redirects with warning |
| **Pre-conditions** | Order in `in_transit` status |
| **Steps** | GET `/warehousing/cross-docking/<pk>/edit/` |
| **Expected** | 302 to detail + warning flash |
| **Current behaviour** | Correct ([warehousing/views.py:766-768](warehousing/views.py#L766-L768)) |

### 4.12 Status POST with invalid transition (X-10)

| | |
|---|---|
| **ID** | TC-WH-CD-003 |
| **Description** | POST `crossdock_status` with disallowed target is refused |
| **Pre-conditions** | Order in `pending`; attempt transition to `completed` |
| **Steps** | POST `/warehousing/cross-docking/<pk>/status/` with `new_status=completed` |
| **Expected** | 302 to detail + warning flash; order stays `pending` |
| **Current behaviour** | Correct ([warehousing/views.py:831-833](warehousing/views.py#L831-L833)) |

### 4.13 No audit log on destructive ops (X-17)

| | |
|---|---|
| **ID** | TC-WH-SEC-030 |
| **Description** | Deleting a warehouse / transitioning a cross-dock order should write a `core.AuditLog` row |
| **Pre-conditions** | `core.AuditLog` model exists ([core/models.py:197](core/models.py#L197)) |
| **Steps** | Delete warehouse → assert `AuditLog.objects.filter(...)` has row |
| **Expected** | 1 row with actor, entity, action, tenant |
| **Current behaviour** | **FAILS** — no `AuditLog` writes anywhere in `warehousing/`. |

### 4.14 N+1 guard (B-13)

| | |
|---|---|
| **ID** | TC-WH-PERF-001 |
| **Description** | Bin list with 200 bins must execute ≤ 10 queries |
| **Pre-conditions** | 200 bins (mix of floor + rack) |
| **Steps** | GET `/warehousing/bins/?page=1` inside `django_assert_max_num_queries(10)` |
| **Expected** | Passes |
| **Current behaviour** | Expected green: view uses `.select_related('zone', 'zone__warehouse', 'rack')`. `Bin.utilization_percentage` is pure-python on already-fetched fields. Test needed to lock in. |

### 4.15 Warehouse map totals (M-02)

| | |
|---|---|
| **ID** | TC-WH-MAP-001 |
| **Description** | `/warehousing/<pk>/map/` shows correct total/occupied/available counts |
| **Pre-conditions** | Warehouse with 10 bins, 3 occupied |
| **Steps** | GET map URL |
| **Expected** | `total_bins=10`, `occupied_bins=3`, `available_bins=7` |
| **Current behaviour** | Correct — view computes via separate COUNT queries ([warehousing/views.py:144-152](warehousing/views.py#L144-L152)) |

### 4.16 Anonymous access (WH-10)

| | |
|---|---|
| **ID** | TC-WH-SEC-020 |
| **Description** | All 35 URLs must 302 to login for anon users |
| **Pre-conditions** | Fresh client |
| **Steps** | Parametrise GET over every URL name |
| **Expected** | 302 with `next=` param |
| **Current behaviour** | Correct — every view has `@login_required` |

### 4.17 XSS in warehouse name (SEC-011)

| | |
|---|---|
| **ID** | TC-WH-SEC-011 |
| **Description** | Warehouse.name containing `<script>alert(1)</script>` renders escaped on list |
| **Pre-conditions** | Warehouse with that name |
| **Steps** | GET list → inspect response body |
| **Expected** | `&lt;script&gt;...&lt;/script&gt;` |
| **Current behaviour** | Correct (Django auto-escape) — covered by regression test. |

### 4.18 Concurrent code generation (WH-13)

| | |
|---|---|
| **ID** | TC-WH-CON-001 |
| **Description** | Two parallel `Warehouse.objects.create(tenant=t)` calls must not produce duplicate `WH-00001` |
| **Pre-conditions** | Empty warehouse table for tenant |
| **Steps** | Launch 2 threads calling `.create()` simultaneously |
| **Expected** | Both succeed with distinct codes |
| **Current behaviour** | **RACE CANDIDATE** — `_generate_code` reads max outside a transaction; second write raises IntegrityError. |

### 4.19 Reopen resets timestamps (X-03)

| | |
|---|---|
| **ID** | TC-WH-CD-004 |
| **Description** | Reopening a cancelled order clears `actual_arrival` and `actual_departure` |
| **Pre-conditions** | Cancelled order with timestamps set |
| **Steps** | POST `/warehousing/cross-docking/<pk>/reopen/` |
| **Expected** | `status='pending'`, both `actual_*` fields None |
| **Current behaviour** | Correct ([warehousing/views.py:862-865](warehousing/views.py#L862-L865)) |

### 4.20 Seed idempotency (S-02)

| | |
|---|---|
| **ID** | TC-WH-SEED-001 |
| **Description** | Running `seed_warehousing` twice without `--flush` is a no-op for already-seeded tenants |
| **Pre-conditions** | Tenant already seeded |
| **Steps** | `python manage.py seed_warehousing` |
| **Expected** | Stdout "Warehousing data already exists" — no new rows |
| **Current behaviour** | Correct ([warehousing/management/commands/seed_warehousing.py:56-58](warehousing/management/commands/seed_warehousing.py#L56-L58)) |

---

## 5. Automation Strategy

### 5.1 Tool stack

- **pytest 8.x + pytest-django 4.x** — unit + integration
- **factory-boy / model_bakery** — fixture generation (aligned with catalog/vendors patterns)
- **Playwright (python)** — E2E smoke on the CRUD hierarchy
- **Locust** — load test on `warehouse_map` and `bin_list` with 1000 bins
- **bandit** — static security scan on `warehousing/`
- **OWASP ZAP** (baseline) — dynamic AuthN/Z pass
- Existing [pytest.ini](pytest.ini) already points to `config.settings_test`; update `testpaths` to include `warehousing/tests`.

### 5.2 Suite layout

```
warehousing/tests/
├── __init__.py
├── conftest.py                  # tenant, user, warehouse, zone, bin fixtures
├── test_models.py               # unit — properties, transitions, auto-codes
├── test_forms.py                # validation (incl. D-01..D-04 guards once fixed)
├── test_views_warehouse.py      # CRUD + IDOR + filters
├── test_views_zone.py
├── test_views_aisle.py
├── test_views_rack.py
├── test_views_bin.py
├── test_views_crossdock.py      # state machine + formset
├── test_templates.py            # badge rendering, filter retention
├── test_security.py             # OWASP A01/A03/A04/A09
├── test_performance.py          # N+1 guards
└── test_seed.py                 # idempotency
```

And append `warehousing/tests` to `testpaths` in [pytest.ini](pytest.ini#L5).

### 5.3 `conftest.py` — reusable fixtures (runnable against current codebase)

```python
# warehousing/tests/conftest.py
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

from core.models import Tenant
from warehousing.models import (
    Warehouse, Zone, Aisle, Rack, Bin, CrossDockOrder,
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
        username="qa_user",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="qa_other",
        password="qa_pass_123!",
        tenant=other_tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(tenant=tenant, name="Main DC")  # auto code


@pytest.fixture
def zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse,
        name="Storage", code="Z-STR-01", zone_type="storage",
    )


@pytest.fixture
def aisle(db, tenant, zone):
    return Aisle.objects.create(
        tenant=tenant, zone=zone, name="Aisle 1", code="A-01",
    )


@pytest.fixture
def rack(db, tenant, aisle):
    return Rack.objects.create(
        tenant=tenant, aisle=aisle, name="Rack 1", code="R-01-01",
        levels=4, max_weight_capacity=Decimal("500.00"),
    )


@pytest.fixture
def bin_fixture(db, tenant, zone, rack):
    return Bin.objects.create(
        tenant=tenant, zone=zone, rack=rack,
        name="Bin 1", code="BIN-01-01-01",
        bin_type="standard",
        max_weight=Decimal("100.00"),
        max_volume=Decimal("2.50"),
        max_quantity=50,
    )


@pytest.fixture
def crossdock(db, tenant, user):
    return CrossDockOrder.objects.create(
        tenant=tenant, source="Vendor A", destination="Store 1",
        created_by=user,
    )
```

### 5.4 `test_models.py` — unit

```python
import pytest
from decimal import Decimal
from warehousing.models import Warehouse, Bin


@pytest.mark.django_db
class TestWarehouseModel:
    def test_auto_code_first(self, tenant):
        w = Warehouse.objects.create(tenant=tenant, name="A")
        assert w.code == "WH-00001"

    def test_auto_code_increments(self, tenant):
        Warehouse.objects.create(tenant=tenant, name="A")
        w2 = Warehouse.objects.create(tenant=tenant, name="B")
        assert w2.code == "WH-00002"

    def test_auto_code_is_per_tenant(self, tenant, other_tenant):
        Warehouse.objects.create(tenant=tenant, name="A")
        w = Warehouse.objects.create(tenant=other_tenant, name="B")
        assert w.code == "WH-00001"


@pytest.mark.django_db
class TestBinProperties:
    def test_utilization_percentage(self, bin_fixture):
        bin_fixture.current_weight = Decimal("50.00")
        bin_fixture.current_volume = Decimal("1.25")
        bin_fixture.current_quantity = 25
        bin_fixture.save()
        assert bin_fixture.utilization_percentage == 50.0

    def test_utilization_zero_caps(self, tenant, zone):
        b = Bin.objects.create(
            tenant=tenant, zone=zone, name="Empty", code="BIN-EMPTY",
            bin_type="standard",
        )
        assert b.utilization_percentage == 0

    def test_available_weight_clamps_negative(self, bin_fixture):
        bin_fixture.current_weight = Decimal("200.00")
        assert bin_fixture.available_weight == 0

    def test_location_path_with_rack(self, bin_fixture):
        assert bin_fixture.location_path.startswith(bin_fixture.zone.warehouse.code)
        assert bin_fixture.code in bin_fixture.location_path

    def test_location_path_floor_bin(self, tenant, zone):
        b = Bin.objects.create(
            tenant=tenant, zone=zone, name="Floor", code="BIN-FLR",
            bin_type="pallet",
        )
        assert "R-" not in b.location_path


TRANSITIONS_OK = [
    ("pending", "in_transit"),
    ("pending", "cancelled"),
    ("in_transit", "at_dock"),
    ("at_dock", "processing"),
    ("processing", "dispatched"),
    ("dispatched", "completed"),
    ("cancelled", "pending"),
]
TRANSITIONS_BAD = [
    ("pending", "completed"),
    ("pending", "at_dock"),
    ("completed", "pending"),
    ("completed", "cancelled"),
    ("dispatched", "cancelled"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", TRANSITIONS_OK)
def test_transition_allowed(crossdock, src, dst):
    crossdock.status = src
    assert crossdock.can_transition_to(dst)


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", TRANSITIONS_BAD)
def test_transition_denied(crossdock, src, dst):
    crossdock.status = src
    assert not crossdock.can_transition_to(dst)
```

### 5.5 `test_forms.py` — validation (highlights D-01..D-04 gaps)

```python
import pytest
from warehousing.forms import ZoneForm, BinForm
from warehousing.models import Zone, Warehouse


@pytest.mark.django_db
class TestZoneFormUniqueness:
    def test_duplicate_code_in_tenant_rejected(self, tenant, warehouse):
        """D-01 — currently FAILS; acceptance criterion for remediation."""
        Zone.objects.create(
            tenant=tenant, warehouse=warehouse,
            name="First", code="Z-DUP", zone_type="storage",
        )
        form = ZoneForm(data={
            "warehouse": warehouse.pk,
            "name": "Dup", "code": "Z-DUP", "zone_type": "storage",
            "temperature_controlled": False, "is_active": True,
            "description": "",
        }, tenant=tenant)
        assert not form.is_valid()
        assert "code" in form.errors

    def test_same_code_in_other_tenant_allowed(
        self, tenant, other_tenant, warehouse
    ):
        Zone.objects.create(
            tenant=tenant, warehouse=warehouse,
            name="T1", code="Z-SHARED", zone_type="storage",
        )
        other_wh = Warehouse.objects.create(tenant=other_tenant, name="Other WH")
        form = ZoneForm(data={
            "warehouse": other_wh.pk, "name": "T2", "code": "Z-SHARED",
            "zone_type": "storage", "temperature_controlled": False,
            "is_active": True, "description": "",
        }, tenant=other_tenant)
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestZoneFormTemperature:
    def test_temp_min_gt_max_rejected(self, tenant, warehouse):
        """D-02 — currently FAILS."""
        form = ZoneForm(data={
            "warehouse": warehouse.pk, "name": "Inv", "code": "Z-INV",
            "zone_type": "storage", "temperature_controlled": True,
            "temperature_min": "50", "temperature_max": "-10",
            "is_active": True, "description": "",
        }, tenant=tenant)
        assert not form.is_valid()


@pytest.mark.django_db
class TestBinFormIntegrity:
    def test_negative_max_weight_rejected(self, tenant, zone):
        """D-03 — currently FAILS."""
        form = BinForm(data={
            "zone": zone.pk, "rack": "", "name": "Neg", "code": "BIN-NEG",
            "bin_type": "standard",
            "max_weight": "-100", "max_volume": "1", "max_quantity": 10,
            "is_active": True,
        }, tenant=tenant)
        assert not form.is_valid()

    def test_rack_zone_mismatch_rejected(self, tenant, warehouse, rack):
        """D-04 — currently FAILS."""
        other_zone = Zone.objects.create(
            tenant=tenant, warehouse=warehouse,
            name="Other", code="Z-OTHER", zone_type="storage",
        )
        form = BinForm(data={
            "zone": other_zone.pk, "rack": rack.pk,
            "name": "Mix", "code": "BIN-MIX",
            "bin_type": "standard",
            "max_weight": "10", "max_volume": "1", "max_quantity": 1,
            "is_active": True,
        }, tenant=tenant)
        assert not form.is_valid()
```

### 5.6 `test_views_warehouse.py` — integration + IDOR

```python
import pytest
from django.urls import reverse
from warehousing.models import Warehouse


@pytest.mark.django_db
class TestWarehouseViews:
    def test_login_required(self, client):
        r = client.get(reverse("warehousing:warehouse_list"))
        assert r.status_code == 302
        assert "/login" in r.url or "next=" in r.url

    def test_list_filters_type(self, client_logged_in, tenant):
        Warehouse.objects.create(tenant=tenant, name="DC", warehouse_type="distribution_center")
        Warehouse.objects.create(tenant=tenant, name="Cold", warehouse_type="cold_storage")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list") + "?type=cold_storage"
        )
        assert b"Cold" in r.content
        assert b"DC" not in r.content

    def test_list_filter_retention_in_pagination(self, client_logged_in, tenant):
        for i in range(25):
            Warehouse.objects.create(
                tenant=tenant, name=f"W{i}", warehouse_type="distribution_center"
            )
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list")
            + "?type=distribution_center&active=active&page=2"
        )
        assert r.status_code == 200
        assert b"type=distribution_center" in r.content
        assert b"active=active" in r.content

    def test_idor_cross_tenant_detail(self, client_logged_in, other_tenant):
        b_wh = Warehouse.objects.create(tenant=other_tenant, name="Hidden")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_detail", args=[b_wh.pk])
        )
        assert r.status_code == 404

    def test_delete_non_empty_blocked(self, client_logged_in, warehouse, zone):
        r = client_logged_in.post(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk]),
            follow=True,
        )
        assert Warehouse.objects.filter(pk=warehouse.pk).exists()
        assert b"Cannot delete" in r.content

    def test_delete_empty_succeeds(self, client_logged_in, warehouse):
        r = client_logged_in.post(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk])
        )
        assert r.status_code == 302
        assert not Warehouse.objects.filter(pk=warehouse.pk).exists()

    def test_post_only_on_delete(self, client_logged_in, warehouse):
        r = client_logged_in.get(
            reverse("warehousing:warehouse_delete", args=[warehouse.pk])
        )
        assert r.status_code == 302  # redirect, no delete
        assert Warehouse.objects.filter(pk=warehouse.pk).exists()
```

### 5.7 `test_views_crossdock.py` — state machine via HTTP

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestCrossDockStatus:
    def test_valid_transition_pending_to_in_transit(
        self, client_logged_in, crossdock
    ):
        r = client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "in_transit"},
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "in_transit"
        assert r.status_code == 302

    def test_invalid_transition_ignored(self, client_logged_in, crossdock):
        client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "completed"},
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "pending"  # unchanged

    def test_at_dock_auto_sets_arrival(self, client_logged_in, crossdock):
        crossdock.status = "in_transit"
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_status", args=[crossdock.pk]),
            {"new_status": "at_dock"},
        )
        crossdock.refresh_from_db()
        assert crossdock.actual_arrival is not None

    def test_reopen_clears_timestamps(self, client_logged_in, crossdock):
        from django.utils import timezone
        crossdock.status = "cancelled"
        crossdock.actual_arrival = timezone.now()
        crossdock.actual_departure = timezone.now()
        crossdock.save()
        client_logged_in.post(
            reverse("warehousing:crossdock_reopen", args=[crossdock.pk]),
        )
        crossdock.refresh_from_db()
        assert crossdock.status == "pending"
        assert crossdock.actual_arrival is None
        assert crossdock.actual_departure is None

    def test_edit_locked_post_pending(self, client_logged_in, crossdock):
        crossdock.status = "in_transit"
        crossdock.save()
        r = client_logged_in.get(
            reverse("warehousing:crossdock_edit", args=[crossdock.pk]),
        )
        assert r.status_code == 302
```

### 5.8 `test_security.py` — OWASP A01/A03/A04/A09

```python
import pytest
from django.urls import reverse
from warehousing.models import Warehouse


@pytest.mark.django_db
class TestWarehousingSecurity:
    def test_xss_in_warehouse_name_escaped(self, client_logged_in, tenant):
        Warehouse.objects.create(
            tenant=tenant, name="<script>alert(1)</script>"
        )
        r = client_logged_in.get(reverse("warehousing:warehouse_list"))
        assert b"<script>alert" not in r.content
        assert b"&lt;script&gt;alert" in r.content

    def test_sql_injection_on_search_safe(self, client_logged_in, tenant):
        Warehouse.objects.create(tenant=tenant, name="Legit")
        r = client_logged_in.get(
            reverse("warehousing:warehouse_list") + "?q=' OR 1=1 --"
        )
        assert r.status_code == 200  # no 500 from ORM

    def test_cross_tenant_list_isolation(self, client_logged_in, other_tenant):
        Warehouse.objects.create(tenant=other_tenant, name="Secret")
        r = client_logged_in.get(reverse("warehousing:warehouse_list"))
        assert b"Secret" not in r.content

    def test_superuser_tenant_none_sees_empty(
        self, client, django_user_model, tenant
    ):
        Warehouse.objects.create(tenant=tenant, name="Owned")
        su = django_user_model.objects.create_superuser(
            username="root", password="x", email="r@r.com"
        )
        client.force_login(su)
        r = client.get(reverse("warehousing:warehouse_list"))
        assert b"Owned" not in r.content  # middleware sets tenant=None


@pytest.mark.django_db
def test_audit_log_on_warehouse_delete(client_logged_in, warehouse):
    """D-06 — currently FAILS; acceptance criterion."""
    from core.models import AuditLog
    client_logged_in.post(
        reverse("warehousing:warehouse_delete", args=[warehouse.pk]),
    )
    assert AuditLog.objects.filter(action__icontains="delete").exists()
```

### 5.9 `test_performance.py` — N+1 guards

```python
import pytest
from decimal import Decimal
from django.urls import reverse
from warehousing.models import Warehouse, Zone, Bin


@pytest.mark.django_db
class TestPerformance:
    def test_bin_list_no_n_plus_one(
        self, client_logged_in, tenant, django_assert_max_num_queries
    ):
        wh = Warehouse.objects.create(tenant=tenant, name="A")
        z = Zone.objects.create(
            tenant=tenant, warehouse=wh, name="Z", code="Z-1",
            zone_type="storage",
        )
        for i in range(50):
            Bin.objects.create(
                tenant=tenant, zone=z, name=f"B{i}", code=f"BIN-{i:04d}",
                bin_type="standard",
                max_weight=Decimal("100"), max_volume=Decimal("1"),
                max_quantity=10,
            )
        with django_assert_max_num_queries(10):
            r = client_logged_in.get(reverse("warehousing:bin_list"))
        assert r.status_code == 200

    def test_warehouse_map_query_budget(
        self, client_logged_in, warehouse, django_assert_max_num_queries
    ):
        with django_assert_max_num_queries(15):
            r = client_logged_in.get(
                reverse("warehousing:warehouse_map", args=[warehouse.pk])
            )
        assert r.status_code == 200
```

### 5.10 Playwright E2E smoke (optional)

```python
# warehousing/tests/e2e/test_hierarchy.py
import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_create_full_hierarchy(page, live_server):
    page.goto(f"{live_server.url}/login/")
    page.fill("[name=username]", "admin_acme")
    page.fill("[name=password]", "demo123")
    page.click("button[type=submit]")
    page.goto(f"{live_server.url}/warehousing/create/")
    page.fill("[name=name]", "E2E DC")
    page.click("button[type=submit]")
    expect(page.locator("text=E2E DC")).to_be_visible()
    # ... zone → aisle → rack → bin
```

### 5.11 Locust load test

```python
# warehousing/tests/locustfile.py
from locust import HttpUser, task, between


class WarehouseBrowser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post(
            "/login/",
            {"username": "admin_acme", "password": "demo123"},
        )

    @task(3)
    def bin_list(self):
        self.client.get("/warehousing/bins/?page=1")

    @task(1)
    def warehouse_map(self):
        self.client.get("/warehousing/1/map/")
```

### 5.12 Updating pytest.ini

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings_test
python_files = tests.py test_*.py *_tests.py
addopts = -ra -q --strict-markers
testpaths = catalog/tests vendors/tests warehousing/tests
filterwarnings =
    ignore::DeprecationWarning
```

---

## 6. Defects, Risks & Recommendations

### 6.1 Defect register

| ID | Severity | OWASP | Location | Finding | Recommendation |
|---|---|---|---|---|---|
| **D-01** | **High** | A04 Insecure design | [warehousing/forms.py:82](warehousing/forms.py#L82) (Zone), [:144](warehousing/forms.py#L144) (Aisle), [:182](warehousing/forms.py#L182) (Rack), [:231](warehousing/forms.py#L231) (Bin) | `unique_together=('tenant','code')` not enforced at form level. Because `tenant` is not a form field, `validate_unique()` excludes it — duplicate codes reach DB → `IntegrityError`, 500 response. **Verified 2026-04-17.** | Add `clean_code()` in each ModelForm: `if qs.filter(tenant=self.tenant, code=code).exclude(pk=self.instance.pk).exists(): raise ValidationError("Code already exists for this tenant.")` |
| **D-02** | Medium | A04 | [warehousing/forms.py:82](warehousing/forms.py#L82) (ZoneForm) | No validation that `temperature_min <= temperature_max`. Silently allows inverted ranges, making downstream temperature checks meaningless. **Verified 2026-04-17.** | Add `clean()` to `ZoneForm`: raise `ValidationError` when `temperature_controlled=True and (min is None or max is None or min > max)`. |
| **D-03** | Medium | A04 | [warehousing/forms.py:231](warehousing/forms.py#L231) (BinForm), [warehousing/models.py:221-231](warehousing/models.py#L221-L231) | No server-side validator for `max_weight >= 0`, `max_volume >= 0`. HTML `min='0'` is client-side only. `DecimalField(default=0)` has no `MinValueValidator`. **Verified 2026-04-17.** | Add `MinValueValidator(Decimal('0'))` to model fields; mirror `clean_*` in form. Same fix applies to `Rack.max_weight_capacity`. |
| **D-04** | High | A04 | [warehousing/forms.py:273-286](warehousing/forms.py#L273-L286) | `BinForm` accepts any `(zone, rack)` pair. When `rack.aisle.zone != zone`, `Bin.location_path` emits an incoherent trail; reporting against zones becomes inconsistent. **Verified 2026-04-17.** | Add `clean()` to `BinForm`: `if rack and rack.aisle.zone_id != zone.id: raise ValidationError({"rack": "Rack must belong to the selected zone"})`. |
| **D-05** | Medium | A04 | [templates/warehousing/bin_list.html:126-138](templates/warehousing/bin_list.html#L126-L138) | Badge mapping checks `picking`, `reserve`, `staging`, `receiving`, `shipping` — none of which are in `Bin.BIN_TYPE_CHOICES` (`standard`, `bulk`, `pick`, `pallet`, `cold`, `hazmat`). Five branches are dead code; only `bulk` matches; the rest render a generic grey badge. **Confirmed by model-template diff.** | Rewrite branches to match actual choices: `{% if bin.bin_type == 'standard' %}`...`{% elif bin.bin_type == 'pick' %}`...etc. Prefer a template filter or dict lookup — one source of truth. |
| **D-06** | Medium | A09 Logging failures | [warehousing/views.py](warehousing/views.py) entire file | No `core.AuditLog` entries written for: warehouse/zone/aisle/rack/bin/cross-dock deletes, cross-dock status transitions, reopen. `AuditLog` model exists at [core/models.py:197](core/models.py#L197) but is unused here. | Emit `AuditLog.objects.create(tenant=..., actor=request.user, entity_type='warehouse', entity_id=pk, action='delete', payload={...})` in every delete view and every `crossdock_status` / `crossdock_reopen` success path. |
| **D-07** | Medium | A01 Broken access control | [warehousing/views.py](warehousing/views.py) all views | Only `@login_required`. No role/permission check — any logged-in user of a tenant can delete any warehouse, cancel any cross-dock order, reopen, etc. | Introduce a decorator `@require_tenant_admin` (or Django permission) and apply to delete + status-transition views. Non-admin tenant users should have read-only access. |
| **D-08** | Low | A04 | [warehousing/models.py:57-71](warehousing/models.py#L57-L71), [:357-371](warehousing/models.py#L357-L371) | `_generate_code` / `_generate_order_number` read-max-then-write without a lock. Two concurrent creates will produce duplicate codes and the second save will raise `IntegrityError`. | Wrap generation in `transaction.atomic()` with `select_for_update()` on the tenant row, or use a dedicated sequence. Alternatively, catch `IntegrityError` and retry. |
| **D-09** | Low | A04 | [warehousing/models.py:392-395](warehousing/models.py#L392-L395) | `CrossDockItem.quantity` is `PositiveIntegerField(default=1)` — allows 0. | Add `MinValueValidator(1)` or `CheckConstraint(quantity__gte=1)`. |
| **D-10** | Low | A04 | [warehousing/forms.py:296-331](warehousing/forms.py#L296-L331) | `CrossDockOrderForm` does not validate `scheduled_arrival <= scheduled_departure`. Allows nonsensical timelines. | Add cross-field `clean()` check. |
| **D-11** | Low | A04 | [warehousing/views.py:631](warehousing/views.py#L631) | Deletion guard uses only `bin.is_occupied`. `is_occupied` is a manually-managed flag — if `current_quantity > 0` but `is_occupied=False`, deletion passes and inventory is silently lost. | Also refuse delete when `current_quantity > 0 or current_weight > 0 or current_volume > 0`. Better still: derive `is_occupied` as a `@property` from current_* fields. |
| **D-12** | Info | A04 | [warehousing/models.py:145](warehousing/models.py#L145) (Aisle), [:180](warehousing/models.py#L180) (Rack) | No FK pruning validator: an aisle can be moved to a zone in a different warehouse via edit (and similarly rack → aisle, bin → rack/zone). | On each form `clean()`, enforce parent warehouse/zone consistency. |
| **D-13** | Info | — | [warehousing/tests.py](warehousing/tests.py) | Module ships with zero automated test coverage. | Implement suite per §5. |
| **D-14** | Info | A03 | [templates/warehousing/warehouse_list.html:151](templates/warehousing/warehouse_list.html#L151) and peers | Pagination links concatenate GET params without `urlencode`. Current filter values are controlled by server, so low risk, but brittle under future arbitrary filter inputs. | Use `{% querystring %}` tag (Django 5.1+) or a custom `url_replace` filter. |
| **D-15** | Info | — | [warehousing/views.py:693](warehousing/views.py#L693) | `formset.save(commit=False)` then manually setting `item.tenant = tenant` and `item.save()` — deleted items are iterated via `formset.deleted_objects` after `.save(commit=False)`. Works today, but fragile. | Prefer: set `formset.instance = order`, iterate `formset.save(commit=False)`, set tenant, then `formset.save_m2m()` — plus explicit loop over `formset.deleted_forms`. |

### 6.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Duplicate-code 500s shown to users | High (every daily use) | Medium (trust, not data loss) | Fix D-01 urgently |
| Inconsistent capacity / temperature data propagates to downstream reports | Medium | Medium | Fix D-02, D-03 |
| Zone/rack mismatched bins break put-away logic | Medium | High | Fix D-04 |
| Bin type drift silently loses visual differentiation | Medium | Low | Fix D-05 |
| Auditability gap during security incident | Low | High (compliance) | Fix D-06 |
| Any tenant user can destroy tenant-level data | Medium | High | Fix D-07 |
| Concurrent create produces 500 under load | Low today | Medium | Fix D-08 when multi-user becomes routine |

### 6.3 Recommendations (priority order)

1. **Fix D-01** — Add `clean_code()` to `ZoneForm`, `AisleForm`, `RackForm`, `BinForm`. One-line reusable mixin.
2. **Fix D-05** — Rewrite bin_list badge block to match actual choices. 30-minute change.
3. **Fix D-04** — Cross-field validator in `BinForm.clean()`.
4. **Fix D-02 + D-03 + D-09 + D-10** — Numeric / temporal validators. Adds 6-8 small `clean*()` methods.
5. **Fix D-07** — Introduce `require_tenant_admin` decorator; apply to destructive views. Align with the rest of the app.
6. **Fix D-06** — Audit-log helper + call sites.
7. **Fix D-11** — Occupancy check on delete.
8. **Fix D-08** — Wrap code-generation in `transaction.atomic()` + retry.
9. **Fix D-13** — Implement automation suite from §5.
10. **D-12, D-14, D-15** — Cleanups during next touch.

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Target coverage

| File | Current | Target |
|---|---|---|
| [warehousing/models.py](warehousing/models.py) | 0% | ≥ 90% line, ≥ 85% branch |
| [warehousing/forms.py](warehousing/forms.py) | 0% | ≥ 95% line (after D-01..D-04 fixes) |
| [warehousing/views.py](warehousing/views.py) | 0% | ≥ 85% line (incl. all redirect branches) |
| [warehousing/management/commands/seed_warehousing.py](warehousing/management/commands/seed_warehousing.py) | 0% | ≥ 70% (happy path + idempotency) |
| Templates (bin_list, warehouse_list, crossdock_detail) | n/a | Snapshot / filter-retention tests |
| Mutation score | — | ≥ 70% on models/forms |

### 7.2 KPI dashboard

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | 100% | 95-99% | <95% |
| Open High/Critical defects | 0 | 1 | ≥2 |
| Open Medium defects | ≤3 | 4-6 | ≥7 |
| Suite runtime (unit + integration) | <20s | 20-60s | >60s |
| p95 latency — `bin_list?page=1` (200 bins) | <300 ms | 300-800 ms | >800 ms |
| Query count — `bin_list` list view | ≤10 | 11-15 | >15 |
| Query count — `warehouse_map` with 500 bins | ≤15 | 16-25 | >25 |
| Regression escape rate (defects found in prod / sprint) | 0 | 1 | ≥2 |
| Audit-log coverage on destructive ops | 100% | 80-99% | <80% |
| Security scan (bandit HIGH) | 0 | 0 | ≥1 |

### 7.3 Release Exit Gate

A release MUST satisfy **all** of the following to ship:

- [ ] D-01, D-04, D-05, D-07 are fixed (High/Med architectural defects).
- [ ] `warehousing/tests/` has ≥ 60 passing tests (per §5).
- [ ] Line coverage ≥ 85% on `warehousing/` per §7.1.
- [ ] No failing test in the full suite; no `xfail` in security or form-integrity files.
- [ ] `bandit -r warehousing/` returns zero High findings.
- [ ] N+1 guards (`test_bin_list_no_n_plus_one`, `warehouse_map_query_budget`) green.
- [ ] Manual smoke: create full hierarchy → map view → cross-dock round-trip passes.
- [ ] Seed idempotency verified on a tenant with existing data.
- [ ] `AuditLog` row emitted on ≥ 1 delete and ≥ 1 cross-dock transition (D-06).

---

## 8. Summary

The Warehousing & Bin Management module is **functionally complete** — the full `Warehouse → Zone → Aisle → Rack → Bin` hierarchy, a cross-dock workflow with an explicit state machine, and CRUD views with correct tenant scoping, IDOR guards, and filter-retention across pagination are all in place. Auto-code generation, the warehouse map, and the seed command are tenant-safe and idempotent.

However, the module ships with **zero automated test coverage** (D-13) and **four verified data-integrity defects**:

- **D-01 (High)** — `unique_together + tenant` form-validation gap on Zone/Aisle/Rack/Bin codes → `IntegrityError` 500 on any duplicate. This is the recurring NavIMS pattern captured in [.claude/tasks/lessons.md](.claude/tasks/lessons.md) lesson #6 — it has resurfaced here.
- **D-04 (High)** — `BinForm` allows a rack/zone mismatch, breaking put-away semantics and `location_path` reporting.
- **D-05 (Med)** — `bin_list.html` badge mapping is keyed against non-existent choice values; five branches are dead code.
- **D-02, D-03, D-07, D-06** (Medium) — missing temperature-range, non-negative-capacity, RBAC, and audit-log enforcement.

**Next actions (recommended order):**

1. Apply D-01 fix via a reusable `TenantUniqueCodeMixin` on the four affected forms.
2. Fix D-05 (template).
3. Fix D-04 (cross-field validator).
4. Scaffold `warehousing/tests/` with the suite in §5 — new failing tests for D-01..D-04 serve as acceptance criteria; fixes turn them green.
5. Add D-06 audit-log emission + D-07 RBAC in a follow-up PR.

The module otherwise reflects mature multi-tenant discipline; once the defects above are closed and the automation suite is in place, it will meet the Exit Gate in §7.3.

---

### Appendix: Manual verification log (2026-04-17)

| Defect | Reproduction | Observed | File |
|---|---|---|---|
| D-01 | Django shell — ZoneForm with duplicate code within tenant | `form.is_valid() == True`; `form.save()` raises `IntegrityError (1062, ... Duplicate entry '5-Z-DUP-01' for key 'warehousing_zone_tenant_id_code_bb61f847_uniq')` | [warehousing/forms.py:82](warehousing/forms.py#L82) |
| D-02 | ZoneForm `temperature_min=50`, `temperature_max=-10` | `form.is_valid() == True` | [warehousing/forms.py:82](warehousing/forms.py#L82) |
| D-03 | BinForm `max_weight=-100`, `max_volume=-1` | `form.is_valid() == True` | [warehousing/forms.py:231](warehousing/forms.py#L231) |
| D-04 | BinForm zone=Z2 + rack from Z1's aisle | Saves; `location_path` = `WH > Z2 > Z1_aisle > Z1_rack > BIN` | [warehousing/forms.py:231](warehousing/forms.py#L231) |
| D-05 | Diff `BIN_TYPE_CHOICES` ([warehousing/models.py:191-198](warehousing/models.py#L191-L198)) vs template ([templates/warehousing/bin_list.html:126-138](templates/warehousing/bin_list.html#L126-L138)) | 5 branches unreachable; 1 match (bulk) | — |
| D-06 | `grep AuditLog warehousing/` | 0 hits | — |
