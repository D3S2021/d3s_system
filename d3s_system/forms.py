from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm

User = get_user_model()

class PerfilNombreForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        widgets = {
            'first_name': forms.TextInput(attrs={'class':'form-control','placeholder':'Nombre'}),
            'last_name' : forms.TextInput(attrs={'class':'form-control','placeholder':'Apellido'}),
        }
        labels = {'first_name':'Nombre', 'last_name':'Apellido'}
