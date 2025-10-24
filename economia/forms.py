from django import forms
from .models import Transaccion, Categoria

class GastoForm(forms.ModelForm):
    # Acepta dd/mm/aaaa (usuario) e ISO yyyy-mm-dd (input date)
    fecha = forms.DateField(
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",           # el <input type="date"> usa ISO en value
            attrs={
                "type": "date",          # muestra calendario nativo
                "class": "vDateField",
            }
        )
    )

    class Meta:
        model = Transaccion
        fields = ["categoria", "fecha", "monto", "descripcion"]
        labels = {
            "categoria": "Categoría",
            "fecha": "Fecha",
            "monto": "Monto",
            "descripcion": "Descripción",
        }
        widgets = {
            "categoria": forms.Select(attrs={"class": "vSelect"}),
            # no sobrescribo 'fecha' acá (ya está arriba)
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
        """
        Normaliza '1.234,56' o '1234,56' -> 1234.56
        (Django/DB lo convertirá al tipo correcto después).
        """
        raw = (self.data.get(self.add_prefix("monto")) or "").strip()
        normalized = raw.replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            raise forms.ValidationError("Ingrese un monto válido.")


class GastoOwnEditForm(forms.ModelForm):
    """Edición restringida para el dueño (pendiente): solo fecha, monto, descripción."""
    fecha = forms.DateField(
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "class": "vDateField",
            }
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
        fields = ("nombre", )  # el tipo lo inyectamos desde la URL
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
