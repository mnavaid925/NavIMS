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
