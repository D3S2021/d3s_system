# economia/templatetags/economia_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(mapping, key):
    """
    Uso:  {{ dict_var|get_item:llave }}
    Soporta dicts y objetos con __getitem__.
    Si no existe, retorna cadena vacía.
    """
    try:
        # dict con .get
        return mapping.get(key)
    except AttributeError:
        try:
            # indexable
            return mapping[key]
        except Exception:
            return ""
