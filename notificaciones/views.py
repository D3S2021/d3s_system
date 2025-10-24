# notificaciones/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Notificacion


@login_required
def lista_notificaciones(request: HttpRequest) -> HttpResponse:
    """
    Lista todas las notificaciones del usuario.
    Por defecto ordena: no leídas primero y, dentro de eso, de más nueva a más vieja.
    Permite filtrar solo no leídas con ?only_unread=1
    """
    qs = Notificacion.objects.filter(user=request.user)
    if request.GET.get("only_unread") in {"1", "true", "True"}:
        qs = qs.filter(leida=False)

    notifs = qs.order_by("leida", "-creada")
    return render(request, "notificaciones/lista.html", {"notificaciones": notifs})


@login_required
def detalle(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Muestra el detalle de la notificación y la marca como leída si no lo estaba.
    """
    n = get_object_or_404(Notificacion, pk=pk, user=request.user)

    if not n.leida:
        n.leida = True
        n.save(update_fields=["leida"])

    return render(request, "notificaciones/detalle.html", {"n": n})


@login_required
def marcar_leida(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Marca una notificación como leída y redirige a la lista (o al next si viene).
    """
    n = get_object_or_404(Notificacion, pk=pk, user=request.user)
    if not n.leida:
        n.leida = True
        n.save(update_fields=["leida"])

    messages.success(request, "Notificación marcada como leída.")
    return redirect(request.GET.get("next") or "notificaciones:lista")


@login_required
def marcar_todas(request: HttpRequest) -> HttpResponse:
    """
    Marca todas las notificaciones del usuario como leídas y redirige a la lista.
    """
    updated = (
        Notificacion.objects.filter(user=request.user, leida=False).update(leida=True)
    )
    if updated:
        messages.success(request, "Todas las notificaciones fueron marcadas como leídas.")
    else:
        messages.info(request, "No había notificaciones nuevas para marcar.")

    return redirect(request.GET.get("next") or "notificaciones:lista")


# ----- Endpoints JSON (para AJAX) ---------------------------------------------

@login_required
@require_POST
def api_marcar_leida(request: HttpRequest, pk: int) -> JsonResponse:
    """
    Marca una notificación como leída (JSON).
    """
    n = get_object_or_404(Notificacion, pk=pk, user=request.user)
    if not n.leida:
        n.leida = True
        n.save(update_fields=["leida"])
    return JsonResponse({"ok": True, "id": n.pk, "leida": True})


@login_required
@require_POST
def api_marcar_todas(request: HttpRequest) -> JsonResponse:
    """
    Marca todas las notificaciones como leídas (JSON).
    """
    count = Notificacion.objects.filter(user=request.user, leida=False).update(leida=True)
    return JsonResponse({"ok": True, "marcadas": count})
