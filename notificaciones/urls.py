# notificaciones/urls.py
from django.urls import path
from . import views

app_name = "notificaciones"

urlpatterns = [
    path("", views.lista_notificaciones, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/leida/", views.marcar_leida, name="marcar_leida"),
    path("marcar-todas/", views.marcar_todas, name="marcar_todas"),

    # APIs (opcional, si las usás con fetch/AJAX)
    path("api/<int:pk>/leida/", views.api_marcar_leida, name="api_marcar_leida"),
    path("api/marcar-todas/", views.api_marcar_todas, name="api_marcar_todas"),
]
