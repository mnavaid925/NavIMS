"""Shared form helpers for tenant-scoped modules.

Lifted from `warehousing/forms.py:TenantUniqueCodeMixin` after the pattern
recurred in a fourth module (lot_tracking — for `serial_number` rather than
`code`). Accepts a configurable `tenant_unique_field` so the same mixin
handles any `(tenant, X)` unique_together constraint.
"""
from django.core.exceptions import ValidationError


class TenantUniqueCodeMixin:
    """Enforce `unique_together = ('tenant', <field>)` at the form layer.

    Django's `ModelForm.validate_unique()` excludes any model field that is
    not rendered on the form — so when `tenant` is populated inside `save()`
    rather than being a form field, the partial unique check passes and the
    duplicate reaches the DB as an IntegrityError → 500.

    Form subclasses must set `tenant_unique_field` (defaults to `'code'`) and
    pass `tenant=...` to `__init__`.
    """

    tenant_unique_field = 'code'

    def _clean_tenant_unique_field(self, field_name):
        value = self.cleaned_data.get(field_name)
        if not value:
            return value
        stripped = value.strip() if isinstance(value, str) else value
        tenant = getattr(self, 'tenant', None)
        if tenant is None:
            return stripped
        model = self._meta.model
        kwargs = {f'{field_name}__iexact': stripped} if isinstance(stripped, str) else {field_name: stripped}
        qs = model.objects.filter(tenant=tenant, **kwargs)
        if self.instance.pk is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            display = model._meta.get_field(field_name).verbose_name or field_name
            raise ValidationError(
                f'{str(display).capitalize()} "{stripped}" already exists for this tenant.'
            )
        return stripped

    def clean_code(self):
        # Default implementation — subclasses with a different unique field
        # override `tenant_unique_field` + define their own `clean_<field>()`
        # that delegates to `_clean_tenant_unique_field(field)`.
        return self._clean_tenant_unique_field('code')
