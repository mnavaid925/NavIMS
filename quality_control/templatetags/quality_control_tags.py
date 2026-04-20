"""Template tags for the quality_control module.

`querystring` — merge the current `request.GET` with keyword overrides and
emit a URL-encoded string (without the leading '?'). Used in list templates
to preserve filter params across pagination links (D-06).

Example:
    <a href="?{% querystring page=2 %}">2</a>

If `page` is already in the current query string, it is overwritten with `2`;
every other key (q, status, severity, etc.) is preserved.
"""
from urllib.parse import urlencode

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring(context, **overrides):
    request = context.get('request')
    params = {}
    if request is not None and hasattr(request, 'GET'):
        # Use QueryDict.lists() to preserve multi-value keys (rare, but safe).
        for key in request.GET:
            values = request.GET.getlist(key)
            if values:
                params[key] = values[-1]
    for key, value in overrides.items():
        if value is None or value == '':
            params.pop(key, None)
        else:
            params[key] = value
    return urlencode(params)
