from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Notificacion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifs")
    titulo = models.CharField(max_length=120)
    cuerpo = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True)  # adónde lleva al hacer click
    leida = models.BooleanField(default=False)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return f"[{self.user}] {self.titulo}"
