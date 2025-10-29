from django.urls import path
from . import views

app_name = "proyectos"

urlpatterns = [
    # Dashboard / listados
    path("", views.dashboard, name="dashboard"),
    path("lista/", views.proyecto_list, name="lista"),
    path("<int:pk>/", views.proyecto_detalle, name="detalle"),
    path("<int:pk>/historial/", views.proyecto_historial, name="historial"),
    path("<int:pk>/facturacion/", views.proyecto_facturacion, name="facturacion"),
    path("kanban/<int:pk>/", views.kanban_proyecto, name="kanban"),

    # Proyecto: acciones
    path("nuevo/", views.proyecto_crear, name="nuevo"),
    path("<int:pk>/editar/", views.proyecto_editar, name="editar"),
    path("<int:pk>/editar-modal/", views.editar_modal, name="editar_modal"),
    path("<int:pk>/archivar/", views.proyecto_archivar, name="archivar"),
    path("<int:pk>/cambiar-estado/", views.proyecto_cambiar_estado, name="cambiar_estado"),
    path("<int:pk>/cerrar/", views.proyecto_cerrar, name="cerrar"),
    path("<int:pk>/reabrir/", views.proyecto_reabrir, name="reabrir"),
    # API para duplicar:
    path("api/<int:pk>/", views.proyecto_api_json, name="api_proyecto"),

    # Tareas
    path("<int:proyecto_id>/tareas/crear/", views.tarea_crear, name="tarea_crear"),
    path("tareas/<int:pk>/editar/", views.tarea_editar, name="tarea_editar"),
    path("tareas/<int:pk>/cambiar-estado/", views.tarea_cambiar_estado, name="tarea_cambiar_estado"),
    path("tareas/<int:pk>/eliminar/", views.tarea_eliminar, name="tarea_eliminar"),
    path("tareas/<int:tarea_id>/comentario/", views.comentario_agregar, name="comentario_agregar"),
    path("tareas/<int:tarea_id>/adjunto/", views.adjunto_subir, name="adjunto_subir"),
    path("tareas/<int:pk>/detalle-modal/", views.tarea_detalle_modal, name="tarea_detalle_modal"),

    # Horas
    path("horas/nueva/", views.horas_nueva, name="horas_nueva"),
    path("horas/mias/", views.horas_mias, name="horas_mias"),

    # ⬇️ ESTA ES LA QUE TE DABA ERROR: debe apuntar a horas_economia_list
    path("horas/economia/", views.horas_economia_list, name="horas_economia"),

    path("horas/<int:pk>/aprobar/", views.horas_aprobar, name="horas_aprobar"),
    path("horas/<int:pk>/rechazar/", views.horas_rechazar, name="horas_rechazar"),

    path("tareas/<int:pk>/chat/enviar/", views.tarea_chat_enviar, name="tarea_chat_enviar"),

    path("tareas/open/<int:pk>/", views.tarea_open, name="tarea_open"),


]
