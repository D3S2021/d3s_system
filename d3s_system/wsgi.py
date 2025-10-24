"""
WSGI config for d3s_system project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'd3s_system.settings')

application = get_wsgi_application()

# --- Crear o asegurar superusuario automáticamente ---
import os
from django.contrib.auth import get_user_model
from django.db import OperationalError

try:
    User = get_user_model()
    username = os.getenv("DJANGO_SUPERUSER_USERNAME")
    email = os.getenv("DJANGO_SUPERUSER_EMAIL")
    password = os.getenv("DJANGO_SUPERUSER_PASSWORD")

    if username and email and password:
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, email=email, password=password)
            print(f"Superusuario '{username}' creado automáticamente.")
        else:
            print(f"Superusuario '{username}' ya existe.")
    else:
        print("Variables DJANGO_SUPERUSER_* no definidas, no se crea usuario.")
except OperationalError:
    print("La base de datos aún no está lista.")
except Exception as e:
    print("Error al crear superusuario:", e)
