from django.urls import path
from . import views

app_name = "economia"

urlpatterns = [
    path("", views.dashboard_economia, name="dashboard"),
    path("resumen/", views.resumen_categorias, name="resumen"),
    path("resumen/", views.resumen_categorias, name="resumen_categorias"),
    path("transacciones/", views.lista_transacciones, name="transacciones"),
    path("cierre/", views.cierre_caja, name="cierre"),
    path("cierre/", views.cierre_caja, name="cierre_caja"),
    path("nuevo/", views.nueva_transaccion, name="nuevo"),
    path("plan/", views.planificar_mes, name="planificar_mes"),
    path("categoria/nueva/<str:tipo>/", views.categoria_nueva, name="categoria_nueva"),
    path("categoria/<int:pk>/eliminar/", views.categoria_eliminar, name="categoria_eliminar"),

    path("transacciones/<int:pk>/editar/", views.editar_transaccion, name="tx_editar"),
    path("transacciones/<int:pk>/eliminar/", views.eliminar_transaccion, name="tx_eliminar"),
    path("transacciones/<int:pk>/estado/", views.cambiar_estado_transaccion, name="tx_estado"),
    path("mias/<int:pk>/editar/", views.editar_mia_desde_perfil, name="tx_mia_editar"),
    path("pendientes/", views.transacciones_pendientes, name="pendientes"),
    path("nuevo/", views.nueva_transaccion, name="nuevo"),

]
