from django import template
register = template.Library()

@register.filter
def get_field(form, name):
    try:
        return form[name]          # BoundField
    except KeyError:
        return None                 # <-- return None, not ""
