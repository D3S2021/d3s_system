# proyectos/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.exceptions import ValidationError

from .models import (
    Proyecto, Tarea, Comentario, Adjunto,
    FacturaProyecto, HoraTrabajo
)

User = get_user_model()

# ===========================
# FORMULARIO DE PROYECTO
# ===========================
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Proyecto

User = get_user_model()


class ProyectoForm(forms.ModelForm):
    """
    Form mejorado:
    - Presupuesto con formateo en el front (oninput) y limpieza backend.
    - Archivo PDF opcional de presupuesto.
    - Miembros con checkbox (excluye admin/superusuarios si querés).
    - Rango de fechas con validación (inicio <= fin).
    - Campo 'duplicar_desde' para precargar desde otro proyecto.
    """

    presupuesto_total = forms.DecimalField(
        label="Presupuesto total",
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "placeholder": "0.00",
                # para el formateo en vivo desde tu JS (formatCurrency)
                "oninput": "formatCurrency(this)",
                "inputmode": "decimal",
            }
        ),
    )

    presupuesto_pdf = forms.FileField(
        label="Archivo de presupuesto (PDF)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
    )

    duplicar_desde = forms.ModelChoiceField(
        label="Duplicar desde proyecto",
        required=False,
        queryset=Proyecto.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        empty_label="Seleccioná un proyecto…",
    )

    class Meta:
        model = Proyecto
        fields = [
            "nombre",
            "descripcion",
            "estado",
            "prioridad",
            "responsable",
            "miembros",
            "fecha_inicio",
            "fecha_fin",
            "presupuesto_total",
            # estos dos no existen en el modelo; los manejamos en el form
            "presupuesto_pdf",
            "duplicar_desde",
        ]
        widgets = {
            "descripcion": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Breve descripción del proyecto..."}
            ),
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "responsable": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        # pasamos el user desde la vista: ProyectoForm(user=request.user)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # === Usuarios visibles (miembros/responsables) ===
        # Opción A: excluir username "admin"
        base_qs = (
            User.objects.filter(is_active=True)
            .exclude(username__iexact="admin")
            .order_by("first_name", "last_name", "username")
        )
        # Si preferís excluir cualquier superusuario, reemplazá la línea anterior por:
        # base_qs = (
        #     User.objects.filter(is_active=True)
        #     .exclude(is_superuser=True)
        #     .order_by("first_name", "last_name", "username")
        # )

        self.fields["miembros"].queryset = base_qs
        self.fields["miembros"].widget = forms.CheckboxSelectMultiple()

        self.fields["responsable"].queryset = base_qs
        self.fields["responsable"].empty_label = "---------"

        # === Proyectos para duplicar ===
        if user and user.has_perm("proyectos.can_manage_proyectos"):
            self.fields["duplicar_desde"].queryset = Proyecto.objects.filter(
                is_archivado=False
            ).order_by("-creado_en")
        elif user:
            self.fields["duplicar_desde"].queryset = (
                Proyecto.objects.filter(
                    Q(is_archivado=False)
                    & (Q(responsable=user) | Q(miembros=user))
                )
                .distinct()
                .order_by("-creado_en")
            )
        else:
            self.fields["duplicar_desde"].queryset = Proyecto.objects.none()

    # === Limpiezas/validaciones ===
    def clean_presupuesto_pdf(self):
        archivo = self.cleaned_data.get("presupuesto_pdf")
        if archivo:
            name = (archivo.name or "").lower()
            content_type = getattr(archivo, "content_type", "")
            if not (name.endswith(".pdf") or content_type == "application/pdf"):
                raise ValidationError("Solo se permiten archivos PDF.")
        return archivo

    def clean_presupuesto_total(self):
        """
        Permite que el presupuesto llegue con separadores de miles/puntos/comas
        y lo normaliza a Decimal.
        """
        val = self.cleaned_data.get("presupuesto_total")
        if isinstance(val, (int, float, Decimal)) or val is None:
            return val

        # si llega como string formateado, normalizamos
        s = str(val).strip()
        if not s:
            return None

        # quitamos separadores de miles comunes
        s = s.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            return Decimal(s)
        except InvalidOperation:
            raise ValidationError("Formato de moneda inválido.")

    def clean(self):
        cleaned = super().clean()
        ini = cleaned.get("fecha_inicio")
        fin = cleaned.get("fecha_fin")
        if ini and fin and fin < ini:
            self.add_error("fecha_fin", "La fecha fin debe ser posterior o igual a inicio.")
        return cleaned

    def save(self, commit=True):
        """
        Guardamos el Proyecto y adjuntamos el archivo PDF en un atributo temporal
        para que la vista pueda manejar su almacenamiento si no existe el campo en el modelo.
        """
        instance = super().save(commit=False)
        # Adjuntamos el file a la instancia como atributo (no de base de datos)
        instance._presupuesto_pdf = self.cleaned_data.get("presupuesto_pdf")

        if commit:
            instance.save()
            self.save_m2m()
        return instance



