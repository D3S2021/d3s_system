from django.conf import settings
from django.db import models
from django.utils import timezone
import os, mimetypes
from uuid import uuid4
from django.utils.text import slugify

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

    presupuesto_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

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
    estado = models.CharField(max_length=10, choices=ESTADOS, default="todo")
    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default="media")

    asignados = models.ManyToManyField(
        User, blank=True, related_name="tareas_asignadas_m2m"
    )
    asignado_a = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_asignadas"
    )

    @property
    def asignados_effective(self):
        ids = set(self.asignados.values_list("id", flat=True))
        out = list(self.asignados.all())
        if self.asignado_a_id and self.asignado_a_id not in ids and self.asignado_a:
            out.append(self.asignado_a)
        return out

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


# --------- NUEVO: Adjuntos del Proyecto ---------
def proyecto_upload_to(instance, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    safe = slugify(base)[:60] or "archivo"
    return f"proyectos/{instance.proyecto_id or 'tmp'}/{uuid4().hex}_{safe}{ext.lower()}"

class AdjuntoProyecto(models.Model):
    proyecto      = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="adjuntos")
    archivo       = models.FileField(upload_to=proyecto_upload_to)
    alias         = models.CharField(max_length=200, blank=True) 
    descripcion   = models.CharField(max_length=200, blank=True)
    original_name = models.CharField(max_length=200, blank=True)
    content_type  = models.CharField(max_length=120, blank=True)
    size_bytes    = models.PositiveIntegerField(default=0)
    subido_por    = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    subido_en     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-subido_en"]

    def save(self, *args, **kwargs):
        if self.archivo and not self.original_name:
            self.original_name = os.path.basename(self.archivo.name)
        if self.archivo and hasattr(self.archivo, "size"):
            self.size_bytes = int(self.archivo.size or 0)
        if not self.content_type and self.original_name:
            self.content_type = mimetypes.guess_type(self.original_name)[0] or ""
        super().save(*args, **kwargs)

    def filename(self):
        return os.path.basename(self.archivo.name)

    def size_human(self):
        n = float(self.size_bytes or 0)
        for u in ["B","KB","MB","GB","TB"]:
            if n < 1024.0:
                return f"{n:,.0f}{u}".replace(",", ".")
            n /= 1024.0
        return f"{n:.1f}PB"

    def __str__(self):
        return f"{self.proyecto} · {self.original_name or self.filename()}"


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
    inicio = models.TimeField(  # <-- NUEVO si no lo tenías
        null=True, blank=True
    )
    fin = models.TimeField(     # <-- NUEVO si no lo tenías
        null=True, blank=True
    )
    horas = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
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
