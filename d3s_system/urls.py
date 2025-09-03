from django.contrib import admin
from django.urls import path
from django.http import HttpResponse

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", lambda r: HttpResponse("D3S SYSTEM funcionando ✔"), name="home"),
]
