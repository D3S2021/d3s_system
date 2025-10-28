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

# === EJECUTAR seed_groups AUTOMÁTICAMENTE (solo 1 vez) ===
try:
    from django.core.management import call_command
    call_command("seed_groups")
except Exception as e:
    print(f"⚠️ Error ejecutando seed_groups: {e}")


'''
# --- Reinicialización de base de datos (sólo una vez) ---
import os
from django.db import connection
from django.core.management import call_command

if os.getenv("RESET_DB_ON_START") == "1":
    print("⚠️ Reinicializando base de datos...")
    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            # eliminar todas las tablas
            tables = connection.introspection.table_names()
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table};")
            cursor.execute("PRAGMA foreign_keys = ON;")

        print("✅ Base de datos vaciada. Ejecutando migraciones...")
        call_command("migrate", interactive=False)
        print("✅ Migraciones aplicadas correctamente.")
    except Exception as e:
        print("❌ Error al reinicializar la base:", e)
'''