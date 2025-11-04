from django.contrib import admin
from .models import Categoria, Transaccion, PlanMensual


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("nombre",)


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "categoria",
        "monto",
        "estado",
        "usuario",
        "validado_por",
        "proyecto",  # 👈 agregado
        "es_efectivo",
    )
    list_filter = ("estado", "categoria__tipo", "categoria", "proyecto","es_efectivo")
    search_fields = ("descripcion", "usuario__username", "categoria__nombre")
    autocomplete_fields = ("categoria", "usuario", "validado_por", "proyecto")

    # 🔒 No permitir agregar nuevas transacciones desde el admin
    def has_add_permission(self, request):
        return False

    # ✅ Sí permitir editar y eliminar
    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


@admin.register(PlanMensual)
class PlanMensualAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "categoria", "monto_esperado", "actualizado_en")
    list_filter = ("year", "month", "categoria")
    search_fields = ("categoria__nombre",)
