from django.contrib import admin, messages
from django.conf import settings
from .models import WhatsAppConfig, WhatsAppTemplate, WhatsAppMessageLog
from .services import send_whatsapp_template

@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(admin.ModelAdmin):
    list_display = ("enabled", "phone_number_id", "business_account_id")
    fieldsets = (
        (None, {"fields": ("enabled",)}),
        ("Credenciales", {"fields": ("phone_number_id", "business_account_id", "token")}),
        ("Webhook", {"fields": ("verify_token",)}),
    )

@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "active")
    list_filter = ("active", "language")
    search_fields = ("name",)
    actions = ["enviar_prueba"]

    def enviar_prueba(self, request, queryset):
        to = getattr(settings, "WHATSAPP_TEST_TO", "")
        if not to:
            self.message_user(
                request,
                "Configurá settings.WHATSAPP_TEST_TO (número E.164, e.g. +549341xxxxxxx) para probar.",
                level=messages.ERROR,
            )
            return
        count_ok = 0
        count_fail = 0
        for tpl in queryset:
            ok, _resp, _log = send_whatsapp_template(
                to_e164=to,
                template_name=tpl.name,
                language=tpl.language or "es",
                components=None,  # si tu plantilla requiere parámetros, los agregamos en el próximo paso
            )
            if ok: count_ok += 1
            else:  count_fail += 1
        if count_ok and not count_fail:
            self.message_user(request, f"Enviado OK ({count_ok}).", level=messages.SUCCESS)
        elif count_ok and count_fail:
            self.message_user(request, f"Parcial: {count_ok} OK, {count_fail} errores.", level=messages.WARNING)
        else:
            self.message_user(request, "Todos fallaron. Revisá config/token/plantilla.", level=messages.ERROR)
    enviar_prueba.short_description = "Enviar prueba a settings.WHATSAPP_TEST_TO"

@admin.register(WhatsAppMessageLog)
class WhatsAppMessageLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "to", "template", "status", "provider_message_id")
    list_filter = ("status", "template")
    search_fields = ("to", "provider_message_id")
    readonly_fields = ("created_at", "last_update", "payload", "response", "error")
