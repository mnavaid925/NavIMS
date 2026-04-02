Here is the text extracted from the image:

### **Workflow Orchestration**

**1. Plan Mode Default**

* Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
* If something goes sideways, STOP and re-plan immediately – don't keep pushing
* Use plan mode for verification steps, not just building
* Write detailed specs upfront to reduce ambiguity

**2. Subagent Strategy**

* Use subagents liberally to keep main context window clean
* Offload research, exploration, and parallel analysis to subagents
* For complex problems, throw more compute at it via subagents
* One task per subagent for focused execution

**3. Self-Improvement Loop**

* After ANY correction from the user: update `.claude/tasks/lessons.md` with the pattern
* Write rules for yourself that prevent the same mistake
* Ruthlessly iterate on these lessons until mistake rate drops
* Review lessons at session start for relevant project

**4. Verification Before Done**

* Never mark a task complete without proving it works
* Diff behavior between main and your changes when relevant
* Ask yourself: "Would a staff engineer approve this?"
* Run tests, check logs, demonstrate correctness

**5. Demand Elegance (Balanced)**

* For non-trivial changes: pause and ask "is there a more elegant way?"
* If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
* Skip this for simple, obvious fixes – don't over-engineer
* Challenge your own work before presenting it

**6. Autonomous Bug Fixing**

* When given a bug report: just fix it. Don't ask for hand-holding
* Point at logs, errors, failing tests – then resolve them
* Zero context switching required from the user
* Go fix failing CI tests without being told how

---

### **Task Management**

1. **Plan First**: Write plan to `.claude/tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `.claude/tasks/todo.md`
6. **Capture Lessons**: Update `.claude/tasks/lessons.md` after corrections

---

### **Core Principles**

* **Simplicity First**: Make every change as simple as possible. Impact minimal code.
* **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
* **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

---

### GIT Commit Rule

* Whenever you create a new file or update a file or delete a file.
* Provide me git commit seperate for each file at the end. So, I will commit by my self.
* git commit should be one line only.
* eg: 
git add 'src/file.js'
git commit -m 'some example changes'.

---

### Filter Implementation Rules (Preventing Recurring Issues)

Every list page in this application MUST have working filters. When creating or modifying any list view/template, follow these mandatory steps:

1. **View must pass ALL context needed by template filters:**
   - For status dropdowns: pass `status_choices` (from `Model.STATUS_CHOICES`)
   - For FK dropdowns (categories, items, vendors, warehouses): pass the queryset to the template
   - For type/method dropdowns: pass the model's `CHOICES` constant
   - Never assume the template will get data it wasn't explicitly passed in the view context

2. **Template filter comparison rules:**
   - For string fields: `{% if request.GET.status == value %}selected{% endif %}`
   - For FK/pk fields: use `|stringformat:"d"` — NEVER use `|slugify` for pk comparison
   - Example: `{% if request.GET.category == cat.pk|stringformat:"d" %}selected{% endif %}`

3. **View filter logic:**
   - Always parse GET params and apply to queryset BEFORE pagination
   - Search: `request.GET.get('q', '').strip()` with `Q()` lookups
   - Status: `request.GET.get('status', '')` with `qs.filter(status=value)`
   - Active/Inactive: map `'active'`/`'inactive'` to `is_active=True/False`

4. **Template variable naming must match view context:**
   - If view passes `suggestions`, template must use `{% for r in suggestions %}`
   - If model field is `suggested_quantity`, template must use `r.suggested_quantity` (not `r.suggested_qty`)
   - If view passes `stats` dict, template accesses `stats.pending` (not `pending_count`)

5. **Badge values must match model CHOICES:**
   - Template badge conditions must use exact model choice values (e.g., `'weighted_avg'` not `'weighted_average'`)
   - Always include an `{% else %}` fallback: `{{ obj.get_field_display }}`

Run the `/frontend-design` skill for the full pattern reference.

---

### CRUD Completeness Rules (Preventing Missing Actions)

Every new module MUST include all CRUD operations from the start. Never ship a module with only list/add/view — Edit and Delete are mandatory.

1. **Every model that has a list page MUST have these views:**
   - `list_view` — with search + filters
   - `create_view` — add form
   - `detail_view` — read-only detail page (for models with enough fields)
   - `edit_view` — edit form (same template as create, pre-filled)
   - `delete_view` — POST-only with confirmation, redirects to list

2. **Every list template MUST have an Actions column with:**
   - View button (eye icon) — links to detail page
   - Edit button (pencil icon) — links to edit form
   - Delete button (bin icon) — POST form with `onclick="return confirm('...')"` and `{% csrf_token %}`
   - Conditional display: wrap Edit/Delete in `{% if obj.status == 'draft' %}` when status-dependent

3. **Every detail template MUST have an Actions sidebar with:**
   - Edit button — links to edit form (conditional on status)
   - Delete button — POST form with confirm dialog (conditional on status)
   - Back to List link

4. **Delete view pattern:**
   ```python
   @login_required
   def model_delete_view(request, pk):
       obj = get_object_or_404(Model, pk=pk, tenant=request.tenant)
       if request.method == 'POST':
           obj.delete()
           messages.success(request, 'Deleted successfully.')
           return redirect('app:model_list')
       return redirect('app:model_list')
   ```

5. **Delete URL pattern:**
   - Always add: `path('models/<int:pk>/delete/', views.model_delete_view, name='model_delete')`

---

### Seed Command Rules (Preventing Data Issues)

1. **Idempotent by default:**
   - Seed commands MUST be safe to run multiple times without `--flush`
   - Use `get_or_create` for models with unique constraints
   - For models with auto-generated numbers (PR-00001, PO-00001), check existence before creating:
     ```python
     existing = Model.objects.filter(tenant=tenant, number=number).first()
     if existing:
         results.append(existing)
         continue
     ```
   - Never use bare `.save()` or `.create()` for models with unique_together constraints

2. **Always skip if data exists:**
   - Check `if Model.objects.filter(tenant=tenant).exists()` at the start
   - Print a warning: `"Data already exists. Use --flush to re-seed."`

3. **Print login instructions:**
   - After seeding, always print which tenant admin accounts to use
   - Always warn: `"Superuser 'admin' has no tenant — data won't appear when logged in as admin"`

4. **`__init__.py` files:**
   - When creating `management/commands/` directories, ALWAYS create both:
     - `management/__init__.py`
     - `management/commands/__init__.py`

---

### Multi-Tenancy Rules (Preventing Data Visibility Issues)

1. **Superuser has no tenant:**
   - The `admin` superuser has `tenant=None`
   - All procurement/module views filter by `tenant=request.tenant`
   - When `request.tenant` is `None`, queries return empty results — this is BY DESIGN
   - Always instruct users to log in as a **tenant admin** (e.g., `admin_<slug>`) to see module data

2. **Every view MUST filter by tenant:**
   - `Model.objects.filter(tenant=request.tenant)` — no exceptions
   - Never use `Model.objects.all()` in tenant-scoped views

3. **Every model MUST have a tenant FK:**
   - Except User, Role (which have it already) and pure join/through tables
   - Always include: `tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE, related_name='...')`

---

### Vulnerability
When you find a security vulnerability, flag it immediately with a WARNING comment and suggest a secure alternative. Never implement insecure patterns even if asked.
