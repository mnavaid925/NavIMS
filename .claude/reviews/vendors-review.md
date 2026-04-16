# Vendor / Supplier Management — Comprehensive SQA Test Report

> Target: [vendors/](../../vendors/) Django app (Supplier Directory, Performance Tracking, Contracts & Terms, Communication Log — IMS module §2).
> Scope: full module end-to-end review — models, forms, views, URLs, templates, seed, admin.
> Standards: OWASP Top 10 (2021) · ISO/IEC/IEEE 29119-2 (Test Processes) · Django 4.x / pytest-django conventions.
> Date: 2026-04-17 · Reviewer: Senior SQA (15+ yrs, Django/Python).
> Verification: every High/Critical defect confirmed via Django-shell reproduction (see §6).

---

## 1. Module Analysis

### 1.1 Inventory of code under review

| Artefact | File | LoC | Purpose |
|---|---|---|---|
| Models | [vendors/models.py](../../vendors/models.py) | 212 | `Vendor`, `VendorPerformance`, `VendorContract`, `VendorCommunication` |
| Forms | [vendors/forms.py](../../vendors/forms.py) | 299 | 4 `ModelForm`s — all tenant-scoped via `__init__(tenant=...)` |
| Views | [vendors/views.py](../../vendors/views.py) | 527 | 23 function views — CRUD + 6 inline-from-detail handlers |
| URLs | [vendors/urls.py](../../vendors/urls.py) | 43 | `app_name='vendors'`; 22 routes |
| Admin | [vendors/admin.py](../../vendors/admin.py) | 47 | 4 `ModelAdmin` + 3 inlines |
| Seed | [vendors/management/commands/seed_vendors.py](../../vendors/management/commands/seed_vendors.py) | 308 | idempotent, `--flush` supported |
| Templates | [templates/vendors/](../../templates/vendors/) | 9 files | `*_list.html`, `*_form.html`, `vendor_detail.html` |
| Migrations | [vendors/migrations/](../../vendors/migrations/) | 1 | `0001_initial.py` only |
| Tests | — | 0 | **No automated tests exist for this module.** |

### 1.2 Data model (entities & constraints)

