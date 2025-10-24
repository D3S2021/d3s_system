# d3s_system/urls.py
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from .views import perfil_usuario 
from django.contrib.auth import views as auth_views
from .views import logout_then_login
from django.conf import settings
from django.conf.urls.static import static
from .views import perfil_editar_modal, password_change_modal

urlpatterns = [
    path("", lambda request: redirect("perfil"), name="home"),
    path("perfil/", perfil_usuario, name="perfil"),
    path("admin/", admin.site.urls),
    path("economia/", include("economia.urls", namespace="economia")), 
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", logout_then_login, name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("notificaciones/", include("notificaciones.urls", namespace="notificaciones")),
    path("proyectos/", include(("proyectos.urls", "proyectos"), namespace="proyectos")),
    path('perfil/editar-modal/', perfil_editar_modal, name='perfil_editar_modal'),
    path('perfil/password-modal/', password_change_modal, name='password_change_modal'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)