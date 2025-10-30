from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Proyecto(models.Model):
    ESTADOS = [
        ("planificado", "Planificado"),
        ("presupuestado", "Presupuestado"),
        ("aprobado", "Aprobado"),
        ("en_progreso", "En progreso"),
        ("en_pausa", "En pausa"),
        ("finalizado", "Finalizado"),
        ("facturacion", "Facturación"),
        ("archivado", "Archivado"),
    ]
    PRIORIDADES = [
        ("baja", "Baja"),
        ("media", "Media"),
        ("alta", "Alta"),
        ("critica", "Crítica"),
    ]

    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="planificado")
    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default="media")
    responsable = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="proyectos_responsable"
    )
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)

    # Presupuesto base y flag de cierre con facturación incompleta
    presupuesto_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Archivo de presupuesto (PDF)
    presupuesto_pdf = models.FileField(
        upload_to="proyectos/presupuestos/%Y/%m/",
        null=True,
        blank=True,
    )

    facturacion_incompleta = models.BooleanField(default=False)

    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="proyectos_creados")
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)
    is_archivado = models.BooleanField(default=False)

    miembros = models.ManyToManyField(User, blank=True, related_name="proyectos_miembro")

    class Meta:
        permissions = [
            ("can_manage_proyectos", "Puede gestionar todos los proyectos"),
        ]
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["prioridad"]),
            models.Index(fields=["-creado_en"]),
        ]

    def __str__(self):
        return self.nombre


class Tarea(models.Model):
    ESTADOS = [
        ("todo", "Por hacer"),
        ("doing", "En curso"),
        ("review", "En revisión"),
        ("done", "Hecha"),
    ]
    PRIORIDADES = [
        ("baja", "Baja"),
        ("media", "Media"),
        ("alta", "Alta"),
        ("critica", "Crítica"),
    ]

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="tareas")
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    # 🔧 fix: max_length correcto, sin hacks
    estado = models.CharField(max_length=10, choices=ESTADOS, default="todo")
    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default="media")

    # ===== NUEVO (mínimo): permitir múltiples asignados sin romper lo actual =====
    asignados = models.ManyToManyField(
        User, blank=True, related_name="tareas_asignadas_m2m"
    )
    # Mantengo el FK existente para compatibilidad (lo migraremos después si querés)
    asignado_a = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_asignadas"
    )
    # ============================================================================
    # Acceso unificado (útil mientras conviven ambos campos):
    @property
    def asignados_effective(self):
        """Lista de usuarios asignados incluyendo el viejo FK si existe y no está en el M2M."""
        ids = set(self.asignados.values_list("id", flat=True))
        out = list(self.asignados.all())
        if self.asignado_a_id and self.asignado_a_id not in ids and self.asignado_a:
            out.append(self.asignado_a)
        return out
    # ============================================================================

    vence_el = models.DateField(null=True, blank=True)
    estimacion_horas = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="tareas_creadas")
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["estado", "-creado_en"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["prioridad"]),
            models.Index(fields=["vence_el"]),
        ]

    def __str__(self):
        return f"[{self.proyecto}] {self.titulo}"


class Comentario(models.Model):
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    cuerpo = models.TextField()
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["creado_en"]
        indexes = [
            models.Index(fields=["creado_en"]),
        ]

    def __str__(self):
        return f"Comentario de {self.autor} en {self.tarea}"


class Adjunto(models.Model):
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name="adjuntos")
    archivo = models.FileField(upload_to="proyectos/adjuntos/%Y/%m/")
    subido_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    subido_en = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["subido_en"]),
        ]

    def __str__(self):
        return f"Adjunto {self.archivo.name}"


# --------- Historial del Proyecto ---------
class HistorialProyecto(models.Model):
    TIPO = [
        ("estado_tarea", "Cambio de estado de tarea"),
        ("recordatorio", "Recordatorio de vencimiento"),
        ("factura", "Movimiento de factura"),
        ("ajuste", "Ajuste de presupuesto"),
        ("cierre_incompleto", "Cierre con facturación incompleta"),
        ("reapertura", "Reapertura de proyecto"),
        ("cierre", "Cierre de proyecto"),
    ]
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="historial")
    tipo = models.CharField(max_length=32, choices=TIPO)
    descripcion = models.TextField()
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["-creado_en"]),
            models.Index(fields=["tipo"]),
        ]


# --------- Facturas del Proyecto ---------
class FacturaProyecto(models.Model):
    ESTADOS = [
        ("cargada", "Cargada / A revisión"),
        ("aprobada", "Aprobada"),
        ("pend_acreditacion", "Pendiente de acreditación"),
        ("acreditada", "Acreditada"),
        # "rechazada" no persiste: se elimina y queda la traza en historial
    ]
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="facturas")
    numero = models.CharField(max_length=50)
    fecha_emision = models.DateField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    descripcion = models.TextField(blank=True)
    archivo = models.FileField(upload_to="proyectos/facturas/%Y/%m/", blank=True, null=True)

    estado = models.CharField(max_length=20, choices=ESTADOS, default="cargada")
    creada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="facturas_creadas")
    creada_en = models.DateTimeField(default=timezone.now)

    aprobada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas_aprobadas")
    aprobada_en = models.DateTimeField(null=True, blank=True)

    acreditada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas_acreditadas")
    acreditada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["-creada_en"]),
            models.Index(fields=["numero"]),
        ]

    def __str__(self):
        return f"Factura {self.numero} · {self.proyecto.nombre}"


# --------- Horas de trabajo ---------
class HoraTrabajo(models.Model):
    ESTADOS = (
        ("cargada", "Cargada"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="horas_trabajo"
    )
    proyecto = models.ForeignKey(
        "Proyecto", on_delete=models.SET_NULL, null=True, blank=True, related_name="horas_trabajo"
    )
    tarea = models.ForeignKey(
        "Tarea", on_delete=models.SET_NULL, null=True, blank=True, related_name="horas_trabajo"
    )

    fecha = models.DateField(default=timezone.now)
    # Guardamos solo la cantidad (el formulario calcula a partir de inicio/fin)
    horas = models.DecimalField(max_digits=5, decimal_places=2)  # ej. 0.25, 1.50, 8.00
    descripcion = models.TextField(blank=True)
    es_facturable = models.BooleanField(default=False)

    estado = models.CharField(max_length=10, choices=ESTADOS, default="cargada")
    aprobada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="horas_aprobadas"
    )
    aprobada_en = models.DateTimeField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now_add=False, auto_now=True)

    class Meta:
        ordering = ("-fecha", "-creado_en")
        verbose_name = "Hora de trabajo"
        verbose_name_plural = "Horas de trabajo"
        permissions = [
            ("can_manage_economia", "Puede acceder al área de economía"),
            ("can_approve_horas", "Puede aprobar horas de trabajo"),
        ]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["-fecha"]),
            models.Index(fields=["proyecto"]),
            models.Index(fields=["usuario"]),
        ]

    def __str__(self):
        base = f"{self.usuario} · {self.horas} hs · {self.fecha:%d/%m/%Y}"
        if self.proyecto:
            base += f" · {self.proyecto.nombre}"
        return base