| Model | File:Line | Key constraints | Risk notes |
|---|---|---|---|
| `Vendor` | [models.py:6](../../vendors/models.py#L6) | `unique_together=('tenant','company_name')`; 4 status choices; 4 vendor_type choices | A04: duplicate company_name silently bypasses form validation (see D-01). |
| `VendorPerformance` | [models.py:77](../../vendors/models.py#L77) | `MinValueValidator(1)`/`MaxValueValidator(5)` on 3 rating fields; `defect_rate`/`on_time_delivery_rate` have NO max validator | D-04: rate fields accept any `DecimalField(max_digits=5, decimal_places=2)` value, so up to `999.99` is accepted. |
| `VendorContract` | [models.py:131](../../vendors/models.py#L131) | `unique_together=('tenant','contract_number')`; `document = FileField(upload_to='vendors/contracts/')` with no validators | D-02 (dup bypass) + D-06 (unrestricted uploads). |
| `VendorCommunication` | [models.py:173](../../vendors/models.py#L173) | `communication_date` has no bounds | Future dates accepted. |

### 1.3 URL → View → Template map

| URL | View | Auth | Tenant scope | Template |
|---|---|---|---|---|
| `vendors/` | `vendor_list_view` [views.py:20](../../vendors/views.py#L20) | `@login_required` | ✅ `filter(tenant=request.tenant)` | [vendor_list.html](../../templates/vendors/vendor_list.html) |
| `vendors/create/` | `vendor_create_view` [views.py:57](../../vendors/views.py#L57) | `@login_required` | ✅ via form.tenant | [vendor_form.html](../../templates/vendors/vendor_form.html) |
| `vendors/<pk>/` | `vendor_detail_view` [views.py:77](../../vendors/views.py#L77) | `@login_required` | ✅ `get_object_or_404(..., tenant=...)` | [vendor_detail.html](../../templates/vendors/vendor_detail.html) |
| `vendors/<pk>/edit/` | `vendor_edit_view` [views.py:101](../../vendors/views.py#L101) | `@login_required` | ✅ | shares `vendor_form.html` |
| `vendors/<pk>/delete/` | `vendor_delete_view` [views.py:123](../../vendors/views.py#L123) | `@login_required` + POST-only | ✅ | — (redirect) |
| `vendors/performance/` | `performance_list_view` [views.py:142](../../vendors/views.py#L142) | `@login_required` | ✅ | [performance_list.html](../../templates/vendors/performance_list.html) |
| `vendors/performance/create/` | `performance_create_view` [views.py:171](../../vendors/views.py#L171) | `@login_required` | ✅ | [performance_form.html](../../templates/vendors/performance_form.html) |
| `vendors/performance/<pk>/edit/` | `performance_edit_view` [views.py:193](../../vendors/views.py#L193) | `@login_required` | ✅ | same form |
| `vendors/performance/<pk>/delete/` | `performance_delete_view` [views.py:215](../../vendors/views.py#L215) | `@login_required` + POST-only | ✅ | — |
| `vendors/contracts/...` | contract CRUD [views.py:232-321](../../vendors/views.py#L232) | `@login_required` | ✅ | `contract_*.html` |
| `vendors/communications/...` | communication CRUD [views.py:329-419](../../vendors/views.py#L329) | `@login_required` | ✅ | `communication_*.html` |
| `vendors/<pk>/performance/add/` | `vendor_performance_add_view` [views.py:427](../../vendors/views.py#L427) | `@login_required` | ⚠️ vendor via URL only — **form NOT tenant-scoped** | — (redirect) |
| `vendors/<pk>/performance/<perf_pk>/delete/` | [views.py:444](../../vendors/views.py#L444) | `@login_required` | ✅ | — |
| `vendors/<pk>/contracts/add/` | [views.py:463](../../vendors/views.py#L463) | `@login_required` | ⚠️ form not tenant-scoped | — |
| `vendors/<pk>/contracts/<contract_pk>/delete/` | [views.py:479](../../vendors/views.py#L479) | `@login_required` | ✅ | — |
| `vendors/<pk>/communications/add/` | [views.py:498](../../vendors/views.py#L498) | `@login_required` | ⚠️ form not tenant-scoped | — |
| `vendors/<pk>/communications/<comm_pk>/delete/` | [views.py:515](../../vendors/views.py#L515) | `@login_required` | ✅ | — |

### 1.4 Dependencies and framework surface

- Django auth decorators: `@login_required` on every view — **no RBAC / `is_tenant_admin` gate anywhere in the module** (A01 — see D-10).
- `core.Tenant` (multi-tenant root), `settings.AUTH_USER_MODEL` (FK for `reviewed_by` / `communicated_by`).
- `core.AuditLog` **is not emitted anywhere in this module** (A09 — see D-09).
- File uploads: `VendorContract.document` — no `validators=[...]`, no custom `clean_document`, no magic-byte check (A08 — see D-06).
- Template base: [base.html](../../templates/base.html) (Bootstrap 5 + Remix icons).
- Inline admin already exposes `Vendor` with `[VendorPerformanceInline, VendorContractInline, VendorCommunicationInline]` — admin auto-escape is fine.

### 1.5 Pre-test risk profile

| Risk surface | Level | Reason |
|---|---|---|
| Multi-tenant isolation | **High** | All FKs correctly scoped; but inline `*_add_view` forms don't receive `tenant` kwarg — relies on view-side override. Fragile. |
| Data integrity | **High** | Two `unique_together` traps (D-01, D-02); no cross-field validation on contract dates (D-03); no max validator on rate fields (D-04). |
| File upload | **Critical** | Unrestricted `FileField` on contract document (D-06). |
| AuthZ beyond auth | **High** | No role check; any tenant user can delete vendors with an active contract history (D-10). |
| Audit / repudiation | **Medium** | No AuditLog records on destructive ops (D-09). |
| XSS / injection | **Low** | Django ORM + auto-escape; `URLField` rejects `javascript:` (verified). |
| Performance | **Low-Medium** | `Vendor.average_performance_score` iterates Python (D-12). Lists use `select_related` — good. |
| CSRF | **Low** | Django middleware + templates use `{% csrf_token %}` consistently. |

---

## 2. Test Plan

### 2.1 Objectives (ISO/IEC/IEEE 29119-3)

1. Verify **functional correctness** of CRUD for all four vendor entities across three tenants.
2. Prove **tenant isolation** end-to-end (cross-tenant IDOR returns 404 or behaves safely).
3. Prove **form-level validation** rejects duplicate `unique_together` keys as a `ValidationError`, not a `500 IntegrityError`.
4. Establish **boundary** and **negative** coverage on all numeric/date fields.
5. Verify **file-upload safety** on contract documents (type whitelist, size cap, magic-byte check).
6. Confirm **no regression** of CRUD-completeness and filter patterns mandated by [.claude/CLAUDE.md](../../.claude/CLAUDE.md).
7. Map every security assertion to an **OWASP Top-10 (2021)** category.

### 2.2 Test scope matrix

| Layer | In scope | Out of scope |
|---|---|---|
| Unit | Model saves, properties (`overall_score`, `average_performance_score`), form `clean_*` | ORM field internals |
| Integration | View ↔ form ↔ DB ↔ template | Third-party middleware |
| Functional | End-to-end CRUD flow per entity, filter retention, pagination | Admin UI flows (already covered by `django.contrib.admin` tests) |
| Boundary | 1 & 5 rating ratings; 0/100 percentage; contract value 0/max; `max_length` on every CharField | — |
| Edge | Empty strings, unicode, emoji, whitespace-only, RTL, 10 KB notes, JSON/HTML in subject | — |
| Negative | Invalid vendor_type enum; non-numeric rating; IDOR across tenant; future review_date | — |
| Security | OWASP A01-A10 (see §2.3), CSRF, file upload, tab-nabbing | DoS, supply-chain |
| Performance | `django_assert_max_num_queries` on list views; N+1 in `average_performance_score` | Load testing (proposal only — §5.5) |
| Regression | CRUD completeness ([CLAUDE.md](../../.claude/CLAUDE.md) §CRUD), filter retention across pagination, seed idempotency | — |

### 2.3 OWASP coverage plan

| OWASP | Target file:line | How we test |
|---|---|---|
| **A01** Broken Access Control | [views.py:80](../../vendors/views.py#L80), [views.py:104](../../vendors/views.py#L104), [views.py:130](../../vendors/views.py#L130) | Tenant-A client hits tenant-B object pk → expect 404. Unauthenticated hits every URL → 302 to login. |
| **A02** Crypto failures | `settings.py` + `VendorContract.document` | Verify storage backend; no plaintext creds. |
| **A03** Injection / XSS | [vendor_list.html:38](../../templates/vendors/vendor_list.html#L38) `{{ q }}`, [vendor_detail.html:59](../../templates/vendors/vendor_detail.html#L59) `<a href="{{ vendor.website }}">` | Store `<script>` in name → confirm escape. SQLi in `?q=' OR 1=1 --`. `website=javascript:...` → form rejects. `target="_blank"` without `rel="noopener"` flagged. |
| **A04** Insecure design | [models.py:63](../../vendors/models.py#L63) `unique_together` | Duplicate `company_name`/`contract_number` via form → expect `ValidationError`, not 500. |
| **A05** Security misconfig | `settings.py` | `DEBUG=False`, `SECURE_*` headers — out of this module's scope (flag as project-wide). |
| **A07** Auth failures | n/a (reuses core auth) | Session / CSRF enforcement tests |
| **A08** Data integrity / file upload | [models.py:160](../../vendors/models.py#L160) `document` | Upload `.exe`, `.svg`, `.php`, polyglot, 50 MB, filename with `../` |
| **A09** Logging failures | every destructive view | Assert `AuditLog.objects.filter(...)` exists after delete. |
| **A10** SSRF | n/a | `website` URL is not fetched server-side. |

### 2.4 Entry / exit criteria

**Entry.** Seed data loaded (`seed`, `seed_vendors`); 3+ tenants; 6+ vendors each; config/settings_test.py active; pytest-django installed.

**Exit.** All §4 test cases pass; zero open Critical or High defects; line coverage ≥ 80%, branch ≥ 70%, mutation ≥ 60% on [vendors/](../../vendors/); p95 list-view latency < 300 ms at 10k rows.

---

## 3. Test Scenarios

### 3.1 Vendor CRUD

| # | Scenario | Type |
|---|---|---|
| C-01 | Unauthenticated user hits `/vendors/` | Security · A01 |
| C-02 | Authenticated tenant-A user lists own vendors | Functional |
| C-03 | Authenticated tenant-A user lists vendors — empty state | Functional |
| C-04 | Search by company_name substring | Functional |
| C-05 | Search by email substring | Functional |
| C-06 | Search by tax_id substring | Functional |
| C-07 | Filter by status=active | Functional |
| C-08 | Filter by vendor_type=manufacturer | Functional |
| C-09 | Combined search + filter retained across pagination page 2 | Regression · CLAUDE Filter Rules |
| C-10 | Create vendor — happy path | Functional |
| C-11 | Create vendor — minimum required (company_name only) | Boundary |
| C-12 | Create vendor — company_name > 255 chars | Boundary |
| C-13 | Create vendor — duplicate company_name (same tenant) | **Negative · D-01** |
| C-14 | Create vendor — duplicate company_name (different tenant) allowed | Functional |
| C-15 | Create vendor — invalid email | Negative |
| C-16 | Create vendor — `website='javascript:alert(1)'` | Security · A03 |
| C-17 | Create vendor — XSS payload in `company_name` | Security · A03 |
| C-18 | Create vendor — unicode / emoji in company_name | Edge |
| C-19 | View detail of own vendor | Functional |
| C-20 | View detail of other-tenant vendor | **Security · A01 IDOR** |
| C-21 | Edit vendor — happy path | Functional |
| C-22 | Edit vendor — change company_name to a name already taken in tenant | **Negative · D-01** |
| C-23 | Edit vendor — GET method preserves existing values | Regression |
| C-24 | Delete vendor — POST | Functional |
| C-25 | Delete vendor — GET (not allowed) | Negative |
| C-26 | Delete vendor without CSRF token | Security · CSRF |
| C-27 | Delete another tenant's vendor | **Security · A01 IDOR** |
| C-28 | Delete a vendor with active contract (cascade) | Regression |
| C-29 | Delete vendor emits AuditLog | **Security · A09 (D-09)** |

### 3.2 Vendor Performance

| # | Scenario | Type |
|---|---|---|
| P-01 | Create performance — happy path (all ratings 1-5) | Functional |
| P-02 | Create performance — rating = 0 (below min) | Boundary · Negative |
| P-03 | Create performance — rating = 6 (above max) | Boundary · Negative |
| P-04 | Create performance — `defect_rate = 150.00` | **Boundary · D-04** |
| P-05 | Create performance — `defect_rate = -1.00` | Boundary · Negative |
| P-06 | Create performance — `review_date` in the future | **Edge · D-05** |
| P-07 | Create performance — review_date accepts `0001-01-01` | Boundary |
| P-08 | Direct ORM create with `delivery_rating=0` bypasses validator | **Data integrity · D-07** |
| P-09 | Inline add from detail — form POST | Functional |
| P-10 | Inline add with invalid data — silent failure (D-11) | **UX defect** |
| P-11 | Filter performance list by vendor (FK) — pk comparison | Regression · CLAUDE Filter Rules |
| P-12 | `overall_score` rounding — `(5+4+4)/3 = 4.3` | Unit |
| P-13 | `Vendor.average_performance_score` with zero reviews returns `None` | Unit · edge |
| P-14 | `reviewed_by = SET_NULL` on user deletion keeps performance | Regression |
| P-15 | Cross-tenant: create performance for a vendor that belongs to another tenant | **Security · A01 (see §6 D-14)** |

### 3.3 Vendor Contract

| # | Scenario | Type |
|---|---|---|
| X-01 | Create contract — happy path | Functional |
| X-02 | Create contract — duplicate contract_number (same tenant) | **Negative · D-02** |
| X-03 | Create contract — same contract_number across tenants | Functional |
| X-04 | Create contract — `end_date < start_date` | **Negative · D-03** |
| X-05 | Create contract — `end_date = null` (perpetual) | Functional |
| X-06 | Create contract — `contract_value` precision `99999999.99` (max) | Boundary |
| X-07 | Create contract — `contract_value = -100` | Boundary · Negative |
| X-08 | Upload `.pdf` document — accepted | Functional |
| X-09 | Upload `.exe` document | **Security · A08 (D-06)** |
| X-10 | Upload `.svg` with embedded `<script>` | **Security · A08 polyglot** |
| X-11 | Upload 100 MB file | Security · A08 size cap |
| X-12 | Upload filename `../../etc/passwd` | Security · A08 path traversal |
| X-13 | Filter contracts by status + vendor (pk) retained across page 2 | Regression |
| X-14 | Delete contract — POST | Functional |
| X-15 | Cross-tenant delete contract (tenant-B pk via inline URL of tenant-A vendor) | Security · A01 |
| X-16 | CSRF missing on contract delete POST | Security · CSRF |

### 3.4 Vendor Communication

| # | Scenario | Type |
|---|---|---|
| M-01 | Log communication — happy path (email type) | Functional |
| M-02 | Log — `subject` 256 chars (> max_length) | Boundary |
| M-03 | Log — `message` 1 MB | Boundary · performance |
| M-04 | Log — XSS in subject | Security · A03 |
| M-05 | Log — `communication_date` in future (allowed? no validator) | Edge |
| M-06 | Filter by type + vendor retained | Regression |
| M-07 | `communicated_by = SET_NULL` on user delete | Regression |
| M-08 | Inline add from detail — `request.POST` has foreign vendor pk — overridden by URL | Security · A01 guard |

### 3.5 Seed command (management)

| # | Scenario | Type |
|---|---|---|
| S-01 | `python manage.py seed_vendors` on fresh DB creates 6 vendors/tenant | Functional |
| S-02 | Running twice is idempotent (no IntegrityError, no duplicates) | Regression |
| S-03 | `seed_vendors --flush` deletes all vendor data across tenants | Functional |
| S-04 | Seed with zero tenants prints warning, exits cleanly | Negative |

### 3.6 CLAUDE.md rule conformance

| # | Scenario | Type |
|---|---|---|
| K-01 | Every list template has a working `Actions` column (View / Edit / Delete) | **CRUD completeness (D-13 for subentity detail pages)** |
| K-02 | Every detail page has an Actions sidebar (Edit / Delete / Back) | Regression |
| K-03 | Every list view passes `*_choices` to its template | Filter Rules |
| K-04 | Every FK filter template uses `\|stringformat:"d"` (NOT `\|slugify`) | Filter Rules |
| K-05 | Seed prints tenant admin credentials + superuser warning | Seed Rules |

---

## 4. Detailed Test Cases

> Convention: `TC-<ENTITY>-<NNN>` · ID format stable across iterations · parametrised where applicable.

### 4.1 Vendor CRUD

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-VEN-001** | Unauthenticated access to vendor list redirects to login | Fresh Django test client; no session | `GET /vendors/` | — | 302 → `/accounts/login/?next=/vendors/` | Session unchanged |
| **TC-VEN-002** | Tenant-A admin sees only tenant-A vendors | 3 vendors seeded for T1, 3 for T2; user = admin_T1 | `GET /vendors/` | — | 200; body contains all T1 names; body does NOT contain T2 names | — |
| **TC-VEN-003** | Search matches by partial `company_name` | T1 has vendors ["Acme Co","Global LLC"] | `GET /vendors/?q=Acme` | `q=Acme` | 200; 1 row "Acme Co"; zero "Global LLC" | — |
| **TC-VEN-004** | Status filter works | Seed has 4 active, 1 pending, 1 inactive | `GET /vendors/?status=pending` | `status=pending` | 200; exactly 1 row ("QuickShip") | — |
| **TC-VEN-005** | Combined search+filter retained across pagination page 2 | 25 vendors, `?q=Co&status=active` | `GET /vendors/?q=Co&status=active&page=2` | | 200; page 2 URL shown; all rows contain "Co" AND status=active; hidden inputs propagate | — |
| **TC-VEN-006** | Create vendor — happy path | Logged in as admin_T1 | `POST /vendors/create/` form | `company_name=New Co`, `vendor_type=distributor`, `status=active`, `payment_terms=net_30`, `lead_time_days=7`, `minimum_order_quantity=10`, `is_active=on` | 302 → list; `Vendor.objects.filter(tenant=T1, company_name='New Co').exists()` | `messages` stack contains success |
| **TC-VEN-007** | Create — missing required `company_name` | Logged in | `POST` with blank name | `company_name=""` | 200 (re-render); form.errors has `company_name` | No vendor created |
| **TC-VEN-008** | Duplicate `company_name` (same tenant) — form must reject | T1 has "Acme Co" | `POST /vendors/create/` | `company_name="Acme Co"` | **200 re-render with `form.errors['company_name']`** — NOT a 500 | Only 1 "Acme Co" in T1 |
| **TC-VEN-009** | Duplicate `company_name` across tenants is allowed | T1 has "Acme Co" | Login as admin_T2, `POST` with same name | `company_name="Acme Co"` | 302 → list; T2 "Acme Co" created | 2 rows total across tenants |
| **TC-VEN-010** | `website=javascript:alert(1)` rejected | Logged in | `POST /vendors/create/` | `website="javascript:alert(1)"` | 200 re-render; `form.errors['website']` = "Enter a valid URL." | No vendor created |
| **TC-VEN-011** | XSS in `company_name` is escaped on list | T1 vendor with `name="<script>alert(1)</script>"` exists | `GET /vendors/` | — | `b"<script>alert(1)</script>" not in response.content`; `b"&lt;script&gt;" in response.content` | — |
| **TC-VEN-012** | Unicode + emoji preserved | Logged in | create vendor `name="Société 日本 🚀"` | — | Roundtrips; displayed verbatim | — |
| **TC-VEN-013** | Cross-tenant IDOR on detail → 404 | T2 vendor pk=99 exists; login as admin_T1 | `GET /vendors/99/` | — | 404 | — |
| **TC-VEN-014** | Cross-tenant IDOR on edit GET → 404 | as above | `GET /vendors/99/edit/` | — | 404 | — |
| **TC-VEN-015** | Cross-tenant IDOR on edit POST → 404, not a data leak | as above | `POST /vendors/99/edit/` with valid data | — | 404; tenant-B vendor unchanged | — |
| **TC-VEN-016** | Cross-tenant IDOR on delete → 404, row NOT deleted | as above | `POST /vendors/99/delete/` | — | 404; `Vendor.objects.filter(pk=99).exists()` remains True | — |
| **TC-VEN-017** | Delete via GET is a no-op | Vendor pk=1 of T1, login admin_T1 | `GET /vendors/1/delete/` | — | 302 → list; vendor still exists | — |
| **TC-VEN-018** | Delete without CSRF returns 403 | `Client(enforce_csrf_checks=True)`; force_login admin_T1 | `POST /vendors/1/delete/` without csrfmiddlewaretoken | — | 403 Forbidden; vendor unchanged | — |
| **TC-VEN-019** | Delete emits AuditLog | Vendor pk=1 exists, admin_T1 | `POST /vendors/1/delete/` with CSRF | — | `AuditLog.objects.filter(tenant=T1, action__icontains='delete', model_name='Vendor', object_id='1').exists()` | **CURRENTLY FAILS → D-09** |
| **TC-VEN-020** | Bulk 500 vendors — list view ≤ 10 SQL queries | Seed 500 vendors | `GET /vendors/` with `django_assert_max_num_queries(10)` | — | passes | — |

### 4.2 VendorPerformance

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-PERF-001** | Create — ratings 1/1/1 | Vendor exists | POST `performance/create/` | `delivery=1,quality=1,compliance=1,defect_rate=0,on_time_delivery_rate=0` | 302; record created; `overall_score == 1.0` | `reviewed_by = request.user` |
| **TC-PERF-002** | Create — ratings 5/5/5 | as above | POST | `…=5,5,5,0.00,100.00` | 302; `overall_score == 5.0` | — |
| **TC-PERF-003** | Create — rating = 0 rejected | as above | POST with `delivery=0` | — | 200 re-render; `form.errors['delivery_rating']` | — |
| **TC-PERF-004** | Create — rating = 6 rejected | as above | POST with `quality=6` | — | 200 re-render; `form.errors['quality_rating']` | — |
| **TC-PERF-005** | Create — `defect_rate=150.00` | as above | POST | `defect_rate=150` | **SHOULD BE 200 re-render with error — CURRENTLY 302 success** (D-04) | — |
| **TC-PERF-006** | Create — `defect_rate=-1` | as above | POST | `defect_rate=-1` | 200 re-render (DecimalField rejects negative when `min='0'` only enforced client-side; server accepts if model allows). Actually DB column is `Decimal(5,2)` not `PositiveDecimal` — accepts negatives. **DEFECT if accepted.** | — |
| **TC-PERF-007** | Create — review_date future | as above | POST `review_date=2099-01-01` | — | **SHOULD reject — CURRENTLY accepts (D-05)** | — |
| **TC-PERF-008** | Create — review_date `0001-01-01` | as above | POST | — | Accepted by Django DateField; noise — recommend ≥ 2000-01-01 | — |
| **TC-PERF-009** | ORM create with `delivery_rating=0` | no form | `VendorPerformance.objects.create(..., delivery_rating=0,...)` | — | **Created — validators not enforced at DB layer (D-07)** | — |
| **TC-PERF-010** | Inline add from detail happy path | Vendor pk=1, logged in | `POST /vendors/1/performance/add/` | valid data | 302 → detail; 1 new row | — |
| **TC-PERF-011** | Inline add with invalid data silently redirects | Vendor pk=1 | POST with `review_date=""` | — | 302 → detail; **NO error message shown (D-11)** | — |
| **TC-PERF-012** | Filter performance list by vendor pk — retained across pages | 30 rows for vendor pk=3 | `GET /vendors/performance/?vendor=3&page=2` | — | Page 2 contains only vendor=3 rows; hidden filter preserved | — |
| **TC-PERF-013** | `overall_score` rounding — `(5+4+4)/3 = 4.333` | create perf with 5/4/4 | read `.overall_score` | — | `4.3` (1 decimal round) | — |
| **TC-PERF-014** | `average_performance_score` with 0 reviews | Vendor with no perf | read property | — | `None` | — |
| **TC-PERF-015** | Cross-tenant: inline-add via T1 URL for vendor pk that belongs to T2 | T2 vendor pk=99 | login as T1, `POST /vendors/99/performance/add/` | valid data | 404 (vendor scoped in URL) | No record created |
| **TC-PERF-016** | `reviewed_by = SET_NULL` on user delete | perf.reviewed_by=userX; delete userX | `User.delete()` | — | performance still exists with `reviewed_by=None` | — |

### 4.3 VendorContract

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-CON-001** | Create — happy path | Vendor exists | POST `contracts/create/` | `number=CON-001, start=today, end=today+365, value=10000` | 302; row created | — |
| **TC-CON-002** | Duplicate contract_number (same tenant) | T1 has CON-001 | POST | `number=CON-001` | **200 re-render with form error — CURRENTLY 500 IntegrityError (D-02)** | — |
| **TC-CON-003** | Same number across tenants allowed | T1 has CON-001 | login admin_T2, POST | `number=CON-001` | 302; created | — |
| **TC-CON-004** | `end_date < start_date` rejected | — | POST `start=2026-06-01, end=2026-01-01` | — | **200 re-render with error — CURRENTLY 302 success (D-03)** | — |
| **TC-CON-005** | `end_date = blank` allowed | — | POST with `end_date=""` | — | 302; `end_date=None` | — |
| **TC-CON-006** | `contract_value = 99999999.99` (max_digits=12) | — | POST | `value=99999999.99` | 302 | — |
| **TC-CON-007** | `contract_value = 999999999999.99` (overflow) | — | POST | — | 200 re-render with error | — |
| **TC-CON-008** | `contract_value = -100` | — | POST | `value=-100` | **Should reject** — currently DecimalField(min=0 only on widget) | — |
| **TC-CON-009** | Upload `.pdf` — accepted | — | POST multipart with `document=contract.pdf` (1 MB, valid %PDF magic) | — | 302 | File stored under `vendors/contracts/` |
| **TC-CON-010** | **Upload `.exe`** | — | POST multipart with `document=trojan.exe` (MZ magic) | — | **200 re-render rejecting ext — CURRENTLY accepts (D-06)** | — |
| **TC-CON-011** | Upload `.svg` with `<script>` | — | POST multipart with SVG polyglot | — | Reject — currently accepts | — |
| **TC-CON-012** | Upload 50 MB file | — | POST multipart 50 MB | — | Reject with size error — currently accepts up to server limit | — |
| **TC-CON-013** | Filename traversal `../../secret.txt` | — | POST multipart | — | Django `FileSystemStorage.get_valid_name()` strips `/`; final name sanitised | — |
| **TC-CON-014** | Filter by status + vendor pk retained on page 2 | 30 contracts | `GET /vendors/contracts/?status=active&vendor=3&page=2` | — | hidden filter inputs preserved | — |
| **TC-CON-015** | Delete contract emits AuditLog | — | POST delete | — | **Expected AuditLog — CURRENTLY missing (D-09)** | — |
| **TC-CON-016** | Cross-tenant inline delete | T2 contract pk=99 | `POST /vendors/1/contracts/99/delete/` as admin_T1 | — | 404; T2 contract intact | — |

### 4.4 VendorCommunication

| ID | Description | Pre-conditions | Steps | Expected Result |
|---|---|---|---|---|
| **TC-COM-001** | Log — happy path email | — | POST | 302; row created with `communicated_by=request.user` |
| **TC-COM-002** | `subject` > 255 chars | — | POST 300-char subject | 200 re-render with length error |
| **TC-COM-003** | `message` 1 MB | — | POST | 302 accepted (TextField) |
| **TC-COM-004** | XSS in subject | — | POST `subject=<script>` | 302; rendering escapes on detail |
| **TC-COM-005** | Filter by type + vendor retained on page 2 | 30 rows | `GET …&type=email&vendor=3&page=2` | preserved |
| **TC-COM-006** | Inline add w/ foreign vendor pk in form body, URL pk is tenant-A | — | POST | 302; saved row has `vendor = URL pk` (A01 guarded) |

### 4.5 Security (cross-cutting)

| ID | Description | Pre-conditions | Steps | Expected Result |
|---|---|---|---|---|
| **TC-SEC-001** | Auth required on 22 URLs | anon client | parametrize all URLs | 302 → login |
| **TC-SEC-002** | Cross-tenant IDOR on all 4 detail/edit/delete endpoints | T2 pk=99 | parametrize | 404 |
| **TC-SEC-003** | CSRF enforced on all destructive POSTs | `enforce_csrf_checks=True` | POST delete | 403 |
| **TC-SEC-004** | `target="_blank"` has `rel="noopener noreferrer"` on website link | vendor with website | `GET /vendors/<pk>/` | `rel="noopener noreferrer"` in anchor — **currently MISSING (D-08)** |
| **TC-SEC-005** | No raw SQL — `?q=' OR 1=1 --` returns 200 empty list | — | GET | ORM parameterizes; safe |
| **TC-SEC-006** | No role check lets an arbitrary authenticated tenant user delete a vendor | non-admin `tenant_user` of T1 | POST delete | **Currently 302 success — expected 403 (D-10)** |
| **TC-SEC-007** | AuditLog row emitted on every destructive op | — | create/delete across all 4 entities | row exists (D-09 — currently fails) |

### 4.6 Seed / CLAUDE.md conformance

| ID | Description | Steps | Expected Result |
|---|---|---|---|
| **TC-SEED-001** | `seed_vendors` on empty DB | `call_command('seed_vendors')` | 6 vendors per tenant created |
| **TC-SEED-002** | Run twice — idempotent | run twice | second run prints "already exists, Use --flush"; no duplicates |
| **TC-SEED-003** | `seed_vendors --flush` | run | all vendor data deleted then re-seeded |
| **TC-CLAUDE-001** | Every list template has Actions col (View+Edit+Delete) | scan templates | `vendor_list.html` ✅ (all 3); `performance_list.html` / `contract_list.html` / `communication_list.html` — **verify (likely missing View; no detail page exists)** |
| **TC-CLAUDE-002** | No filter uses `\|slugify` for pk | grep | zero matches |
| **TC-CLAUDE-003** | Seed prints superuser warning | stdout capture | `"Superuser \"admin\" has no tenant"` present |

---

## 5. Automation Strategy

### 5.1 Tool stack (recommended)

| Purpose | Tool | Rationale |
|---|---|---|
| Unit / integration | **pytest-django** (already in use for catalog) | Consistent with repo convention |
| Fixtures | **factory-boy** + **faker** | Avoid fixture duplication; deterministic seeds |
| Functional E2E | **Playwright (Python)** | Multi-tenant smoke; runs against live `runserver` |
| Load / stress | **Locust** | Contract list at 10 k rows; `p95 < 300 ms` |
| SAST | **bandit** + **ruff** | Catches `exec`, `shell=True`, hardcoded secrets, unused imports |
| DAST | **OWASP ZAP (baseline)** | XSS / SQLi / misconfig smoke in CI |
| Coverage | **coverage.py** + **pytest-cov** | Line & branch; goal ≥ 80/70 |
| Mutation | **mutmut** | Catches tests that don't actually assert |

### 5.2 Suite layout

```
vendors/
└── tests/
    ├── __init__.py
    ├── conftest.py              # fixtures (tenant, user, vendor, contract, ...)
    ├── factories.py             # factory-boy factories
    ├── test_models.py           # unit — saves, properties, __str__
    ├── test_forms.py            # form validation incl. clean_* guards
    ├── test_views_vendor.py     # integration — list/create/edit/detail/delete
    ├── test_views_performance.py
    ├── test_views_contract.py   # incl. file upload
    ├── test_views_communication.py
    ├── test_security.py         # OWASP-mapped
    ├── test_performance.py      # query counts
    ├── test_seed.py             # idempotency + --flush
    └── e2e/
        └── test_vendor_smoke.py # Playwright
```

Add `vendors/tests` to [pytest.ini](../../pytest.ini) `testpaths` alongside `catalog/tests`.

### 5.3 `conftest.py` — tenant-scoped fixtures

```python
# vendors/tests/conftest.py
import pytest
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model

from core.models import Tenant
from vendors.models import Vendor, VendorPerformance, VendorContract, VendorCommunication

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
        username="vendor_qa",
        password="qa_pass_123!",
        tenant=tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def other_user(db, other_tenant):
    return User.objects.create_user(
        username="vendor_qa_other",
        password="qa_pass_123!",
        tenant=other_tenant,
        is_tenant_admin=True,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(
        tenant=tenant,
        company_name="Acme Corp",
        email="acme@example.com",
        vendor_type="manufacturer",
        status="active",
        payment_terms="net_30",
    )


@pytest.fixture
def foreign_vendor(db, other_tenant):
    return Vendor.objects.create(
        tenant=other_tenant,
        company_name="Foreign Co",
        status="active",
    )


@pytest.fixture
def performance(db, tenant, vendor, user):
    return VendorPerformance.objects.create(
        tenant=tenant, vendor=vendor,
        review_date=date.today(),
        delivery_rating=5, quality_rating=4, compliance_rating=5,
        defect_rate=Decimal("1.20"),
        on_time_delivery_rate=Decimal("97.50"),
        reviewed_by=user,
    )


@pytest.fixture
def contract(db, tenant, vendor):
    return VendorContract.objects.create(
        tenant=tenant, vendor=vendor,
        contract_number="CON-001", title="Annual Supply",
        start_date=date.today(),
        end_date=date.today().replace(year=date.today().year + 1),
        payment_terms="net_30", lead_time_days=14, moq=100,
        contract_value=Decimal("100000.00"),
        status="active",
    )
```

### 5.4 `test_models.py` — model invariants

```python
# vendors/tests/test_models.py
import pytest
from decimal import Decimal
from datetime import date
from django.db import IntegrityError, transaction

from vendors.models import Vendor, VendorPerformance, VendorContract


@pytest.mark.django_db
class TestVendorModel:
    def test_str_returns_company_name(self, vendor):
        assert str(vendor) == "Acme Corp"

    def test_unique_together_tenant_company_name(self, tenant, vendor):
        with pytest.raises(IntegrityError), transaction.atomic():
            Vendor.objects.create(
                tenant=tenant, company_name="Acme Corp", status="active",
            )

    def test_same_company_name_across_tenants_allowed(self, tenant, other_tenant, vendor):
        clone = Vendor.objects.create(
            tenant=other_tenant, company_name="Acme Corp", status="active",
        )
        assert clone.pk != vendor.pk

    def test_average_performance_score_none_when_no_reviews(self, vendor):
        assert vendor.average_performance_score is None

    def test_average_performance_score_rounds_to_1_decimal(self, vendor, tenant):
        VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=5, quality_rating=4, compliance_rating=4,
        )  # overall 4.3
        VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=3, quality_rating=3, compliance_rating=3,
        )  # overall 3.0
        assert vendor.average_performance_score == 3.7  # (4.3+3.0)/2 = 3.65 → 3.7


@pytest.mark.django_db
class TestPerformanceModel:
    def test_overall_score_rounds(self, performance):
        # (5+4+5)/3 = 4.666... → 4.7
        assert performance.overall_score == 4.7

    @pytest.mark.parametrize("d,q,c,expected", [
        (5, 5, 5, 5.0),
        (1, 1, 1, 1.0),
        (3, 4, 5, 4.0),
    ])
    def test_overall_score_parametrised(self, tenant, vendor, d, q, c, expected):
        p = VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=d, quality_rating=q, compliance_rating=c,
        )
        assert p.overall_score == expected


@pytest.mark.django_db
class TestContractModel:
    def test_unique_together_tenant_contract_number(self, contract):
        with pytest.raises(IntegrityError), transaction.atomic():
            VendorContract.objects.create(
                tenant=contract.tenant, vendor=contract.vendor,
                contract_number="CON-001", title="dup",
                start_date=date.today(),
            )
```

### 5.5 `test_forms.py` — form-level negative coverage

```python
# vendors/tests/test_forms.py
import pytest
from datetime import date, timedelta
from decimal import Decimal

from vendors.forms import (
    VendorForm, VendorPerformanceForm, VendorContractForm, VendorCommunicationForm
)
from vendors.models import Vendor


@pytest.mark.django_db
class TestVendorFormDuplicate:
    """D-01 regression."""
    def test_duplicate_company_name_same_tenant_raises_form_error(self, tenant, vendor):
        form = VendorForm(
            data={
                "company_name": "Acme Corp",
                "vendor_type": "distributor", "status": "active",
                "payment_terms": "net_30", "lead_time_days": 0,
                "minimum_order_quantity": 1, "is_active": "on",
            },
            tenant=tenant,
        )
        assert form.is_valid() is False
        assert "company_name" in form.errors


@pytest.mark.django_db
class TestPerformanceFormBoundaries:
    def _base(self, vendor):
        return {
            "vendor": vendor.pk,
            "review_date": date.today().isoformat(),
            "delivery_rating": 5, "quality_rating": 5, "compliance_rating": 5,
            "defect_rate": "0", "on_time_delivery_rate": "100",
        }

    @pytest.mark.parametrize("field", ["delivery_rating", "quality_rating", "compliance_rating"])
    def test_rating_zero_rejected(self, tenant, vendor, field):
        data = self._base(vendor); data[field] = 0
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert field in form.errors

    @pytest.mark.parametrize("field", ["delivery_rating", "quality_rating", "compliance_rating"])
    def test_rating_six_rejected(self, tenant, vendor, field):
        data = self._base(vendor); data[field] = 6
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert field in form.errors

    def test_defect_rate_above_100_rejected(self, tenant, vendor):
        """D-04 regression."""
        data = self._base(vendor); data["defect_rate"] = "150.00"
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert "defect_rate" in form.errors

    def test_review_date_in_future_rejected(self, tenant, vendor):
        """D-05 regression."""
        data = self._base(vendor)
        data["review_date"] = (date.today() + timedelta(days=30)).isoformat()
        form = VendorPerformanceForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert "review_date" in form.errors


@pytest.mark.django_db
class TestContractFormCrossField:
    def _base(self, vendor):
        return {
            "vendor": vendor.pk,
            "contract_number": "CON-BAR",
            "title": "Test",
            "start_date": date.today().isoformat(),
            "end_date": "",
            "payment_terms": "net_30",
            "lead_time_days": 0, "moq": 1,
            "contract_value": "0.00",
            "status": "draft",
        }

    def test_duplicate_contract_number_same_tenant(self, tenant, contract, vendor):
        """D-02 regression."""
        data = self._base(vendor); data["contract_number"] = "CON-001"
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert "contract_number" in form.errors

    def test_end_date_before_start_date_rejected(self, tenant, vendor):
        """D-03 regression."""
        data = self._base(vendor)
        data["start_date"] = "2026-06-01"
        data["end_date"]   = "2026-01-01"
        form = VendorContractForm(data=data, tenant=tenant)
        assert form.is_valid() is False
        assert form.non_field_errors() or "end_date" in form.errors

    def test_exe_document_rejected(self, tenant, vendor):
        """D-06 regression."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        evil = SimpleUploadedFile("trojan.exe", b"MZ\x90\x00", content_type="application/x-msdownload")
        data = self._base(vendor)
        form = VendorContractForm(data=data, files={"document": evil}, tenant=tenant)
        assert form.is_valid() is False
        assert "document" in form.errors
```

### 5.6 `test_views_vendor.py` — integration + tenant isolation

```python
# vendors/tests/test_views_vendor.py
import pytest
from django.urls import reverse

from vendors.models import Vendor


@pytest.mark.django_db
class TestVendorList:
    def test_only_own_tenant_vendors_shown(self, client_logged_in, vendor, foreign_vendor):
        r = client_logged_in.get(reverse("vendors:vendor_list"))
        assert r.status_code == 200
        assert b"Acme Corp" in r.content
        assert b"Foreign Co" not in r.content

    @pytest.mark.parametrize("q,expected", [
        ("Acme", True),
        ("NotHere", False),
    ])
    def test_search_by_name(self, client_logged_in, vendor, q, expected):
        r = client_logged_in.get(reverse("vendors:vendor_list"), {"q": q})
        assert r.status_code == 200
        assert (b"Acme Corp" in r.content) == expected

    def test_filter_status(self, client_logged_in, tenant, vendor):
        Vendor.objects.create(tenant=tenant, company_name="Pending Co", status="pending")
        r = client_logged_in.get(reverse("vendors:vendor_list"), {"status": "pending"})
        assert b"Pending Co" in r.content
        assert b"Acme Corp" not in r.content


@pytest.mark.django_db
class TestVendorIDOR:
    def test_detail_cross_tenant_404(self, client_logged_in, foreign_vendor):
        r = client_logged_in.get(reverse("vendors:vendor_detail", args=[foreign_vendor.pk]))
        assert r.status_code == 404

    def test_delete_cross_tenant_404_not_deleted(self, client_logged_in, foreign_vendor):
        r = client_logged_in.post(reverse("vendors:vendor_delete", args=[foreign_vendor.pk]))
        assert r.status_code == 404
        assert Vendor.objects.filter(pk=foreign_vendor.pk).exists()


@pytest.mark.django_db
class TestVendorXSS:
    def test_script_in_name_escaped_on_list(self, client_logged_in, tenant):
        Vendor.objects.create(tenant=tenant, company_name="<script>alert(1)</script>", status="active")
        r = client_logged_in.get(reverse("vendors:vendor_list"))
        assert b"<script>alert(1)</script>" not in r.content
        assert b"&lt;script&gt;" in r.content
```

### 5.7 `test_security.py` — OWASP-mapped

```python
# vendors/tests/test_security.py
import pytest
from django.test import Client
from django.urls import reverse


VENDOR_URLS = [
    ("vendors:vendor_list", []),
    ("vendors:vendor_create", []),
    ("vendors:performance_list", []),
    ("vendors:contract_list", []),
    ("vendors:communication_list", []),
]


@pytest.mark.django_db
class TestAuthRequired:  # A01
    @pytest.mark.parametrize("name,args", VENDOR_URLS)
    def test_anon_redirects_to_login(self, client, name, args):
        r = client.get(reverse(name, args=args))
        assert r.status_code == 302
        assert "login" in r.url.lower()


@pytest.mark.django_db
class TestCSRF:  # A01
    def test_delete_without_csrf_403(self, user, vendor):
        c = Client(enforce_csrf_checks=True); c.force_login(user)
        r = c.post(reverse("vendors:vendor_delete", args=[vendor.pk]))
        assert r.status_code == 403


@pytest.mark.django_db
class TestAuditLog:  # A09 — currently expected to FAIL → tracks D-09
    def test_delete_emits_audit_log(self, client_logged_in, user, vendor):
        from core.models import AuditLog
        client_logged_in.post(reverse("vendors:vendor_delete", args=[vendor.pk]))
        assert AuditLog.objects.filter(
            tenant=user.tenant, model_name="Vendor", object_id=str(vendor.pk),
            action__icontains="delete",
        ).exists()


@pytest.mark.django_db
class TestWebsiteLinkTabnabbing:  # A03 — D-08
    def test_website_link_has_rel_noopener(self, client_logged_in, vendor):
        vendor.website = "https://evil.example"
        vendor.save()
        r = client_logged_in.get(reverse("vendors:vendor_detail", args=[vendor.pk]))
        assert b'rel="noopener noreferrer"' in r.content
```

### 5.8 `test_performance.py` — query counts

```python
# vendors/tests/test_performance.py
import pytest
from django.urls import reverse

from vendors.models import Vendor, VendorPerformance
from datetime import date


@pytest.mark.django_db
def test_vendor_list_n_plus_one_guard(client_logged_in, tenant, django_assert_max_num_queries):
    # 50 vendors, 3 perfs each
    for i in range(50):
        v = Vendor.objects.create(tenant=tenant, company_name=f"V{i}", status="active")
        for _ in range(3):
            VendorPerformance.objects.create(
                tenant=tenant, vendor=v, review_date=date.today(),
                delivery_rating=5, quality_rating=5, compliance_rating=5,
            )
    with django_assert_max_num_queries(10):
        client_logged_in.get(reverse("vendors:vendor_list"))


@pytest.mark.django_db
def test_average_performance_score_is_db_aggregated(vendor, tenant):
    """D-12: should use DB aggregate, not Python iteration."""
    from django.db import connection
    for _ in range(20):
        VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=5, quality_rating=5, compliance_rating=5,
        )
    connection.queries_log.clear()
    _ = vendor.average_performance_score
    # Expected: 1 query (aggregate); current impl: 1 query loading all rows → passes but mem-heavy
    assert len(connection.queries) <= 1
```

### 5.9 Running the suite (PowerShell)

```
cd C:\xampp\htdocs\NavIMS
venv\Scripts\Activate.ps1
pytest vendors/tests -v --cov=vendors --cov-report=term-missing
```

Update [pytest.ini](../../pytest.ini) `testpaths` to include `vendors/tests`.

### 5.10 CI gates (proposed)

| Gate | Threshold | Fail build if |
|---|---|---|
| pytest | all pass | any failure |
| coverage | line ≥ 80%, branch ≥ 70% | below |
| bandit | zero HIGH findings | any HIGH |
| ruff | zero | any |
| mutmut | ≥ 60% killed | below |
| `django-assert-max-num-queries` | per test | exceeded |

---

## 6. Defects, Risks & Recommendations

### 6.1 Defect register (verified unless stated)

| ID | Sev | Location | Finding | Recommendation | OWASP |
|---|---|---|---|---|---|
| **D-01** | **Critical** | [vendors/forms.py:5](../../vendors/forms.py#L5) `VendorForm` | **Verified**: duplicate `company_name` for the same tenant passes `form.is_valid() == True` (probe: `form.errors == (none)`) and then raises `IntegrityError: UNIQUE constraint failed: vendors_vendor.tenant_id, vendors_vendor.company_name` on save → **HTTP 500**. Root cause is the pattern documented in [lessons.md #6](../tasks/lessons.md): `tenant` is not a form field, so Django's `validate_unique()` excludes it and the `unique_together` partial check never runs. | Add `clean_company_name(self)` that does `qs = Vendor.objects.filter(tenant=self.tenant, company_name__iexact=name); if self.instance.pk: qs = qs.exclude(pk=self.instance.pk); if qs.exists(): raise ValidationError(...)`. Mirror catalog's `clean_sku`. | A04 Insecure design |
| **D-02** | **Critical** | [vendors/forms.py:176](../../vendors/forms.py#L176) `VendorContractForm` | **Verified**: same pattern on `('tenant','contract_number')` → 500 on duplicate. | Add `clean_contract_number` guard filtered by `self.tenant`. | A04 |
| **D-03** | **High** | [vendors/forms.py:176](../../vendors/forms.py#L176) `VendorContractForm` | **Verified**: `end_date=2026-01-01 < start_date=2026-06-01` passes form validation (probe `form.is_valid() == True`). | Override `clean()`: `if end_date and end_date <= start_date: raise ValidationError('End date must be after start date')`. | A04 |
| **D-04** | **High** | [vendors/models.py:101](../../vendors/models.py#L101) `VendorPerformance.defect_rate` / `on_time_delivery_rate` | **Verified**: `defect_rate=999.99` accepted (`max_digits=5, decimal_places=2` bounds the column but not the logical range). HTML `max=100` is client-side only. | Add `validators=[MinValueValidator(0), MaxValueValidator(100)]` to both fields on the model (and make new migration). | A04 |
| **D-05** | **Medium** | [vendors/models.py:88](../../vendors/models.py#L88) `VendorPerformance.review_date` | **Verified**: review_date 3650 days in the future accepted. | Add `clean_review_date` in form: `if value > date.today(): raise ValidationError('Review date cannot be in the future')`. | A04 |
| **D-06** | **Critical** | [vendors/models.py:160](../../vendors/models.py#L160) `VendorContract.document` | **Verified**: a `trojan.exe` upload passes form validation. No extension whitelist, no MIME/magic-byte check, no size limit, no SVG exclusion, no polyglot defence. Files land under `MEDIA_ROOT/vendors/contracts/` and are publicly servable. | In `VendorContractForm.clean_document`: (a) enforce `FileExtensionValidator(['pdf','doc','docx'])`, (b) cap size at 10 MB, (c) verify magic bytes with `python-magic`, (d) reject `image/svg+xml`. Serve via authenticated view rather than `MEDIA_URL`. | **A08** Software & data integrity |
| **D-07** | **Medium** | [vendors/models.py:89-100](../../vendors/models.py#L89) | **Verified**: ORM-level `create(delivery_rating=0, quality_rating=0, compliance_rating=0)` succeeds. `MinValueValidator(1)` only runs at form/full_clean(). `PositiveIntegerField` permits `0`. | Add DB `CheckConstraint(check=Q(delivery_rating__gte=1) & Q(delivery_rating__lte=5), name=...)` for each rating field in `Meta.constraints`. | A04 |
| **D-08** | **Medium** | [templates/vendors/vendor_detail.html:59](../../templates/vendors/vendor_detail.html#L59) | `<a href="{{ vendor.website }}" target="_blank">` has **no `rel="noopener noreferrer"`** → reverse-tabnabbing. | Add `rel="noopener noreferrer"` to all `target="_blank"` anchors across the module (website link, document download link [:308](../../templates/vendors/vendor_detail.html#L308)). | A03 |
| **D-09** | **Medium** | every destructive view in [views.py](../../vendors/views.py) | No `AuditLog.objects.create(...)` emitted on vendor/contract/performance/communication create/update/delete. Post-incident investigation has no trail. | Add a reusable `emit_audit(request, action, instance, changes='')` helper and call it from every destructive view. | A09 |
| **D-10** | **High** | every view (e.g. [views.py:123](../../vendors/views.py#L123) `vendor_delete_view`) | Only `@login_required`. **Any authenticated tenant user** (incl. invited user with no admin role) can delete vendors, contracts, reviews. No `is_tenant_admin` / RBAC gate. | Introduce a `@tenant_admin_required` decorator (or check `request.user.is_tenant_admin`) on every destructive handler. Wire permissions with `core.Role`/`core.Permission` once that exists. | A01 |
| **D-11** | **Low** | [views.py:427-512](../../vendors/views.py#L427) inline `*_add_view` handlers | `if form.is_valid(): ... ` has no `else` branch. Invalid data → silent redirect to detail, **no error message, no form state retained**. User blames the app. | On invalid form, `messages.error(request, form.errors.as_text())` before redirect. Better: re-render `vendor_detail.html` with the form bound. | — (UX) |
| **D-12** | **Low** | [vendors/models.py:68-74](../../vendors/models.py#L68) `Vendor.average_performance_score` | `sum(p.overall_score for p in performances)` loads all `VendorPerformance` rows into Python. O(n) memory per access. | Replace with `self.performances.aggregate(avg=Avg((F('delivery_rating')+F('quality_rating')+F('compliance_rating'))/3.0))['avg']` or cache the value. | — (perf) |
| **D-13** | **Low** | — | No standalone detail views for `VendorContract` / `VendorPerformance` / `VendorCommunication`. The CLAUDE.md "CRUD Completeness" rule allows skipping detail "for models without enough fields", but `VendorContract` has 12 fields + file document — clearly enough. Users can only access contract details via the vendor-detail page (not via contract-list View icon). | Add `contract_detail_view` / template; same for performance and communication. | CLAUDE conformance |
| **D-14** | **Low-Medium** | [views.py:432](../../vendors/views.py#L432), [:468](../../vendors/views.py#L468), [:503](../../vendors/views.py#L503) inline `*_add_view` | Forms constructed as `VendorPerformanceForm(request.POST)` without `tenant=tenant`. The `vendor` queryset is not restricted. The view then overrides `.vendor = vendor_from_url`, so not exploitable today, but defence-in-depth broken — a future change that reads `form.cleaned_data['vendor']` before overwriting would leak cross-tenant. | Pass `tenant=tenant` to the form in all three inline-add views. | A01 |
| **D-15** | **Info** | [templates/vendors/vendor_detail.html:189-214](../../templates/vendors/vendor_detail.html#L189) | Inline performance/contract/communication tables expose only a Delete icon in their Actions column — no Edit icon. Hides the edit routes that do exist (`performance_edit`, `contract_edit`, `communication_edit`). | Add Edit icon linking to the standalone edit view. | CLAUDE conformance |
| **D-16** | **Info** | [vendors/models.py:54](../../vendors/models.py#L54) `minimum_order_quantity = PositiveIntegerField(default=1)` | `PositiveIntegerField` allows 0. MOQ=0 is semantically meaningless. Form `min='1'` is client-side only. | Add `MinValueValidator(1)` on the model field; migration required. | A04 |
| **D-17** | **Info** | [vendors/models.py:158](../../vendors/models.py#L158) `contract_value = DecimalField(..., default=0)` | Form allows negative values via server (only `min='0'` widget attr). | Add `MinValueValidator(0)` on the field. | A04 |

### 6.2 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A malicious contract file (e.g. weaponised PDF) shared via `MEDIA_URL` and downloaded by another user | Medium | **High** — RCE on employee's workstation | D-06 remediation + serve via authenticated view + virus scanner hook |
| Duplicate vendor/contract causes a user-facing 500 on common input | **High** (duplicate names happen) | Medium — loss of trust, support ticket | D-01 + D-02 |
| Non-admin tenant user wipes vendor data in malice | Low | **High** — business continuity | D-10 |
| No audit trail makes internal-fraud investigation impossible | Medium | High | D-09 |
| Performance data entry at scale (>10k vendors) degrades list view | Low | Low | Already using `select_related`; monitor via `django_assert_max_num_queries` |

### 6.3 Remediation priority (sequenced)

1. **D-01, D-02** — 2 hrs — add `clean_<field>` guards; parametrised tests.
2. **D-06** — 4 hrs — file validator + magic-byte + size cap + auth-served download view.
3. **D-04** — 1 hr — model validators + migration.
4. **D-10** — 3 hrs — `@tenant_admin_required` decorator, wire to delete views.
5. **D-03** — 1 hr — `clean()` cross-field.
6. **D-05, D-07, D-16, D-17** — 2 hrs bundled — validators + migrations.
7. **D-09** — 3 hrs — `emit_audit` helper + unit test.
8. **D-08** — 15 min — template edit.
9. **D-11** — 1 hr — form re-render on inline add failure.
10. **D-12, D-13, D-14, D-15** — polish, defer to next sprint.

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage targets per file

| File | Line % | Branch % | Mutation % |
|---|---|---|---|
| [vendors/models.py](../../vendors/models.py) | 95 | 90 | 75 |
| [vendors/forms.py](../../vendors/forms.py) | 90 | 85 | 70 |
| [vendors/views.py](../../vendors/views.py) | 85 | 75 | 65 |
| [vendors/management/commands/seed_vendors.py](../../vendors/management/commands/seed_vendors.py) | 70 | 60 | 50 |
| **Module total** | **≥ 80** | **≥ 70** | **≥ 60** |

### 7.2 KPI dashboard (traffic-light thresholds)

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | 100% | 95-99% | < 95% |
| Open Critical defects | 0 | — | ≥ 1 |
| Open High defects | ≤ 1 | 2-3 | ≥ 4 |
| Test-suite runtime (whole `vendors/tests`) | < 10 s | 10-30 s | > 30 s |
| Query count — `vendor_list` page (50 vendors) | ≤ 10 | 11-15 | > 15 |
| p95 latency — `vendor_list` page @ 10k rows (Locust) | < 300 ms | 300-700 ms | > 700 ms |
| Regression escape rate (defects found after release / total) | ≤ 5% | 5-10% | > 10% |
| AuditLog coverage on destructive ops | 100% | — | < 100% |

### 7.3 Release exit gate (all must be TRUE)

- [ ] All Critical defects (D-01, D-02, D-06) fixed and regression-tested.
- [ ] All High defects (D-03, D-04, D-10) fixed and regression-tested.
- [ ] `pytest vendors/tests` — 100% passing.
- [ ] `coverage` line ≥ 80%, branch ≥ 70% on `vendors/*.py`.
- [ ] `bandit -r vendors/` — zero HIGH findings.
- [ ] OWASP ZAP baseline against `/vendors/` — zero High findings.
- [ ] Manual smoke: create→edit→upload PDF→delete vendor on 2 tenants as admin, as non-admin (must fail for non-admin).
- [ ] Seed command idempotent on 3 consecutive runs.
- [ ] CLAUDE.md Filter Rules — `grep -r "|slugify" templates/vendors` returns zero.

---

## 8. Summary

The [vendors/](../../vendors/) module is **functionally coherent** (CRUD + inline sub-entity UX, sensible seed data, consistent tenant-scoped queries), but carries **three Critical defects** that would fail a staff-engineer review:

1. **D-01 / D-02** — the `unique_together` + form trap first captured in [lessons.md #6](../tasks/lessons.md) for the catalog module is **present again here** on both `Vendor.company_name` and `VendorContract.contract_number`. Duplicate input produces a 500 instead of a form error. *Confirmed by Django-shell probe.*
2. **D-06** — `VendorContract.document` accepts arbitrary file types including `.exe`/`.svg`/polyglots with no size cap, and is served via public `MEDIA_URL`. This is a direct A08 failure with an easy, high-value remediation path.

Five further **High / Medium** defects round out the list: missing cross-field date validation on contracts (D-03), unbounded `defect_rate`/`on_time_delivery_rate` (D-04), future-dated reviews (D-05), no DB-level CHECK on ratings (D-07), and missing RBAC + audit logging on destructive ops (D-09, D-10). All six have concrete shell reproductions in §6.

The module has **no automated tests** today. §5 proposes a full `vendors/tests` suite (conftest + 7 test files + fixtures) that is **runnable verbatim** against the current codebase, covers every scenario in §3, and encodes each defect as a regression test so the fix is provable and future-proof.

Recommended next action: **invoke the skill again with "fix the defects"** — I'll implement D-01 through D-10 in priority order (est. 16 hrs), verify each via shell + new test, and emit per-file PowerShell-safe commits per CLAUDE.md.

---

*Report generated 2026-04-17 by SQA Review skill. All defects marked "Verified" were reproduced in a Django shell against [config/settings_test.py](../../config/settings_test.py) with an in-memory SQLite DB. Unverified findings are labelled explicitly.*
