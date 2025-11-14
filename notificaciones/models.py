from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Notificacion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifs")
    titulo = models.CharField(max_length=120)
    cuerpo = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True)  # adónde lleva al hacer click
    leida = models.BooleanField(default=False)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return f"[{self.user}] {self.titulo}"

from django.conf import settings
from django.db import models
from django.utils import timezone

class WhatsAppConfig(models.Model):
    """Config única para WhatsApp Cloud API (editable en Admin)."""
    enabled = models.BooleanField(default=True)
    phone_number_id = models.CharField(max_length=64, blank=True)
    business_account_id = models.CharField(max_length=64, blank=True)
    token = models.CharField(max_length=512, blank=True)
    verify_token = models.CharField(max_length=128, default="d3s-verify")

    class Meta:
        verbose_name = "Config WhatsApp Cloud API"
        verbose_name_plural = "Config WhatsApp Cloud API"

    def __str__(self):
        return "Config WhatsApp"

class WhatsAppTemplate(models.Model):
    """Plantillas aprobadas en Meta (solo guardamos el nombre/idioma)."""
    name = models.CharField("Nombre (Meta)", max_length=128, unique=True)  # ej: transaction_update
    language = models.CharField("Idioma", max_length=10, default="es")     # ej: es o es_AR
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Plantilla WhatsApp"
        verbose_name_plural = "Plantillas WhatsApp"

    def __str__(self):
        return f"{self.name} ({self.language})"

class WhatsAppMessageLog(models.Model):
    """Bitácora de envíos y estados."""
    to = models.CharField(max_length=32)  # E.164 (+549...)
    template = models.ForeignKey(WhatsAppTemplate, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(null=True, blank=True)
    response = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=32, default="created")  # created|sent|delivered|read|failed
    provider_message_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_update = models.DateTimeField(auto_now=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"[{self.status}] {self.to} {self.template or ''}"
