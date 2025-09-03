# accounts/templatetags/email_extras.py
from django import template

register = template.Library()

@register.filter
def has_primary(emailaddresses) -> bool:
    """Return True if any EmailAddress in the iterable is marked primary."""
    try:
        return any(getattr(e, "primary", False) for e in emailaddresses)
    except Exception:
        return False
