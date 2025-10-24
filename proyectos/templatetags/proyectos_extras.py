from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    """
    Uso en templates:  cols|get_item:key
    Devuelve d[key] o d.get(key, []), y si falla, devuelve [] para poder iterar.
    """
    try:
        if hasattr(d, "get"):
            return d.get(key, [])
        return d[key]
    except Exception:
        return []

# proyectos/templatetags/proyectos_extras.py
from django import template
register = template.Library()

@register.filter
def get_full_name_or_username(user):
    if not user:
        return "—"
    full = (user.get_full_name() or "").strip()
    return full or user.username

from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    """
    Permite hacer:  dict|get_item:key  en plantillas.
    Devuelve [] si no existe la clave para que el for no explote.
    """
    try:
        return d.get(key, [])
    except Exception:
        return []

from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Permite hacer dict[key] en plantillas"""
    if dictionary and key in dictionary:
        return dictionary.get(key)
    return []
