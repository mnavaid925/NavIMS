# Product & Catalog Management — Comprehensive SQA Test Report

**Module:** `catalog/` (Module 2 — Product & Catalog Management)
**Framework:** Django 4.2, Bootstrap 5, SQLite/PostgreSQL
**Scope:** Categories, Products, Product Attributes (EAV), Product Images, Product Documents
**Test Engineer:** Senior SQA (15+ yrs) — NavIMS
**Report Date:** 2026-04-17

---

## 1. Module Analysis

### 1.1 Architecture Overview

| Layer | Artifact | Purpose |
|---|---|---|
| Models | [catalog/models.py](catalog/models.py) | 5 models: `Category`, `Product`, `ProductAttribute`, `ProductImage`, `ProductDocument` |
| Views | [catalog/views.py](catalog/views.py) | 14 function-based views, `@login_required` |
| Forms | [catalog/forms.py](catalog/forms.py) | 5 ModelForms + `ProductAttributeFormSet` (inline formset) |
| URLs | [catalog/urls.py](catalog/urls.py) | 14 URL patterns under namespace `catalog:` |
| Templates | [templates/catalog/](templates/catalog/) | 6 HTML templates |
| Seed | [catalog/management/commands/seed_catalog.py](catalog/management/commands/seed_catalog.py) | Demo data seeder |

### 1.2 Inputs, Outputs & Dependencies

- **Inputs:** HTTP GET/POST (search, filter, form data), multipart/form-data (file uploads), URL path params (`<int:pk>`).
- **Outputs:** Rendered HTML, redirect responses, flash messages, persisted DB rows, files under `media/products/images/` and `media/products/documents/`.
- **Dependencies:**
  - `core.Tenant` (multi-tenant isolation), `request.tenant` set by `TenantMiddleware`.
  - `django.contrib.auth` (`@login_required`).
  - `Pillow` (ImageField), `django-crispy-forms` (rendering), storage backend (local `media/` by default).

### 1.3 Key Business Rules

