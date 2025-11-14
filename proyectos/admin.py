from django.contrib import admin
from .models import Proyecto, Tarea, Comentario, Adjunto

@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "estado", "prioridad", "responsable", "ver_progreso", "is_archivado", "creado_en")
    list_filter = ("estado", "prioridad", "is_archivado")
    search_fields = ("nombre", "descripcion")
    filter_horizontal = ("miembros",)

    @admin.display(description="Progreso")
    def ver_progreso(self, obj):
        # Muestra “0%” si por algún motivo el field no existe/aún no migraste
        valor = getattr(obj, "progreso", 0)
        return f"{valor}%"

@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "proyecto", "estado", "prioridad", "asignado_a", "vence_el")
    list_filter = ("estado", "prioridad", "proyecto")
    search_fields = ("titulo", "descripcion")

admin.site.register(Comentario)
admin.site.register(Adjunto)


from django.contrib import admin
from .models import HoraTrabajo

@admin.register(HoraTrabajo)
class HoraTrabajoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "fecha", "horas", "proyecto", "tarea", "estado", "es_facturable")
    list_filter = ("estado", "es_facturable", "fecha", "proyecto")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "descripcion")


from django.contrib import admin
from .models import AdjuntoProyecto

@admin.register(AdjuntoProyecto)
class AdjuntoProyectoAdmin(admin.ModelAdmin):
    list_display = ("proyecto", "archivo", "subido_por", "subido_en")
    list_filter = ("proyecto", "subido_en")
    search_fields = ("proyecto__nombre", "archivo", "descripcion")
