# views.py (perfil / horas)

from django import forms
from django.contrib.auth import logout, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q, Sum, Max, Count, F, Value, DecimalField, Case, When, IntegerField
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from economia.models import Transaccion
from proyectos.models import HoraTrabajo, Proyecto, Tarea





# ------------------------------------------------------------
# Utilidad: cerrar sesión y volver a login
# ------------------------------------------------------------
def logout_then_login(request):
    """Cierra la sesión actual y redirige al login."""
    logout(request)
    return redirect("login")


# ------------------------------------------------------------
# PERFIL DE USUARIO
# ------------------------------------------------------------
@login_required
def perfil_usuario(request):
    """
    Panel de perfil:
      - Accesos (Economía, etc.)
      - Transacciones propias en estado 'pendiente'
      - Mis horas (tabla agrupada y detalle inline)
      - Contador de proyectos asignados
    """
    user = request.user

    # Transacciones pendientes del usuario
    mis_pendientes = (
        Transaccion.objects
        .select_related("categoria")
        .filter(usuario=user, estado="pendiente")
        .order_by("-fecha", "-id")
    )

    # Horas (lista plana para renderizar los detalles inline)
    mis_horas = (
        HoraTrabajo.objects
        .select_related("proyecto", "tarea")
        .filter(usuario=user)
        .order_by("-fecha", "-id")
    )

    # Agrupado por proyecto/área:
    # - nombre del grupo (proyecto o "—" si None)
    # - última fecha cargada (MAX)
    # - total de horas (SUM) → cuidado con DecimalField
    # - cantidad de registros
    mis_horas_grouped = (
        HoraTrabajo.objects
        .filter(usuario=user)
        .values(pid=Coalesce(F("proyecto_id"), Value(0)))
        .annotate(
            grupo_nombre=Coalesce(F("proyecto__nombre"), Value("—")),
            ultima=Max("fecha"),
            total_horas=Coalesce(
                Sum("horas"),
                Value(0),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            n_reg=Count("id"),
        )
        .order_by("grupo_nombre")
    )

    # Contador de proyectos asignados (responsable o miembro) no archivados
    proyectos_asignados = (
        Proyecto.objects
        .filter(Q(responsable=user) | Q(miembros=user), is_archivado=False)
        .distinct()
        .count()
    )

    # Accesos según permisos (ejemplo)
    accesos = []
    if user.has_perm("economia.view_transaccion"):
        accesos.append({
            "nombre": "Economía",
            "url": "/economia/",
            "descripcion": "Gestión de ingresos, gastos y balances.",
        })

    ESTADOS_ACTIVOS = ["todo", "doing", "review"]

    tareas_asignadas = (
        Tarea.objects
        .select_related("proyecto", "asignado_a")
        .filter(
            asignado_a=user,
            proyecto__is_archivado=False
        )
        .filter(estado__in=ESTADOS_ACTIVOS)       # si querés incluir todas, quitá esta línea
        .order_by(
            Case(When(vence_el__isnull=True, then=1), default=0, output_field=IntegerField()),
            "vence_el", "id"
        )
    )

    return render(
        request,
        "perfil.html",
        {
            "user": user,
            "accesos": accesos,
            "mis_pendientes": mis_pendientes,
            "mis_horas": mis_horas,                     # detalle inline
            "mis_horas_grouped": mis_horas_grouped,     # tabla agrupada
            "proyectos_asignados": proyectos_asignados,
            "tareas_asignadas": tareas_asignadas,
        },
    )


# ------------------------------------------------------------
# Modales de perfil (nombre y password)
# ------------------------------------------------------------
User = get_user_model()


class PerfilNombreForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name")
        labels = {"first_name": "Nombre", "last_name": "Apellido"}
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "vTextField", "autofocus": True}),
            "last_name": forms.TextInput(attrs={"class": "vTextField"}),
        }


@login_required
def perfil_editar_modal(request):
    user = request.user
    if request.method == "POST":
        form = PerfilNombreForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return JsonResponse({"ok": True})
        html = render_to_string("_perfil_nombre_form.html", {"form": form}, request=request)
        return JsonResponse({"ok": False, "html": html}, status=400)

    form = PerfilNombreForm(instance=user)
    html = render_to_string("_perfil_nombre_form.html", {"form": form}, request=request)
    return HttpResponse(html)


@login_required
def password_change_modal(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return JsonResponse({"ok": True})
        html = render_to_string("_password_change_form.html", {"form": form}, request=request)
        return JsonResponse({"ok": False, "html": html}, status=400)

    form = PasswordChangeForm(request.user)
    html = render_to_string("_password_change_form.html", {"form": form}, request=request)
    return HttpResponse(html)


# ------------------------------------------------------------
# (Opcional) Detalle por proyecto vía AJAX
# Se mantiene por compatibilidad si lo usás en otra parte.
# No interfiere con el detalle inline del perfil.
# ------------------------------------------------------------
@login_required
def horas_detalle(request, proyecto_id):
    user = request.user
    horas = (
        HoraTrabajo.objects
        .select_related("proyecto", "tarea")
        .filter(
            usuario=user,
            proyecto_id=proyecto_id if int(proyecto_id) != 0 else None
        )
        .order_by("-fecha")
    )
    return render(request, "partials/_horas_detalle.html", {"horas": horas})
