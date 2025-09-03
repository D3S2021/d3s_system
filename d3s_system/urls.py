from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

# Vista simple para la página de inicio
def home(request):
    return HttpResponse("<h1>Bienvenido a D3S System 🚀</h1>")

urlpatterns = [
    path("", home, name="home"),       # Página de inicio
    path("admin/", admin.site.urls),   # Acceso al panel de administración
]
