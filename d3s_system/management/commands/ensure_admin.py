# d3s_system/management/commands/ensure_admin.py
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "Crea o actualiza el superusuario desde DJANGO_SUPERUSER_* (idempotente)."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        force_reset = os.getenv("FORCE_SUPERUSER_RESET", "0") == "1"

        if not username or not email or not password:
            self.stdout.write(self.style.WARNING(
                "DJANGO_SUPERUSER_* faltan; no se crea/actualiza superusuario."
            ))
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )

        if created:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"Superusuario '{username}' creado."
            ))
        else:
            # si cambiaron el email, lo actualizamos
            if user.email != email:
                user.email = email
            # si pedís forzar reset, o si el usuario no es superuser/staff, lo corregimos
            if force_reset or not user.is_superuser or not user.is_staff:
                user.is_staff = True
                user.is_superuser = True
                user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"Superusuario '{username}' verificado/actualizado."
            ))
