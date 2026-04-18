from django.contrib import admin, messages
from django.conf import settings
from .models import WhatsAppConfig, WhatsAppTemplate, WhatsAppMessageLog


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

@admin.register(WhatsAppMessageLog)
class WhatsAppMessageLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "to", "template", "status", "provider_message_id")
    list_filter = ("status", "template")
    search_fields = ("to", "provider_message_id")
    readonly_fields = ("created_at", "last_update", "payload", "response", "error")
