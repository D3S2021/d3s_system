# core/seed_utils.py
from django.contrib.auth.models import Group, Permission

def create_default_groups():
    """
    Crea/actualiza grupos 'Contabilidad' y 'Proyectos' y asigna permisos.
    Es idempotente.
    """
    contab, _ = Group.objects.get_or_create(name="Contabilidad")
    proy, _   = Group.objects.get_or_create(name="Proyectos")

    # Ajustá estos codenames a tus modelos reales:
    perms_contab = [
        "view_categoria", "add_categoria", "change_categoria",
        "view_transaccion", "add_transaccion", "change_transaccion",
    ]
    perms_proy = [
        "view_proyecto", "add_proyecto", "change_proyecto",
        "view_tarea", "add_tarea", "change_tarea",
    ]

    def add_perms(group, codenames):
        for code in codenames:
            try:
                p = Permission.objects.get(codename=code)
                group.permissions.add(p)
            except Permission.DoesNotExist:
                # El permiso aún no existe (p.ej. sin migraciones de esa app)
                pass

    add_perms(contab, perms_contab)
    add_perms(proy, perms_proy)
