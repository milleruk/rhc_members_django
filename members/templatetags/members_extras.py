# members/templatetags/members_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(qs_or_dict, key):
    """Return object/value by id or key from a queryset, list, or dict."""
    if key in (None, "", "None"):
        return ""
    try:
        key_int = int(key)
    except (TypeError, ValueError):
        key_int = key

    # dict-like
    if hasattr(qs_or_dict, "get") and not hasattr(qs_or_dict, "model"):
        return qs_or_dict.get(key, "")

    # queryset-like
    try:
        return qs_or_dict.get(id=key_int)
    except Exception:
        pass

    # iterable fallback
    try:
        for obj in qs_or_dict:
            if getattr(obj, "id", None) == key_int or getattr(obj, "pk", None) == key_int:
                return obj
    except Exception:
        pass
    return ""

@register.filter
def attr(obj, name):
    """Safely get attribute by name in templates. {{ obj|attr:"name" }}"""
    try:
        return getattr(obj, name, "")
    except Exception:
        return ""
