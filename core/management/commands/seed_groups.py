from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.db.models import Q

class Command(BaseCommand):
    help = "Crea/actualiza los grupos por defecto con sus permisos"

    def handle(self, *args, **kwargs):
        # Ajustá aquí lo que querés que tenga cada grupo
        CONFIG = {
            "Contabilidad": {
                "economia": ["view", "add", "change"],   # permisos sobre modelos de 'economia'
            },
            "Proyectos": {
                "proyectos": ["view", "add", "change"],  # permisos sobre modelos de 'proyectos'
                # "notificaciones": ["view"],            # si querés sumar algo más
            },
        }

        for group_name, app_map in CONFIG.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            # Si preferís preservar permisos existentes, comentá la línea siguiente
            group.permissions.clear()

            total = 0
            for app_label, actions in app_map.items():
                q = Q(content_type__app_label=app_label)
                subq = Q()
                for action in actions:
                    subq |= Q(codename__startswith=f"{action}_")
                perms = Permission.objects.filter(q & subq)
                group.permissions.add(*perms)
                total += perms.count()

            self.stdout.write(self.style.SUCCESS(
                f"Grupo '{group_name}' configurado con {total} permisos."
            ))