# ===========================
# FORMULARIO DE TAREA
# ===========================
class TareaForm(forms.ModelForm):
    class Meta:
        model = Tarea
        fields = [
            "titulo",
            "descripcion",
            "estado",
            "prioridad",
            "asignado_a",
            "vence_el",
            "estimacion_horas",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "vence_el": forms.DateInput(attrs={"type": "date"}),
        }


# ===========================
# COMENTARIOS Y ADJUNTOS
# ===========================
class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ["cuerpo"]
        widgets = {
            "cuerpo": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Escribí un comentario..."}
            )
        }


class AdjuntoForm(forms.ModelForm):
    class Meta:
        model = Adjunto
        fields = ["archivo"]


# ===========================
# FACTURACIÓN
# ===========================
class FacturaForm(forms.ModelForm):
    class Meta:
        model = FacturaProyecto
        fields = ["numero", "fecha_emision", "monto", "descripcion", "archivo"]
        widgets = {"fecha_emision": forms.DateInput(attrs={"type": "date"})}


# ===========================
# FORMULARIOS DE REAPERTURA / CIERRE
# ===========================
class ReaperturaForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de reapertura",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class CierreIncompletoForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo del cierre incompleto",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


# ===========================
# HORAS DE TRABAJO
# ===========================
class HoraTrabajoForm(forms.ModelForm):
    inicio = forms.TimeField(
        label="Inicio",
        input_formats=["%H:%M"],
        widget=forms.TimeInput(attrs={"type": "time", "step": "60"})
    )
    fin = forms.TimeField(
        label="Fin",
        input_formats=["%H:%M"],
        widget=forms.TimeInput(attrs={"type": "time", "step": "60"})
    )

    class Meta:
        model = HoraTrabajo
        fields = ["usuario", "fecha", "proyecto", "descripcion", "inicio", "fin"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        request_user = kwargs.pop("request_user", None)
        puede_asignar = kwargs.pop("puede_asignar", False)
        super().__init__(*args, **kwargs)

        # Usuario visible solo si tiene permisos
        if puede_asignar:
            self.fields["usuario"].queryset = User.objects.filter(is_active=True)
        else:
            self.fields["usuario"].queryset = User.objects.filter(pk=request_user.pk)
            self.fields["usuario"].widget = forms.HiddenInput()

        # Proyectos disponibles
        if request_user and request_user.has_perm("proyectos.can_manage_proyectos"):
            qs = Proyecto.objects.filter(is_archivado=False)
        else:
            qs = Proyecto.objects.filter(Q(is_archivado=False) &
                                         (Q(responsable=request_user) |
                                          Q(miembros=request_user))).distinct()
        self.fields["proyecto"].queryset = qs.order_by("nombre")

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("inicio")
        fin = cleaned.get("fin")
        if inicio and fin and inicio >= fin:
            raise forms.ValidationError("La hora de inicio debe ser anterior a la de fin.")
        return cleaned
