from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Categoria(models.Model):
    TIPOS = (
        ("ingreso", "Ingreso"),
        ("gasto", "Gasto"),
    )
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.tipo} · {self.nombre}"


class Transaccion(models.Model):
    ESTADOS = (
        ("pendiente", "Pendiente"),
        ("aprobado", "Aprobado"),
        ("rechazado", "Rechazado"),
    )

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, null=True, blank=True)
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    descripcion = models.CharField(max_length=255, blank=True)

    # NUEVOS CAMPOS
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="transacciones"
    )
    estado = models.CharField(max_length=10, choices=ESTADOS, default="pendiente")
    validado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="validaciones"
    )
    validado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("can_validate_transactions", "Puede validar transacciones de economía"),
            ("can_add_ingresos", "Puede registrar ingresos en economía"),
            ("can_edit_own_transactions", "Puede editar sus propias transacciones pendientes"),
        ]

    def __str__(self):
        tipo = self.categoria.tipo if self.categoria else "sin categ."
        nombre = self.categoria.nombre if self.categoria else "Pendiente de categorizar"
        return f"{self.fecha} · {tipo} · {nombre} · ${self.monto} · {self.estado}"


class PlanMensual(models.Model):
    """
    Monto esperado (plan) por categoría para un mes/año.
    Se usa para comparar contra lo real en el resumen por categorías.
    """
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1..12
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="planes")
    monto_esperado = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="planes_creados"
    )

    class Meta:
        unique_together = ("year", "month", "categoria")
        verbose_name = "Plan mensual"
        verbose_name_plural = "Planes mensuales"

    def __str__(self):
        return f"{self.categoria} {self.month}/{self.year} · ${self.monto_esperado}"