| Rule | Location |
|---|---|
| Max 3-level category hierarchy (department → category → subcategory) | [catalog/models.py:40-49](catalog/models.py#L40-L49), [catalog/forms.py:54-55](catalog/forms.py#L54-L55) |
| Slug auto-generated from name (regenerated every save) | [catalog/models.py:40-42](catalog/models.py#L40-L42) |
| `unique_together(tenant, slug)` Category; `(tenant, sku)` Product | [catalog/models.py:34](catalog/models.py#L34), [catalog/models.py:121](catalog/models.py#L121) |
| Circular hierarchy prevention (exclude self + descendants) | [catalog/forms.py:36-53](catalog/forms.py#L36-L53) |
| Only one primary image per product | [catalog/models.py:184-190](catalog/models.py#L184-L190) |
| Category deletion blocked if children OR products exist | [catalog/views.py:134-152](catalog/views.py#L134-L152) |
| Markup auto-compute when cost + retail provided | [catalog/forms.py:178-182](catalog/forms.py#L178-L182) |
| Wholesale ≤ retail, cost ≤ retail | [catalog/forms.py:185-190](catalog/forms.py#L185-L190) |
| Image: whitelist (jpg, jpeg, png, gif, webp, bmp), max 5 MB | [catalog/forms.py:7,256-263](catalog/forms.py#L256-L263) |
| Document: whitelist (pdf, doc, docx, xls, xlsx, csv, txt, rtf, odt), max 20 MB | [catalog/forms.py:8,286-293](catalog/forms.py#L286-L293) |
| Every view filters `Model.objects.filter(tenant=request.tenant)` | throughout [catalog/views.py](catalog/views.py) |

### 1.4 Risk Profile (pre-test)

- **High:** File-upload surface (images + documents) — extension-only validation.
- **High:** Multi-tenant isolation — any missed filter = cross-tenant leak.
- **Medium:** Category tree integrity (circular refs, orphaned children).
- **Medium:** Markup auto-compute overwriting user-entered `0`.
- **Low:** Slug collision on identical/unicode-only category names.

---

## 2. Test Plan

### 2.1 Testing Types in Scope

| Type | Coverage |
|---|---|
| **Unit** | Model `save()` overrides, `full_path`, `primary_image`, form `clean()`, descendant walk |
| **Integration** | View + Form + Model + DB flow per CRUD path |
| **Functional** | End-to-end user journeys (create category → create product → upload image → delete) |
| **Regression** | Full suite on every merge; filters, pagination, CRUD completeness |
| **Boundary** | SKU/name 255 chars, decimal 12,2 / 10,3, file size 5 MB / 20 MB |
| **Edge** | Empty strings, null FKs, unicode, emoji, whitespace |
| **Negative** | Invalid ext, oversize file, duplicate SKU, circular parent, cross-tenant pk |
| **Security (OWASP)** | A01 (AuthN/Z/IDOR), A03 (XSS), A04 (Insecure Design), A05 (Misconfig), A08 (File Upload), A09 (Logging), CSRF |
| **Performance** | 10k products listing, N+1 audit |
| **Scalability** | Pagination at 100k rows |
| **Reliability** | Orphan file cleanup, atomic form+formset save |
| **Usability** | Filter retention across pagination, error-message clarity, mobile responsive |
| **Compliance** | SaaS data boundary; audit trail |

### 2.2 Out of Scope

Django framework internals, third-party package bugs (Pillow, crispy-forms), browser rendering beyond README-listed browsers.

### 2.3 Entry / Exit Criteria

- **Entry:** Code on `main`, migrations applied, `seed_catalog` loaded, login as `admin_acme`/`demo123`.
- **Exit:** ≥ 98 % functional pass rate; 0 open Critical/High defects; security findings triaged.

### 2.4 Environments

| Env | Purpose | DB | Data |
|---|---|---|---|
| Local Dev | Unit + smoke | SQLite | `seed_catalog` |
| CI (pytest) | Automated suite | SQLite in-memory | factory-boy |
| Staging | Functional + UAT | PostgreSQL | anonymised clone |
| Prod-mirror | Performance | PostgreSQL | 100k products seed |

---

## 3. Test Scenarios

### 3.1 Categories (18)

| # | Scenario | Type |
|---|---|---|
| C-01 | List renders tenant categories with annotated product count | Positive |
| C-02 | Create Department (no parent) → level `department` | Positive |
| C-03 | Create Category under Department → level `category` | Positive |
| C-04 | Create Sub-category under Category → level `subcategory` | Positive |
| C-05 | Search by partial name (case-insensitive) | Positive |
| C-06 | Filter by level + status combined; persists through pagination | Positive |
| C-07 | Duplicate name same tenant → slug collision on unique_together | Negative |
| C-08 | Set parent to self (edit) | Negative |
| C-09 | Set parent to descendant (edit) — circular | Negative |
| C-10 | 4th level nesting — parent dropdown filters out subcategories | Negative |
| C-11 | Rename → slug regenerates; uniqueness preserved | Boundary |
| C-12 | Delete empty category | Positive |
| C-13 | Delete with children → blocked | Negative |
| C-14 | Delete with products → blocked | Negative |
| C-15 | Cross-tenant PK → 404 | Security/IDOR |
| C-16 | XSS payload in name → escaped | Security |
| C-17 | Name 256 chars → error | Boundary |
| C-18 | Unicode/emoji name → saves; slug fallback check | Edge |

### 3.2 Products (22)

| # | Scenario | Type |
|---|---|---|
| P-01 | Create with minimum required fields | Positive |
| P-02 | Create with all fields + 3 attributes | Positive |
| P-03 | Duplicate SKU same tenant → error | Negative |
| P-04 | Same SKU across tenants → allowed | Positive |
| P-05 | Auto markup when cost=100, retail=150 → 50.00 % | Positive |
| P-06 | Wholesale > retail → error | Negative |
| P-07 | Cost > retail → error | Negative |
| P-08 | Negative price via crafted POST (bypass `min=0`) | Negative |
| P-09 | Decimal > 12 digits / > 2 dp | Boundary |
| P-10 | Weight 3 dp precision | Boundary |
| P-11 | Search by name, SKU, barcode (Q-OR) | Positive |
| P-12 | Filter status + category + pagination | Positive |
| P-13 | Invalid status param (`?status=EVIL`) → ignored | Security/Negative |
| P-14 | IDOR: assign other-tenant category via crafted POST | Security |
| P-15 | Edit: attribute add/update/delete via formset | Positive |
| P-16 | Delete product → cascades to attrs/images/docs | Positive |
| P-17 | `is_primary` toggle: exactly one primary | Positive |
| P-18 | Upload image > 5 MB → error | Negative |
| P-19 | Disallowed ext (.exe, .svg, .php) → error | Security |
| P-20 | Polyglot image (GIF89a + JS) → evaluate response | Security |
| P-21 | Document > 20 MB or bad ext → error | Negative |
| P-22 | Detail page query count (N+1 guard) | Performance |

### 3.3 Cross-cutting / Non-Functional (10)

| # | Scenario | Type |
|---|---|---|
| X-01 | Unauthenticated access → redirect to login | Security/AuthN |
| X-02 | Superuser (tenant=None) sees empty lists — documented | Functional |
| X-03 | CSRF token required on POSTs | Security |
| X-04 | Path traversal in uploaded filename | Security |
| X-05 | Concurrent delete of same product → 404 on 2nd | Reliability |
| X-06 | Pagination `page=9999 / -1 / abc` fallback | Edge |
| X-07 | Re-upload same filename → storage rename | Reliability |
| X-08 | Delete leaves orphan file on disk (defect D-03) | Reliability |
| X-09 | 10k products list < 800 ms p95 | Performance |
| X-10 | No RBAC — any logged-in tenant user can CRUD | Security/AuthZ |

---

## 4. Detailed Test Cases

### 4.1 Category Test Cases

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-CAT-001** | Create Department category | Logged in as `admin_acme`; no slug `electronics` exists | 1. Go to `/catalog/categories/create/` 2. Name=Electronics, Parent=blank 3. Save | Name=`Electronics` | Redirect to list; flash success; row with `level='department'`, `slug='electronics'`, `tenant=acme` | Category exists; 3 levels possible below |
| **TC-CAT-002** | Create Sub-category (3rd level) | "Electronics" + "Laptops" exist | 1. Open create 2. Name=Gaming Laptops, Parent=Laptops | Name=`Gaming Laptops` | Row with `level='subcategory'`; `full_path` = "Electronics > Laptops > Gaming Laptops" | 3-level tree populated |
| **TC-CAT-003** | Prevent 4-level nesting | Sub-category "Gaming Laptops" exists | 1. Open create 2. Inspect Parent dropdown | — | Sub-category is NOT in Parent options (only `department`+`category`) | Hierarchy capped at 3 |
| **TC-CAT-004** | Block circular hierarchy on edit | "Electronics" has child "Laptops" which has child "Gaming" | 1. Edit Electronics 2. Inspect Parent dropdown | — | Parent dropdown excludes self AND all descendants | Circular refs impossible |
| **TC-CAT-005** | Duplicate slug same tenant | "Electronics" exists | 1. Create "electronics" (lowercase) | Name=`electronics` | `IntegrityError` surfaced as form error; no row created | DB unchanged |
| **TC-CAT-006** | Delete with children blocked | Electronics has child Laptops | 1. Detail page → Delete, confirm | POST | Redirect to detail; error "Cannot delete... has 1 child category" | Data intact |
| **TC-CAT-007** | Delete with products blocked | Laptops has 3 products | 1. Delete Laptops | POST | Error "has 3 products" | Data intact |
| **TC-CAT-008** | Combined search + level filter | 10 categories seeded | 1. GET `/categories/?q=lap&level=category` | — | Only "Laptops" shown; hidden inputs preserve both filters | Filter state retained |
| **TC-CAT-009** | Cross-tenant IDOR | `admin_global` has category pk=999 | 1. As `admin_acme` GET `/catalog/categories/999/` | pk=999 | HTTP 404 | No data leak |
| **TC-CAT-010** | XSS in name | — | 1. Create with name `<script>alert('x')</script>` | Payload | Saved; rendered escaped (`&lt;script&gt;`); no JS execution | Stored safely |
| **TC-CAT-011** | Max-length name | — | 1. Submit 256-char name | `"A"*256` | Form error "at most 255 characters" | Not created |
| **TC-CAT-012** | Unicode & emoji | — | 1. Create "电子产品 🚀" | UTF-8 | Saved; slug non-empty (may need fallback — see D-07) | Check slug integrity |

### 4.2 Product Test Cases

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-PROD-001** | Create with mandatory + pricing | Category "Laptops" exists | 1. `/products/create/` 2. SKU=LAP-001, Name="ThinkPad X1", Cost=800, Retail=1200 3. Save | SKU=`LAP-001` | Redirect to detail; `markup_percentage` auto-filled to `50.00` | Product saved |
| **TC-PROD-002** | Create with 3 attributes (formset) | — | 1. Fill product 2. Add attrs: Color=Black/text, Warranty=24/number, RoHS=Yes/boolean | 3 rows | Product + 3 `ProductAttribute` rows with `tenant` set | Attributes linked |
| **TC-PROD-003** | Duplicate SKU same tenant | `LAP-001` exists | 1. Create new with SKU `LAP-001` | Duplicate | Unique_together error | DB unchanged |
| **TC-PROD-004** | Same SKU across tenants | `LAP-001` in Acme | 1. As `admin_global` create `LAP-001` | Same SKU, other tenant | Saved (tenant isolation) | Both tenants have their own `LAP-001` |
| **TC-PROD-005** | Wholesale > retail rejected | — | 1. Purchase=100, Wholesale=200, Retail=150 | Wholesale>Retail | Error on `wholesale_price`: "should not exceed retail price" | Not saved |
| **TC-PROD-006** | Cost > retail rejected | — | 1. Purchase=200, Retail=150 | Cost>Retail | Error on `purchase_cost`: "negative margin" | Not saved |
| **TC-PROD-007** | Negative price via crafted POST | — | 1. POST `retail_price=-10` bypassing HTML5 | `-10.00` | **DEFECT D-02** — saves negative (no server-side validator) | Expected: error |
| **TC-PROD-008** | Decimal precision weight | — | 1. Weight=1.2345 | 4 dp input | Rounded to 3 dp or validation error | Boundary |
| **TC-PROD-009** | 13-digit retail | — | 1. Retail=99999999999.99 | Overflow | Error "no more than 12 digits" | Rejected |
| **TC-PROD-010** | Search name/SKU/barcode | Products seeded | 1. GET `/products/?q=LAP` | `q=LAP` | All products with LAP in any of 3 fields | Correct filter |
| **TC-PROD-011** | Invalid status param | — | 1. GET `/products/?status=__EVIL__` | Tampered | Whitelist in view; filter ignored; full list | No crash |
| **TC-PROD-012** | IDOR — other-tenant category FK | Other tenant category pk=50 | 1. POST with `category=50` | Tampered FK | **DEFECT D-05 adjacent** — ModelChoiceField queryset protects; confirm with test | Expected: rejected |
| **TC-PROD-013** | Edit: delete attribute via formset | Product has 3 attrs | 1. Mark DELETE on 1, save | Formset delete marker | Attribute row removed | Count -1 |
| **TC-PROD-014** | Delete cascades | Product has 2 images, 1 doc, 3 attrs | 1. POST `/products/<pk>/delete/` | — | All children DB-deleted; files remain on disk (D-03) | Disk leak flagged |
| **TC-PROD-015** | CSRF missing | — | 1. POST delete without token | No token | HTTP 403 | CSRF enforced |
| **TC-PROD-016** | Markup=0 overwritten | — | 1. Purchase=100, Retail=150, Markup=0 (intentional) | Markup=0 | **DEFECT D-04** — `if not markup:` treats 0 as falsy → overwritten to 50 | Document |
| **TC-PROD-017** | Filter retention in pagination | 50 products | 1. Apply filters → click page 2 | — | Page-2 links preserve `q`, `status`, `category` | UX correct |

### 4.3 Product Image Test Cases

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result | Post-conditions |
|---|---|---|---|---|---|---|
| **TC-IMG-001** | Upload valid JPG < 5 MB | Product exists | 1. Detail page upload 2 MB JPG with caption | `test.jpg` 2 MB | Flash success; file under `media/products/images/` | Image + file persisted |
| **TC-IMG-002** | Upload at 5 MB boundary | — | 1. Upload 5.0 MB PNG | 5242880 B | Accepted (size check is `>` not `>=`) | Stored |
| **TC-IMG-003** | Upload 5.01 MB | — | 1. Upload oversize | 5246000 B | Error "under 5 MB" | Rejected |
| **TC-IMG-004** | Disallowed ext `.svg` | — | 1. Upload `logo.svg` | SVG | FileExtensionValidator error | SVG excluded — mitigates embedded scripts |
| **TC-IMG-005** | Polyglot attack (GIF89a + JS) | — | 1. Upload `exploit.gif` with GIF89a header + script | Polyglot | Passes ext; served as `image/gif` — XSS risk if embedded | **Finding D-01** — add magic-byte check + nosniff |
| **TC-IMG-006** | Primary toggle unsets siblings | Product already has 1 primary | 1. Upload new with primary=true | 2nd primary | Old row `is_primary=False`; new row `True` | Exactly 1 primary |
| **TC-IMG-007** | Delete image (POST) | Image exists | 1. POST `/products/<pk>/images/<img_pk>/delete/` | — | DB row deleted; flash success | DB clean |
| **TC-IMG-008** | Delete via GET refused | — | 1. GET delete URL | — | Redirect to detail; no action | Idempotent GET |
| **TC-IMG-009** | Cross-tenant image delete | Two tenants | 1. As A, POST delete of tenant B's image | Tampered pk | HTTP 404 | No cross-tenant delete |
| **TC-IMG-010** | Path traversal filename | — | 1. Upload `../../evil.jpg` | Malicious | Django storage sanitises via `get_valid_name()` | No traversal |

### 4.4 Product Document Test Cases

| ID | Description | Pre-conditions | Steps | Test Data | Expected Result |
|---|---|---|---|---|---|
| **TC-DOC-001** | PDF ≤ 20 MB | Product exists | Upload 5 MB PDF | `manual.pdf` | Accepted |
| **TC-DOC-002** | > 20 MB | — | Upload 20.5 MB | Oversize | Error "under 20 MB" |
| **TC-DOC-003** | `.exe` disallowed | — | `setup.exe` | Bad ext | FileExtensionValidator error |
| **TC-DOC-004** | `.html` disallowed | — | `readme.html` | Not in whitelist | Rejected — safe |
| **TC-DOC-005** | Missing title | — | Empty title | `title=""` | Required-field error |
| **TC-DOC-006** | Cross-tenant delete | — | As A, delete B's doc | Tampered | HTTP 404 |

### 4.5 Non-Functional Test Cases

| ID | Description | Tool | Metric | Target | Method |
|---|---|---|---|---|---|
| **TC-NFR-001** | Product list 10k rows | Locust + DDT | p95 latency | < 800 ms | 50 concurrent users |
| **TC-NFR-002** | N+1 on list | `django_assert_max_num_queries` | Query count | ≤ 10 | `with django_assert_max_num_queries(10)` |
| **TC-NFR-003** | Image upload throughput | Locust | rps | 20 rps | Sustained 5 min |
| **TC-NFR-004** | Category detail queries | Single request | Queries | ≤ 4 | `select_related('parent__parent')` |
| **TC-NFR-005** | Responsive layout < 375 px | DevTools | No horizontal scroll | Pass | Manual |

### 4.6 Security Test Cases (OWASP-aligned)

| ID | OWASP | Description | Expected |
|---|---|---|---|
| **TC-SEC-001** | A01 | Unauthenticated access to all URLs | 302 → login |
| **TC-SEC-002** | A01 | Cross-tenant IDOR (category/product/image/doc) | 404 |
| **TC-SEC-003** | A01 | No RBAC enforcement (all tenant users CRUD) | **Flag D-05** |
| **TC-SEC-004** | A03 | Stored XSS in name/description/caption/barcode/brand | Escaped on render |
| **TC-SEC-005** | A03 | Query tampering `?status=<script>`, SQLi | Whitelist / ORM parameterised |
| **TC-SEC-006** | A04 | Markup auto-compute overwrites user 0 | **Flag D-04** |
| **TC-SEC-007** | A05 | `DEBUG=False`, secure headers | Pass |
| **TC-SEC-008** | A07 | AuthN brute force | Out of module scope |
| **TC-SEC-009** | A08 | File upload — polyglot, MIME spoof | **Flag D-01** |
| **TC-SEC-010** | A09 | Destructive events audit-logged | **Flag D-06** |
| **TC-SEC-011** | — | CSRF POST without token | 403 |
| **TC-SEC-012** | A05 | X-Frame-Options (clickjacking) | Verified via middleware |

---

## 5. Automation Strategy

### 5.1 Recommended Tools

| Layer | Tool | Reason |
|---|---|---|
| Unit / Integration | `pytest` + `pytest-django` | Idiomatic, fixtures |
| Factories | `factory_boy` + `Faker` | Deterministic test data |
| Coverage | `coverage.py` + `pytest-cov` | Branch reports |
| Browser E2E | **Playwright (Python)** | Modern, parallel, auto-wait |
| Perf / Load | `locust` | Python-native scripts |
| SAST | `bandit`, `semgrep` (django-security) | CI-pluggable |
| DAST | OWASP ZAP baseline | Nightly CI |
| Query audit | `django_assert_max_num_queries` | N+1 guard |
| Mutation | `mutmut` | Suite quality gate |

### 5.2 Suite Layout

```
catalog/tests/
  __init__.py
  conftest.py              # tenant, user, client, product, category fixtures
  factories.py             # CategoryFactory, ProductFactory, ...
  test_models.py           # TC-CAT-002, P-01, P-17, slug/level logic
  test_forms.py            # TC-PROD-005/006/007, TC-CAT-003/004
  test_views_category.py   # TC-CAT-001..012
  test_views_product.py    # TC-PROD-001..017
  test_views_image.py      # TC-IMG-001..010
  test_views_document.py   # TC-DOC-001..006
  test_security.py         # TC-SEC-001..012
  test_performance.py      # TC-NFR-002
e2e/
  test_catalog_flow.py     # Playwright golden path
locust/
  locustfile_products.py   # TC-NFR-001, -003
```

### 5.3 Sample — `conftest.py`

```python
import pytest
from django.contrib.auth import get_user_model
from core.models import Tenant
from catalog.models import Category, Product

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
        username="qa_user", password="qa_pass_123!", tenant=tenant,
    )


@pytest.fixture
def client_logged_in(client, user):
    client.login(username="qa_user", password="qa_pass_123!")
    return client


@pytest.fixture
def department(db, tenant):
    return Category.objects.create(tenant=tenant, name="Electronics")


@pytest.fixture
def category(db, tenant, department):
    return Category.objects.create(tenant=tenant, name="Laptops", parent=department)


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, sku="LAP-001", name="ThinkPad X1",
        category=category, purchase_cost=800, retail_price=1200, status="active",
    )
```

### 5.4 Sample — Model Unit Tests

```python
import pytest
from catalog.models import Category, ProductImage


@pytest.mark.django_db
class TestCategoryHierarchy:
    def test_department_level_auto_set(self, tenant):
        cat = Category.objects.create(tenant=tenant, name="Apparel")
        assert cat.level == "department"
        assert cat.slug == "apparel"

    def test_category_level_under_department(self, tenant, department):
        cat = Category.objects.create(tenant=tenant, name="Laptops", parent=department)
        assert cat.level == "category"

    def test_subcategory_level(self, tenant, category):
        sub = Category.objects.create(tenant=tenant, name="Gaming", parent=category)
        assert sub.level == "subcategory"

    def test_full_path(self, tenant, category):
        sub = Category.objects.create(tenant=tenant, name="Gaming", parent=category)
        assert sub.full_path == "Electronics > Laptops > Gaming"

    def test_slug_regenerated_on_rename(self, tenant):
        c = Category.objects.create(tenant=tenant, name="Old Name")
        c.name = "New Name"
        c.save()
        assert c.slug == "new-name"


@pytest.mark.django_db
class TestPrimaryImageInvariant:
    def test_only_one_primary(self, product, tenant, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        img1 = ProductImage.objects.create(
            tenant=tenant, product=product, image="a.jpg", is_primary=True,
        )
        img2 = ProductImage.objects.create(
            tenant=tenant, product=product, image="b.jpg", is_primary=True,
        )
        img1.refresh_from_db()
        assert img1.is_primary is False
        assert img2.is_primary is True
```

### 5.5 Sample — Form Validation Tests

```python
import pytest
from decimal import Decimal
from catalog.forms import ProductForm, CategoryForm


@pytest.mark.django_db
class TestProductFormPricing:
    def _payload(self, **overrides):
        base = dict(
            sku="TC-001", name="Test", status="draft",
            purchase_cost="100.00", retail_price="150.00",
            wholesale_price="120.00", markup_percentage="",
            is_active=True,
        )
        base.update(overrides)
        return base

    def test_auto_markup_calculation(self, tenant):
        form = ProductForm(data=self._payload(), tenant=tenant)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["markup_percentage"] == Decimal("50.00")

    def test_wholesale_exceeds_retail_rejected(self, tenant):
        form = ProductForm(data=self._payload(wholesale_price="200.00"), tenant=tenant)
        assert not form.is_valid()
        assert "wholesale_price" in form.errors

    def test_cost_exceeds_retail_rejected(self, tenant):
        form = ProductForm(data=self._payload(purchase_cost="200.00"), tenant=tenant)
        assert not form.is_valid()
        assert "purchase_cost" in form.errors


@pytest.mark.django_db
class TestCategoryCircularPrevention:
    def test_descendants_excluded_from_parent_choices(self, tenant, department, category):
        form = CategoryForm(instance=department, tenant=tenant)
        parent_pks = set(form.fields["parent"].queryset.values_list("pk", flat=True))
        assert department.pk not in parent_pks
        assert category.pk not in parent_pks

    def test_only_dept_and_cat_levels_allowed_as_parent(self, tenant, category):
        category.children.create(tenant=tenant, name="Gaming")
        form = CategoryForm(tenant=tenant)
        allowed_levels = set(
            form.fields["parent"].queryset.values_list("level", flat=True)
        )
        assert "subcategory" not in allowed_levels
```

### 5.6 Sample — View / Integration + Security

```python
import pytest
from django.urls import reverse
from catalog.models import Product


@pytest.mark.django_db
class TestProductCRUD:
    def test_list_requires_login(self, client):
        r = client.get(reverse("catalog:product_list"))
        assert r.status_code == 302 and "/login" in r.url

    def test_create_product_happy_path(self, client_logged_in, tenant, category):
        r = client_logged_in.post(
            reverse("catalog:product_create"),
            data={
                "sku": "NEW-001", "name": "Test Widget",
                "status": "active", "category": category.pk,
                "purchase_cost": "10.00", "retail_price": "15.00",
                "wholesale_price": "12.00", "markup_percentage": "",
                "is_active": "on",
                "attributes-TOTAL_FORMS": "0",
                "attributes-INITIAL_FORMS": "0",
                "attributes-MIN_NUM_FORMS": "0",
                "attributes-MAX_NUM_FORMS": "1000",
            },
        )
        assert r.status_code == 302
        assert Product.objects.filter(tenant=tenant, sku="NEW-001").exists()


@pytest.mark.django_db
class TestTenantIsolation:
    def test_cannot_view_other_tenant_product(self, client_logged_in, other_tenant):
        foreign = Product.objects.create(
            tenant=other_tenant, sku="X-1", name="Foreign", status="active",
        )
        r = client_logged_in.get(
            reverse("catalog:product_detail", args=[foreign.pk])
        )
        assert r.status_code == 404

    def test_cannot_delete_other_tenant_product(self, client_logged_in, other_tenant):
        foreign = Product.objects.create(
            tenant=other_tenant, sku="X-2", name="Foreign", status="active",
        )
        r = client_logged_in.post(
            reverse("catalog:product_delete", args=[foreign.pk])
        )
        assert r.status_code == 404
        assert Product.objects.filter(pk=foreign.pk).exists()


@pytest.mark.django_db
class TestFilterHardening:
    def test_invalid_status_filter_ignored(self, client_logged_in, product):
        r = client_logged_in.get(
            reverse("catalog:product_list") + "?status=__EVIL__"
        )
        assert r.status_code == 200
        assert product.name.encode() in r.content

    def test_xss_in_name_escaped(self, client_logged_in, tenant, category):
        Product.objects.create(
            tenant=tenant, sku="XSS-1", name="<script>alert(1)</script>",
            category=category, status="active",
        )
        r = client_logged_in.get(reverse("catalog:product_list"))
        assert b"<script>alert(1)</script>" not in r.content
        assert b"&lt;script&gt;" in r.content
```

### 5.7 Sample — File Upload Security

```python
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from catalog.models import ProductImage


def _jpeg_bytes(size=1024):
    return b"\xff\xd8\xff\xe0" + b"\x00" * (size - 4) + b"\xff\xd9"


@pytest.mark.django_db
class TestImageUpload:
    def test_upload_valid_jpg(self, client_logged_in, product, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        upload = SimpleUploadedFile("ok.jpg", _jpeg_bytes(), content_type="image/jpeg")
        r = client_logged_in.post(
            reverse("catalog:product_image_upload", args=[product.pk]),
            data={"image": upload, "caption": "Hero", "is_primary": "on"},
        )
        assert r.status_code == 302
        assert ProductImage.objects.filter(product=product).count() == 1

    def test_reject_oversize(self, client_logged_in, product, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        big = SimpleUploadedFile(
            "big.jpg", b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )
        client_logged_in.post(
            reverse("catalog:product_image_upload", args=[product.pk]),
            data={"image": big},
        )
        assert ProductImage.objects.filter(product=product).count() == 0

    @pytest.mark.parametrize("name", ["evil.exe", "shell.php", "logo.svg"])
    def test_reject_bad_extensions(self, client_logged_in, product, name, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        bad = SimpleUploadedFile(name, b"payload", content_type="image/jpeg")
        client_logged_in.post(
            reverse("catalog:product_image_upload", args=[product.pk]),
            data={"image": bad},
        )
        assert ProductImage.objects.filter(product=product).count() == 0
```

### 5.8 Sample — N+1 / Performance Guard

```python
import pytest
from django.urls import reverse
from catalog.models import Product


@pytest.mark.django_db
def test_product_list_no_n_plus_one(
    client_logged_in, tenant, category, django_assert_max_num_queries,
):
    for i in range(30):
        Product.objects.create(
            tenant=tenant, sku=f"SKU-{i:03d}", name=f"Item {i}",
            category=category, status="active",
        )
    with django_assert_max_num_queries(10):
        r = client_logged_in.get(reverse("catalog:product_list"))
    assert r.status_code == 200
```

### 5.9 Sample — Playwright E2E

```python
import re, pytest
from playwright.sync_api import expect

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def authed_page(browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(f"{BASE}/accounts/login/")
    page.fill("[name=username]", "admin_acme")
    page.fill("[name=password]", "demo123")
    page.click("button[type=submit]")
    expect(page).to_have_url(re.compile(r".*/dashboard/?$"))
    yield page
    ctx.close()


def test_create_product_end_to_end(authed_page):
    page = authed_page
    page.goto(f"{BASE}/catalog/products/create/")
    page.fill("[name=sku]", "E2E-001")
    page.fill("[name=name]", "E2E Widget")
    page.select_option("[name=status]", "active")
    page.fill("[name=purchase_cost]", "10")
    page.fill("[name=retail_price]", "15")
    page.click("button[type=submit]:has-text('Save')")
    expect(page).to_have_url(re.compile(r".*/catalog/products/\d+/$"))
    expect(page.locator("body")).to_contain_text("E2E Widget")
```

### 5.10 Sample — Locust Load Test

```python
from locust import HttpUser, task, between


class CatalogUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post(
            "/accounts/login/",
            data={"username": "admin_acme", "password": "demo123"},
        )

    @task(5)
    def list_products(self):
        self.client.get("/catalog/products/")

    @task(3)
    def search_products(self):
        self.client.get("/catalog/products/?q=laptop")

    @task(1)
    def list_categories(self):
        self.client.get("/catalog/categories/")
```

---

## 6. Defects, Risks & Recommendations

### 6.1 Defects Identified

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| **D-01** | **High (Sec — A04/A08)** | [catalog/forms.py:256-263](catalog/forms.py#L256-L263), [:286-293](catalog/forms.py#L286-L293) | File upload relies on **extension only** — polyglot/MIME bypass possible | Add magic-byte sniff (`python-magic`); verify `Pillow` can open images; keep SVG excluded; set `X-Content-Type-Options: nosniff` and CSP `img-src` |
| **D-02** | **High** | [catalog/models.py:88-91](catalog/models.py#L88-L91), [catalog/forms.py:170-192](catalog/forms.py#L170-L192) | No server-side validator blocks **negative** pricing/dimensions — HTML5 `min=0` is client-side only | Add `MinValueValidator(0)` on all pricing and measurement fields in the model |
| **D-03** | **Medium** | [catalog/views.py:291-301](catalog/views.py#L291-L301), [:329-339](catalog/views.py#L329-L339) | Deleting Product/Image/Document deletes DB row but **not** file on disk → orphan files, disk leak, GDPR residue | Use `django-cleanup` or call `instance.image.delete(save=False)` in `post_delete` signal |
| **D-04** | **Medium** | [catalog/forms.py:178-182](catalog/forms.py#L178-L182) | `if not markup:` treats user-entered `0` as missing → silently overwrites user intent | Use `cleaned_data.get('markup_percentage') in (None, "")` instead |
| **D-05** | **Medium (Sec — A01)** | all [catalog/views.py](catalog/views.py) | Only `@login_required` — no role-based permission check. Any tenant user (incl. "Viewer") can CRUD | Add `@permission_required` / custom decorator integrating with `core.Role` |
| **D-06** | **Medium (Sec — A09)** | all catalog views | Catalog CRUD not written to `core.AuditLog` — destructive actions untraceable | Emit audit events on create/update/delete |
| **D-07** | **Low** | [catalog/models.py:40-42](catalog/models.py#L40-L42) | `slugify()` of unicode-only names (e.g. `电子产品`) returns empty string → unique_together collision risk | Fallback `slug = slugify(name) or f"cat-{uuid4().hex[:8]}"` |
| **D-08** | **Low** | [catalog/views.py:28-34](catalog/views.py#L28-L34) | Triple-stacked `Count` on related joins may over-count / explode rows at deep trees | Use `Count(..., filter=Q(...))` or Subquery |
| **D-09** | **Low** | [catalog/forms.py:60-66](catalog/forms.py#L60-L66) | If `tenant=None` (super-admin) is passed, `CategoryForm.save()` fails at DB layer, not form layer | Raise `ValidationError` in `__init__` when `tenant is None` |
| **D-10** | **Low (Code smell)** | [catalog/forms.py:36-42](catalog/forms.py#L36-L42) | Recursive `_get_descendant_ids` issues N queries for N levels | CTE / `django-mptt` / `django-treebeard` |
| **D-11** | **Info / UX** | [templates/catalog/product_list.html:37-43](templates/catalog/product_list.html#L37-L43) | Three independent `<form method="get">` per filter — fragile, uses hidden inputs to sync state | Consolidate into one form with multiple selects |

### 6.2 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| File-upload RCE or stored XSS via image | Medium | High | D-01 + CSP |
| Cross-tenant leak via missed `filter(tenant=...)` in future views | Medium | Critical | Mandatory `TestTenantIsolation` for every new view; consider `TenantScopedManager` |
| Disk full from orphan media | High | Medium | D-03 + periodic janitor cron |
| Negative pricing propagating to POs / valuations | Low | High | D-02 |
| No RBAC on catalog → data-integrity regressions | High | High | D-05 |

### 6.3 Performance Bottlenecks

- Category list: triple-annotated `Count` — O(n³) join-explosion risk on deep trees.
- Product list: `categories` dropdown queryset unpaginated — fine ≤ 1k, problematic beyond.
- No explicit `db_index=True` on `Product.sku`, `Product.barcode`, `Category.slug` (beyond unique_together composite).

---

## 7. Test Coverage Estimation & Success Metrics

### 7.1 Coverage Targets

| Scope | Target |
|---|---|
| Line coverage (`coverage.py`) | ≥ **90 %** for `catalog/` |
| Branch coverage | ≥ **85 %** |
| Mutation score (`mutmut`) | ≥ **70 %** |
| Critical-path E2E | 100 % of 6 golden paths in Playwright |
| Security test count | 12 / 12 TC-SEC per release |

### 7.2 Projected Coverage by File

| File | Estimated Coverage |
|---|---|
| `catalog/models.py` | 95 % |
| `catalog/forms.py` | 93 % |
| `catalog/views.py` | 92 % |
| `catalog/urls.py` | 100 % |
| `catalog/admin.py` | 60 % (smoke only) |

### 7.3 Success Metrics

| KPI | Green | Amber | Red |
|---|---|---|---|
| Functional pass rate | ≥ 98 % | 90-97 % | < 90 % |
| Open Critical/High defects at release | 0 | ≤ 2 (with workaround) | > 2 |
| Unit+integration suite time | < 60 s | 60-180 s | > 180 s |
| E2E smoke time | < 5 min | 5-10 min | > 10 min |
| Locust p95 `/products/` @ 50 rps | < 800 ms | 800-1500 ms | > 1500 ms |
| Queries on `/products/` with seed data | ≤ 6 | 7-12 | > 12 |
| OWASP ZAP baseline High alerts | 0 | 0 | ≥ 1 |
| Regression escape rate | < 5 % | 5-10 % | > 10 % |

### 7.4 Release Exit Gate

All of the following must be true:

1. **Functional:** 100 % of TC-CAT, TC-PROD, TC-IMG, TC-DOC green.
2. **Security:** D-01, D-02, D-05, D-06 fixed OR risk-accepted with compensating control.
3. **Performance:** TC-NFR-001 and TC-NFR-002 pass at seed volume.
4. **Coverage:** ≥ 90 % lines, ≥ 85 % branches.
5. **Static Analysis:** `bandit` / `semgrep` zero High findings.
6. **Manual UAT sign-off:** tenant admin smoke across Chrome, Firefox, Safari, Edge.

---

## 8. Summary

The Product & Catalog module is **functionally complete** with solid multi-tenant scaffolding, sensible hierarchy rules, and clean form design. Eleven defects/risks identified — most notable:

- Extension-only file validation (**D-01**)
- No server-side non-negative validator on pricing (**D-02**)
- Orphan media files on delete (**D-03**)
- No RBAC beyond login (**D-05**)
- Missing audit trail on destructive ops (**D-06**)

With the proposed `pytest` + Playwright + Locust + OWASP ZAP suite, the module can be fully regressed in < 10 min per PR and can reach **≥ 90 % line coverage** with **≥ 70 % mutation score** — meeting enterprise-grade release gates.

---

*Senior SQA Review — NavIMS Catalog Module, 2026-04-17*
