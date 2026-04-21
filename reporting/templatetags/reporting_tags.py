"""Template helpers for the reporting templates.

`dictkey` — dynamic dict/object lookup used by snapshot_detail.html to render
rows whose column keys are defined in the registry rather than the template.
"""
from django import template

register = template.Library()


@register.filter(name='dictkey')
def dictkey(value, key):
    """Return value[key] for dicts, value.key for attrs, or '' if missing."""
    if value is None:
        return ''
    if isinstance(value, dict):
        return value.get(key, '')
    return getattr(value, key, '')


@register.filter(name='humanize_key')
def humanize_key(value):
    """Convert snake_case keys into a more readable label (for summary cards)."""
    if not value:
        return ''
    return str(value).replace('_', ' ').title()


@register.filter(name='is_simple')
def is_simple(value):
    """True when a value can be rendered as plain text (not dict/list)."""
    return not isinstance(value, (dict, list, tuple, set))
