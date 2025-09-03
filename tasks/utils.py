# tasks/utils.py
from django.urls import reverse, NoReverseMatch

def reverse_first(candidates, *args, **kwargs):
    """
    Try reversing a list of named routes; return the first that works or None.
    """
    if isinstance(candidates, str):
        candidates = [candidates]
    for name in candidates:
        try:
            return reverse(name, *args, **kwargs)
        except NoReverseMatch:
            continue
    return None
