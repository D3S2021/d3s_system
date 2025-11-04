from django import forms
from django.core.exceptions import ValidationError
from .models import Transaccion, Categoria


# -------- validadores de archivo --------
ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_MB = 10  # tamaño máx 10 MB


def _validate_file(f):
    if not f:
        return
    ctype = (getattr(f, "content_type", None) or "").lower()
    if ctype not in ALLOWED_MIME:
        raise ValidationError("Formato no permitido. Subí PDF o imagen (JPG/PNG/WEBP/GIF).")
    if f.size > MAX_MB * 1024 * 1024:
        raise ValidationError(f"El archivo supera el tamaño máximo de {MAX_MB} MB.")


class GastoForm(forms.ModelForm):
    # Acepta dd/mm/aaaa (usuario) e ISO yyyy-mm-dd (input date)
    fecha = forms.DateField(
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "vDateField"}
        )
    )

    # === NUEVO: comprobante ===
    comprobante = forms.FileField(
        required=False,
        label="Comprobante (PDF/imagen)",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": "application/pdf,image/*",
                # en móviles habilita cámara
                "capture": "environment"
            }
        )
    )

    class Meta:
        model = Transaccion
        fields = ["categoria", "fecha", "monto", "descripcion", "comprobante"]
        labels = {
            "categoria": "Categoría",
            "fecha": "Fecha",
            "monto": "Monto",
            "descripcion": "Descripción",
            "comprobante": "Comprobante (PDF/imagen)",
        }
        widgets = {
            "categoria": forms.Select(attrs={"class": "vSelect"}),
            "monto": forms.NumberInput(attrs={"class": "vTextField", "step": "0.01"}),
            "descripcion": forms.TextInput(attrs={"class": "vTextField"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Si NO puede agregar ingresos => es cargador de gastos (oculta categoría)
        is_loader = (user and not user.has_perm("economia.can_add_ingresos"))
        if is_loader and "categoria" in self.fields:
            self.fields["categoria"].required = False
            self.fields["categoria"].widget = forms.HiddenInput()

        qs = Categoria.objects.filter(activo=True).order_by("tipo", "nombre")
        if "categoria" in self.fields:
            self.fields["categoria"].queryset = qs

    def clean_monto(self):
        raw = (self.data.get(self.add_prefix("monto")) or "").strip()
        normalized = raw.replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            raise forms.ValidationError("Ingrese un monto válido.")

    def clean_comprobante(self):
        f = self.cleaned_data.get("comprobante")
        _validate_file(f)
        return f


class GastoOwnEditForm(forms.ModelForm):
    """Edición restringida para el dueño (pendiente): solo fecha, monto, descripción."""
    fecha = forms.DateField(
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "vDateField"}
        )
    )

    class Meta:
        model = Transaccion
        fields = ["fecha", "monto", "descripcion"]
        widgets = {
            "monto": forms.NumberInput(attrs={"class": "vTextField", "step": "0.01"}),
            "descripcion": forms.TextInput(attrs={"class": "vTextField"}),
        }


class CategoriaQuickForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nombre", )
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "vTextField", "placeholder": "Nombre de la categoría"})
        }

    def __init__(self, *args, **kwargs):
        self.tipo = kwargs.pop("tipo", None)  # 'gasto' o 'ingreso'
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tipo = self.tipo
        obj.activo = True
        if commit:
            obj.save()
        return obj
