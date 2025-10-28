from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.db.models import Q

class Command(BaseCommand):
    help = "Crea o actualiza los grupos por defecto con sus permisos."

    def handle(self, *args, **kwargs):
        CONFIG = {
            "Contabilidad": {
                "economia": ["view", "add", "change"],  # permisos del módulo 'economia'
            },
            "Proyectos": {
                "proyectos": ["view", "add", "change"],  # permisos del módulo 'proyectos'
                "notificaciones": ["view"],              # opcional
            },
        }

        for group_name, app_perms in CONFIG.items():
            group, created = Group.objects.get_or_create(name=group_name)

            # Limpia solo los permisos del mismo app_label, no todos
            for app_label in app_perms.keys():
                current_perms = group.permissions.filter(content_type__app_label=app_label)
                group.permissions.remove(*current_perms)

            total = 0
            for app_label, actions in app_perms.items():
                q = Q(content_type__app_label=app_label)
                subq = Q()
                for action in actions:
                    subq |= Q(codename__startswith=f"{action}_")
                perms = Permission.objects.filter(q & subq)
                group.permissions.add(*perms)
                total += perms.count()

            action = "creado" if created else "actualizado"
            self.stdout.write(
                self.style.SUCCESS(f"Grupo '{group_name}' {action} con {total} permisos.")
            )
