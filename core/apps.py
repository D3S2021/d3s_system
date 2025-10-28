# core/apps.py
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from django.db.models.signals import post_migrate
        from core.seed_utils import create_default_groups

        def _seed_groups(sender, **kwargs):
            try:
                create_default_groups()
            except Exception:  # evita romper el deploy si algo falla
                import logging
                logging.getLogger(__name__).exception("Error creando grupos")

        post_migrate.connect(_seed_groups, dispatch_uid="core_seed_default_groups")
