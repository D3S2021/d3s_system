# proyectos/views.py
from datetime import timedelta, datetime, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import (
    Q, Sum, Case, When, IntegerField, Max, Count, Value, CharField
)
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import now

from .models import (
    Proyecto, Tarea, Comentario, Adjunto,
    HistorialProyecto, FacturaProyecto,
    HoraTrabajo,
)
from .forms import (
    ProyectoForm, TareaForm, ComentarioForm, AdjuntoForm,
    FacturaForm, ReaperturaForm, CierreIncompletoForm,
    HoraTrabajoForm,
)

# Notificaciones opcionales
try:
    from notificaciones.models import Notificacion
except Exception:
    Notificacion = None


# ===========================
# Helpers
# ===========================
def _is_ajax(request) -> bool:
    """True si es una llamada AJAX (header clásico) o si nos marcan 'ajax=1'."""
    return (
        request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
        or request.POST.get("ajax") == "1"
        or request.GET.get("ajax") == "1"
    )


def _vencimientos_counter() -> int:
    hoy = now().date()
    limite_7 = hoy + timedelta(days=7)
    return (
        Tarea.objects.filter(
            proyecto__estado="en_progreso",
            estado__in=["todo", "doing", "review"],
            vence_el__isnull=False,
            vence_el__lte=limite_7,
        ).count()
    )


def _counts():
    return {
        "planificados": Proyecto.objects.filter(estado="planificado", is_archivado=False).count(),
        "presupuestados": Proyecto.objects.filter(estado="presupuestado", is_archivado=False).count(),
        "en_progreso":  Proyecto.objects.filter(estado="en_progreso",  is_archivado=False).count(),
        "finalizados":  Proyecto.objects.filter(estado="finalizado",   is_archivado=False).count(),
        "vencimientos": _vencimientos_counter(),
    }


def _qs_permitidos(request):
    if request.user.has_perm("proyectos.can_manage_proyectos"):
        return Proyecto.objects.all()
    return Proyecto.objects.filter(
        Q(responsable=request.user) | Q(miembros=request.user)
    ).distinct()


def _puede_tocar_proyecto(user, proyecto: Proyecto) -> bool:
    return (
        user.has_perm("proyectos.can_manage_proyectos")
        or (proyecto.responsable_id == user.id if proyecto.responsable_id else False)
    )


# ===========================
# Dashboard con tabs
# ===========================
@login_required
def dashboard(request):
    tab = request.GET.get("tab", "vencimientos")
    ctx = {"counts": _counts(), "current_tab": tab}
    ctx["proyectos_existentes"] = Proyecto.objects.order_by("-creado_en")[:200]

    if tab == "planificados":
        ctx["items"] = Proyecto.objects.filter(
            estado="planificado", is_archivado=False
        ).order_by("-creado_en")

    elif tab == "presupuestados":
        ctx["items"] = Proyecto.objects.filter(
            estado="presupuestado", is_archivado=False
        ).order_by("-creado_en")

    elif tab == "en_progreso":
        ctx["items"] = Proyecto.objects.filter(
            estado="en_progreso", is_archivado=False
        ).order_by("-creado_en")

    elif tab == "finalizados":
        ctx["items"] = Proyecto.objects.filter(
            estado="finalizado", is_archivado=False
        ).order_by("-creado_en")

    elif tab == "todos":
        ctx["items"] = Proyecto.objects.filter(
            is_archivado=False
        ).order_by("-creado_en")

    else:
        # Tab "vencimientos": agrupamos tareas con fecha de vencimiento por proyecto
        from itertools import groupby

        qs = (
            Tarea.objects
            .select_related("proyecto", "proyecto__responsable")
            .prefetch_related("asignados")  # <<< clave: múltiples asignados
            .filter(proyecto__is_archivado=False, vence_el__isnull=False)
            .order_by("proyecto__nombre", "proyecto_id", "vence_el", "id")
        )

        grupos = []
        for (pid, pnombre, _), tareas in groupby(
            qs, key=lambda t: (t.proyecto_id, t.proyecto.nombre, t.proyecto.fecha_fin)
        ):
            tareas = list(tareas)
            grupos.append({
                "proyecto": tareas[0].proyecto,
                "fecha_cierre": tareas[0].proyecto.fecha_fin,
                "tareas": tareas,
            })

        ctx["vencimientos_grouped"] = grupos
        ctx["hoy"] = now().date()

    return render(request, "proyectos/dashboard.html", ctx)


@login_required
def vencimientos(request):
    hoy = now().date()
    base = (
        Tarea.objects.select_related("proyecto", "asignado_a", "proyecto__responsable")
        .filter(
            proyecto__estado="en_progreso",
            estado__in=["todo", "doing", "review"],
            vence_el__isnull=False,
        )
    )
    proximos = base.filter(vence_el__gte=hoy).order_by("vence_el")[:50]
    ctx = {"counts": _counts(), "current_tab": "vencimientos", "proximos": proximos}
    return render(request, "proyectos/dashboard.html", ctx)


# ===========================
# Listado simple (con buscador)
# ===========================
@login_required
def proyecto_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Proyecto.objects.select_related("creado_por").order_by("-id")
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(creado_por__username__icontains=q) |
            Q(creado_por__first_name__icontains=q) |
            Q(creado_por__last_name__icontains=q)
        )
    page = request.GET.get("page")
    proyectos = Paginator(qs, 25).get_page(page)
    return render(request, "proyectos/lista.html", {"proyectos": proyectos, "q": q})


# ===========================
# Detalle / Historial / Facturación
# ===========================
@login_required
def proyecto_detalle(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    estados = dict(Tarea.ESTADOS)
    cols = {k: [] for k in estados.keys()}
    tareas_qs = (
        proyecto.tareas
        .select_related("asignado_a")
        .order_by(
            Case(When(vence_el__isnull=True, then=1), default=0, output_field=IntegerField()),
            "vence_el", "id",
        )
    )
    for t in tareas_qs:
        cols.setdefault(t.estado, []).append(t)

    # Si venimos de una notificación con ?open_task=<id>, el JS abrirá el modal
    return render(request, "proyectos/detalle.html", {
        "proyecto": proyecto,
        "estados": estados,
        "cols": cols,
        "hoy": now().date(),
        "form_tarea": TareaForm(),
        "form_comentario": ComentarioForm(),
        "form_adjunto": AdjuntoForm(),
        "estados_proyecto": Proyecto.ESTADOS,
    })


@login_required
def proyecto_cambiar_estado(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    if request.method == "POST":
        nuevo = (request.POST.get("estado") or "").strip()
        if nuevo in dict(Proyecto.ESTADOS):
            antes = proyecto.estado
            if nuevo != antes:
                proyecto.estado = nuevo
                proyecto.save(update_fields=["estado", "actualizado_en"])
                HistorialProyecto.objects.create(
                    proyecto=proyecto, tipo="estado_proyecto", actor=request.user,
                    descripcion=f"Estado del proyecto: {antes} → {nuevo}."
                )
                messages.success(request, "Estado del proyecto actualizado.")
        else:
            messages.error(request, "Estado inválido.")
    return redirect("proyectos:detalle", pk=pk)


@login_required
def proyecto_historial(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    eventos = proyecto.historial.select_related("actor").all()
    return render(request, "proyectos/historial.html", {"proyecto": proyecto, "eventos": eventos})


@login_required
def proyecto_facturacion(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    facturas = proyecto.facturas.all()
    total_facturado = facturas.aggregate(s=Sum("monto"))["s"] or 0
    presupuesto = proyecto.presupuesto_total or 0
    diff = (presupuesto - total_facturado) if presupuesto else None
    return render(request, "proyectos/facturacion.html", {
        "proyecto": proyecto,
        "facturas": facturas,
        "total_facturado": total_facturado,
        "presupuesto": presupuesto,
        "diff": diff,
        "form_factura": FacturaForm(),
    })


# ===========================
# ABM Proyecto (con modal AJAX)
# ===========================
@login_required
def proyecto_crear(request):
    """
    - GET  AJAX → devuelve HTML parcial del formulario (para el modal).
    - POST AJAX → devuelve JSON {ok: True, redirect: "..."} si guardó.
    - Fallback no-AJAX → render/redirect normal.
    """
    # Helper robusto para detectar AJAX:
    def _is_ajax(req):
        return (
            req.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
            or (req.POST.get("ajax") == "1")  # por si el browser bloquea headers
        )

    is_ajax = _is_ajax(request)

    if request.method == "POST":
        form = ProyectoForm(request.POST, request.FILES)
        if form.is_valid():
            p = form.save(commit=False)
            p.creado_por = request.user
            p.save()
            form.save_m2m()
            if is_ajax:
                return JsonResponse(
                    {"ok": True, "redirect": reverse("proyectos:detalle", args=[p.pk])}
                )
            messages.success(request, "Proyecto creado.")
            return redirect("proyectos:detalle", pk=p.pk)

        # inválido
        if is_ajax:
            html = render_to_string(
                "proyectos/_proyecto_form.html",
                {
                    "form": form,
                    # ⬇️ MUY IMPORTANTE: pasar action_url para que el <form> tenga destino correcto
                    "action_url": reverse("proyectos:nuevo"),
                    "submit_label": "Crear proyecto",
                    # (Opcional) datos para el selector "Duplicar de"
                    "mostrar_duplicar": True,
                    "proyectos_existentes": Proyecto.objects.order_by("-creado_en")[:200],
                },
                request=request,
            )
            return JsonResponse({"ok": False, "html": html}, status=400)

        return render(request, "proyectos/form.html", {"form": form, "titulo": "Nuevo proyecto"})

    # GET
    form = ProyectoForm()
    if is_ajax:
        html = render_to_string(
            "proyectos/_proyecto_form.html",
            {
                "form": form,
                # ⬇️ clave: que el partial lleve action correcto
                "action_url": reverse("proyectos:nuevo"),
                "submit_label": "Crear proyecto",
                "mostrar_duplicar": True,
                "proyectos_existentes": Proyecto.objects.order_by("-creado_en")[:200],
            },
            request=request,
        )
        return HttpResponse(html)

    # fallback no-AJAX
    return render(request, "proyectos/form.html", {"form": form, "titulo": "Nuevo proyecto"})


@login_required
def proyecto_api_json(request, pk):
    """Datos mínimos para 'Duplicar proyecto' (precargar el form del modal)."""
    p = get_object_or_404(Proyecto, pk=pk)
    data = {
        "nombre": p.nombre,
        "descripcion": p.descripcion or "",
        "estado": p.estado,
        "prioridad": p.prioridad,
        "responsable_id": p.responsable_id,
        "miembros_ids": list(p.miembros.values_list("id", flat=True)),
        "fecha_inicio": p.fecha_inicio.isoformat() if p.fecha_inicio else "",
        "fecha_fin": p.fecha_fin.isoformat() if p.fecha_fin else "",
        "presupuesto_total": str(p.presupuesto_total or ""),
        "is_archivado": p.is_archivado,
    }
    return JsonResponse(data)


@login_required
def proyecto_editar(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    if request.method == "POST":
        form = ProyectoForm(request.POST, request.FILES, instance=proyecto)
        if form.is_valid():
            form.save()
            messages.success(request, "Proyecto actualizado.")
            return redirect("proyectos:detalle", pk=pk)
    else:
        form = ProyectoForm(instance=proyecto)
    return render(request, "proyectos/form.html", {"form": form, "titulo": f"Editar: {proyecto.nombre}"})


@login_required
def editar_modal(request, pk: int):
    """GET: devuelve el form para modal. POST: guarda y devuelve JSON."""
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    action_url = reverse("proyectos:editar_modal", kwargs={"pk": proyecto.pk})

    def render_form(form):
        html = render_to_string(
            "proyectos/_proyecto_form.html",
            {"form": form, "action_url": action_url, "submit_label": "Guardar cambios", "mostrar_duplicar": False},
            request=request,
        )
        return html

    if request.method == "GET":
        form = ProyectoForm(instance=proyecto)
        return HttpResponse(render_form(form))

    form = ProyectoForm(request.POST, request.FILES, instance=proyecto)
    if form.is_valid():
        form.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "html": render_form(form)})


@login_required
def proyecto_archivar(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    proyecto.is_archivado = True
    proyecto.estado = "archivado"
    proyecto.save(update_fields=["is_archivado", "estado", "actualizado_en"])
    HistorialProyecto.objects.create(
        proyecto=proyecto, tipo="cierre", actor=request.user,
        descripcion="Proyecto archivado."
    )
    messages.success(request, "Proyecto archivado.")
    return redirect("proyectos:lista")


# ===========================
# Cierre / Reapertura
# ===========================
@login_required
def proyecto_cerrar(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    facturado = proyecto.facturas.aggregate(s=Sum("monto"))["s"] or 0
    presupuesto = proyecto.presupuesto_total or 0

    if presupuesto and facturado < presupuesto:
        if request.method == "POST":
            form = CierreIncompletoForm(request.POST)
            if form.is_valid():
                proyecto.facturacion_incompleta = True
                proyecto.estado = "finalizado"
                proyecto.save(update_fields=["facturacion_incompleta", "estado", "actualizado_en"])
                motivo = form.cleaned_data["motivo"]
                HistorialProyecto.objects.create(
                    proyecto=proyecto, tipo="cierre_incompleto", actor=request.user,
                    descripcion=f"Cierre con facturación incompleta. Motivo: {motivo}"
                )
                if Notificacion and proyecto.responsable:
                    Notificacion.objects.create(
                        user=proyecto.responsable,
                        titulo=f"Proyecto '{proyecto.nombre}' cerrado con facturación incompleta",
                        cuerpo=f"Cerrado por {request.user.get_username()}. Motivo: {motivo}",
                        url=f"/proyectos/{proyecto.id}/historial/",
                    )
                messages.warning(request, "Proyecto cerrado con facturación incompleta.")
                return redirect("proyectos:detalle", pk=pk)
        else:
            form = CierreIncompletoForm()
        return render(request, "proyectos/cierre_incompleto.html", {"proyecto": proyecto, "form": form})

    proyecto.estado = "finalizado"
    proyecto.save(update_fields=["estado", "actualizado_en"])
    HistorialProyecto.objects.create(
        proyecto=proyecto, tipo="cierre", actor=request.user, descripcion="Proyecto marcado como finalizado."
    )
    messages.success(request, "Proyecto finalizado.")
    return redirect("proyectos:detalle", pk=pk)

from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .models import Proyecto  # asegúrate del import correcto

@require_POST
def proyecto_cambiar_estado(request, pk):
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Login requerido.")

    proyecto = get_object_or_404(Proyecto, pk=pk)

    # Opcional: si querés restringir quién puede cambiar el estado:
    # if not request.user.has_perm("proyectos.change_proyecto"):
    #     return HttpResponseForbidden("No tenés permisos.")

    nuevo_estado = (request.POST.get("estado") or "").strip()
    # Validamos contra las choices del modelo
    valid_values = {k for k, _ in getattr(Proyecto, "ESTADOS", [])} or {
        "nuevo", "en_curso", "en_pausa", "finalizado", "cancelado"
    }
    if nuevo_estado not in valid_values:
        return HttpResponseBadRequest("Estado inválido.")

    proyecto.estado = nuevo_estado
    proyecto.save(update_fields=["estado"])

    # Para actualizar el label visible sin recargar
    display_map = dict(getattr(Proyecto, "ESTADOS", []))
    return JsonResponse({"ok": True, "estado": nuevo_estado, "display": display_map.get(nuevo_estado, nuevo_estado)})


@login_required
def proyecto_reabrir(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    pendientes = list(proyecto.tareas.filter(estado__in=["todo", "doing", "review"]))

    if request.method == "POST":
        form = ReaperturaForm(request.POST)
        if form.is_valid():
            faltan, updates = [], []
            for t in pendientes:
                key = f"vence_el_{t.id}"
                raw = (request.POST.get(key) or "").strip()
                if not raw:
                    faltan.append(t.titulo)
                else:
                    updates.append((t, raw))
            if faltan:
                messages.error(request, "Debés cargar fecha para todas las tareas pendientes.")
            else:
                for t, iso in updates:
                    t.vence_el = iso
                    t.save(update_fields=["vence_el", "actualizado_en"])
                proyecto.estado = "planificado"
                proyecto.facturacion_incompleta = False
                proyecto.save(update_fields=["estado", "facturacion_incompleta", "actualizado_en"])
                HistorialProyecto.objects.create(
                    proyecto=proyecto, tipo="reapertura", actor=request.user,
                    descripcion=(f"Proyecto reabierto. Motivo: {form.cleaned_data['motivo']}. "
                                 f"Tareas reabiertas: {len(updates)}.")
                )
                if Notificacion:
                    if proyecto.responsable:
                        Notificacion.objects.create(
                            user=proyecto.responsable,
                            titulo=f"Proyecto '{proyecto.nombre}' reabierto",
                            cuerpo=f"Motivo: {form.cleaned_data['motivo']}. Tareas reabiertas: {len(updates)}.",
                            url=f"/proyectos/{proyecto.id}/",
                        )
                    for t, _ in updates:
                        for u in t.asignados.all():
                            Notificacion.objects.create(
                                user=u,
                                titulo=f"Tarea reabierta: {t.titulo}",
                                cuerpo=f"Nuevo vencimiento: {t.vence_el:%d/%m/%Y} (Proyecto {proyecto.nombre})",
                                url=reverse("proyectos:tarea_open", args=[t.id]),
                            )

                messages.success(request, "Proyecto reabierto y tareas actualizadas.")
                return redirect("proyectos:detalle", pk=pk)
    else:
        form = ReaperturaForm()

    return render(request, "proyectos/reapertura.html", {"proyecto": proyecto, "form": form, "pendientes": pendientes})


# ===========================
# TAREAS
# ===========================
def _exclude_admin(form):
    """Oculta 'admin' del/los select(s) de asignación si existen."""
    # Caso FK antiguo
    if "asignado_a" in form.fields:
        qs = form.fields["asignado_a"].queryset
        form.fields["asignado_a"].queryset = qs.exclude(username__iexact="admin")
    # Caso M2M nuevo
    if "asignados" in form.fields:
        qs = form.fields["asignados"].queryset
        form.fields["asignados"].queryset = qs.exclude(username__iexact="admin")

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from .models import Tarea

@login_required
def tomar_tarea(request, pk):
    """
    Permite a un usuario 'quedarse' con una tarea que está asignada a múltiples personas.
    Requisitos:
      - el usuario debe estar entre los asignados
      - la tarea debe tener más de un asignado
      - POST únicamente
    Efecto:
      - deja como único asignado al usuario actual
    """
    if request.method != "POST":
        return redirect(request.META.get("HTTP_REFERER") or reverse("perfil"))

    tarea = get_object_or_404(Tarea, pk=pk)
    # si no usás 'asignados' M2M, reemplazá por el nombre que tengas
    if not tarea.asignados.filter(pk=request.user.pk).exists():
        messages.error(request, "No estás asignado a esta tarea.")
        return redirect(request.POST.get("next") or reverse("perfil"))

    if tarea.asignados.count() <= 1:
        messages.info(request, "La tarea ya está tomada por una sola persona.")
        return redirect(request.POST.get("next") or reverse("perfil"))

    # dejar solo al usuario actual
    tarea.asignados.set([request.user])
    tarea.save(update_fields=[])  # no hace falta campos; mantiene updated_at si tenés auto_now
    messages.success(request, "Tomaste la tarea. Ahora sos el único asignado.")
    return redirect(request.POST.get("next") or reverse("perfil"))


# ========= CREAR TAREA =========
@login_required
def tarea_crear(request, proyecto_id):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=proyecto_id)
    is_ajax = (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"

    # GET → devolver el formulario (partial) para el modal
    if request.method == "GET" and request.GET.get("modal") == "1":
        form = TareaForm()
        _exclude_admin(form)
        html = render_to_string(
            "proyectos/_tarea_form.html",
            {
                "form": form,
                "action_url": reverse("proyectos:tarea_crear", args=[proyecto.id]),
                "submit_label": "Crear tarea",
            },
            request=request,
        )
        return HttpResponse(html)

    # POST → guardar
    if request.method == "POST":
        form = TareaForm(request.POST)
        _exclude_admin(form)
        if form.is_valid():
            t = form.save(commit=False)
            t.proyecto = proyecto
            t.creado_por = request.user
            t.save()
            form.save_m2m()  # ← imprescindible para 'asignados' (M2M)

            # Notificaciones a asignados (excepto quien crea)
            if Notificacion:
                if hasattr(t, "asignados"):
                    for u in t.asignados.exclude(id=request.user.id):
                        Notificacion.objects.create(
                            user=u,
                            titulo=f"Nueva tarea en {proyecto.nombre}",
                            cuerpo=f"{t.titulo}",
                            url=reverse("proyectos:tarea_open", args=[t.id]),
                        )
                elif getattr(t, "asignado_a_id", None) and t.asignado_a_id != request.user.id:
                    # Compat FK antiguo si existiera
                    Notificacion.objects.create(
                        user=t.asignado_a,
                        titulo=f"Nueva tarea en {proyecto.nombre}",
                        cuerpo=f"{t.titulo}",
                        url=reverse("proyectos:tarea_open", args=[t.id]),
                    )

            HistorialProyecto.objects.create(
                proyecto=proyecto,
                tipo="estado_tarea",
                actor=request.user,
                descripcion=f"Creada tarea '{t.titulo}' (estado {t.get_estado_display()}).",
            )

            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Tarea creada.")
            return redirect("proyectos:detalle", pk=proyecto.id)

        # inválido → partial con errores si es AJAX
        if is_ajax:
            html = render_to_string(
                "proyectos/_tarea_form.html",
                {
                    "form": form,
                    "action_url": reverse("proyectos:tarea_crear", args=[proyecto.id]),
                    "submit_label": "Crear tarea",
                },
                request=request,
            )
            return JsonResponse({"ok": False, "html": html}, status=400)

    # fallback
    return redirect("proyectos:detalle", pk=proyecto.id)


@login_required
def tarea_detalle_modal(request, pk: int):
    tarea = get_object_or_404(
        Tarea.objects.select_related("proyecto", "asignado_a"),  # select_related del FK no molesta
        pk=pk
    )
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)

    mensajes = (
        Comentario.objects
        .select_related("autor")
        .filter(tarea=tarea)
        .order_by("creado_en")
    )

    puede_chatear = (
        request.user.has_perm("proyectos.can_manage_proyectos")
        or (tarea.proyecto and tarea.proyecto.responsable_id == request.user.id)
        or (hasattr(tarea, "asignados") and tarea.asignados.filter(id=request.user.id).exists())
        or (getattr(tarea, "asignado_a_id", None) == request.user.id)  # compat FK
    )

    html = render_to_string(
        "proyectos/_tarea_detalle.html",
        {"t": tarea, "mensajes": mensajes, "puede_chatear": puede_chatear},
        request=request,
    )
    resp = HttpResponse(html)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@login_required
def tarea_chat_enviar(request, pk: int):
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=pk)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)

    puede_chatear = (
        request.user.has_perm("proyectos.can_manage_proyectos")
        or (tarea.proyecto and tarea.proyecto.responsable_id == request.user.id)
        or (hasattr(tarea, "asignados") and tarea.asignados.filter(id=request.user.id).exists())
        or (getattr(tarea, "asignado_a_id", None) == request.user.id)
    )
    if not puede_chatear:
        return JsonResponse({"ok": False, "error": "Sin permiso para chatear en esta tarea."}, status=403)

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método inválido."}, status=405)

    cuerpo = (request.POST.get("mensaje") or "").strip()
    if not cuerpo:
        return JsonResponse({"ok": False, "error": "Escribí un mensaje."}, status=400)

    msg = Comentario.objects.create(tarea=tarea, autor=request.user, cuerpo=cuerpo)

    html = render_to_string("proyectos/_tarea_chat_message.html", {"m": msg}, request=request)
    response = JsonResponse({"ok": True, "html": html})
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


# ========= EDITAR TAREA =========
@login_required
def tarea_editar(request, pk):
    """
    - GET ?modal=1 → devuelve el partial del form con la instancia.
    - POST (AJAX)   → valida/guarda y responde JSON.
    - Fallback      → redirect al detalle.
    """
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=pk)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)

    def _render(form):
        html = render_to_string(
            "proyectos/_tarea_form.html",
            {"form": form, "submit_label": "Guardar cambios"},
            request=request,
        )
        return html

    # GET modal
    if request.method == "GET" and request.GET.get("modal") == "1":
        form = TareaForm(instance=tarea)
        _exclude_admin(form)
        return HttpResponse(_render(form))

    # POST (guardar)
    if request.method == "POST":
        is_ajax = _is_ajax(request)

        # Para detectar nuevos asignados (M2M)
        antes_ids = set()
        if hasattr(tarea, "asignados"):
            antes_ids = set(tarea.asignados.values_list("id", flat=True))

        form = TareaForm(request.POST, instance=tarea)
        _exclude_admin(form)
        if form.is_valid():
            antes_estado = tarea.estado
            t = form.save()  # commit=True → Django guarda M2M automáticamente

            # Notificar a los NUEVOS asignados (M2M)
            if Notificacion and hasattr(t, "asignados"):
                despues_ids = set(t.asignados.values_list("id", flat=True))
                nuevos = despues_ids - antes_ids
                for uid in nuevos:
                    if uid != request.user.id:
                        Notificacion.objects.create(
                            user_id=uid,
                            titulo=f"Tarea actualizada en {t.proyecto.nombre}",
                            cuerpo=f"{t.titulo}",
                            url=reverse("proyectos:tarea_open", args=[t.id]),
                        )

            # Historial por cambio de estado
            if antes_estado != t.estado:
                HistorialProyecto.objects.create(
                    proyecto=t.proyecto,
                    tipo="estado_tarea",
                    actor=request.user,
                    descripcion=f"Cambio de estado: '{t.titulo}' {antes_estado} → {t.estado}.",
                )

            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Tarea actualizada.")
            return redirect("proyectos:detalle", pk=t.proyecto_id)

        # inválido
        if is_ajax:
            return JsonResponse({"ok": False, "html": _render(form)}, status=400)

    # fallback
    return redirect("proyectos:detalle", pk=tarea.proyecto_id)


@login_required
def tarea_cambiar_estado(request, pk):
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=pk)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)

    is_ajax = (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"
    action = (request.POST.get("action") or "").strip().lower()

    # ==== NUEVO: acciones de flujo rápido desde el modal ====
    if action in {"start", "finish"}:
        # Debe estar asignado (por M2M o FK antiguo)
        asignado = False
        if hasattr(tarea, "asignados"):
            asignado = tarea.asignados.filter(id=request.user.id).exists()
        if getattr(tarea, "asignado_a_id", None) == request.user.id:
            asignado = True

        if not asignado:
            if is_ajax:
                return JsonResponse({"ok": False, "error": "No estás asignado a esta tarea."}, status=403)
            messages.error(request, "No estás asignado a esta tarea.")
            ref = request.META.get("HTTP_REFERER")
            return redirect(ref) if ref else redirect("proyectos:detalle", pk=tarea.proyecto_id)

        antes = tarea.estado
        if action == "start":
            if tarea.estado != "todo":
                if is_ajax:
                    return JsonResponse({"ok": False, "error": "Solo se puede empezar si está 'Por hacer'."}, status=400)
                messages.error(request, "Solo se puede empezar si la tarea está 'Por hacer'.")
            else:
                tarea.estado = "doing"
                # Se la queda el usuario que la empieza
                if hasattr(tarea, "asignados"):
                    tarea.asignados.set([request.user])
                elif hasattr(tarea, "asignado_a_id"):
                    tarea.asignado_a = request.user
                tarea.save(update_fields=["estado", "actualizado_en"])

                HistorialProyecto.objects.create(
                    proyecto=tarea.proyecto, tipo="estado_tarea", actor=request.user,
                    descripcion=f"Cambio de estado: '{tarea.titulo}' {antes} → {tarea.estado}."
                )

                if Notificacion and tarea.proyecto.responsable:
                    Notificacion.objects.create(
                        user=tarea.proyecto.responsable,
                        titulo="Estado de tarea cambiado",
                        cuerpo=f"{tarea.titulo}: {antes} → {tarea.estado} (Proyecto {tarea.proyecto.nombre})",
                        url=reverse("proyectos:tarea_open", args=[tarea.id]),
                    )

                if is_ajax:
                    return JsonResponse({"ok": True, "estado": tarea.estado})
                messages.success(request, "Tarea iniciada.")
        elif action == "finish":
            if tarea.estado != "doing":
                if is_ajax:
                    return JsonResponse({"ok": False, "error": "Solo se puede terminar si está 'En curso'."}, status=400)
                messages.error(request, "Solo se puede terminar si la tarea está 'En curso'.")
            else:
                tarea.estado = "review"  # pasa a En revisión
                tarea.save(update_fields=["estado", "actualizado_en"])

                HistorialProyecto.objects.create(
                    proyecto=tarea.proyecto, tipo="estado_tarea", actor=request.user,
                    descripcion=f"Cambio de estado: '{tarea.titulo}' {antes} → {tarea.estado}."
                )

                if Notificacion and tarea.proyecto.responsable:
                    Notificacion.objects.create(
                        user=tarea.proyecto.responsable,
                        titulo="Tarea para revisión",
                        cuerpo=f"{tarea.titulo} quedó lista para revisión (Proyecto {tarea.proyecto.nombre})",
                        url=reverse("proyectos:tarea_open", args=[tarea.id]),
                    )

                if is_ajax:
                    return JsonResponse({"ok": True, "estado": tarea.estado})
                messages.success(request, "Tarea enviada a revisión.")

        # Si no es AJAX, seguimos el redirect estándar
        ref = request.META.get("HTTP_REFERER")
        return redirect(ref) if ref else redirect("proyectos:detalle", pk=tarea.proyecto_id)
    # ==== FIN NUEVO ====

    # --- Lógica existente: cambio directo via POST["estado"] ---
    nuevo = request.POST.get("estado")
    if nuevo in dict(Tarea.ESTADOS):
        antes = tarea.estado
        tarea.estado = nuevo
        tarea.save(update_fields=["estado", "actualizado_en"])

        HistorialProyecto.objects.create(
            proyecto=tarea.proyecto, tipo="estado_tarea", actor=request.user,
            descripcion=f"Cambio de estado: '{tarea.titulo}' {antes} → {tarea.estado}."
        )

        if Notificacion and tarea.proyecto.responsable:
            Notificacion.objects.create(
                user=tarea.proyecto.responsable,
                titulo=f"Estado de tarea cambiado",
                cuerpo=f"{tarea.titulo}: {antes} → {tarea.estado} (Proyecto {tarea.proyecto.nombre})",
                url=reverse("proyectos:tarea_open", args=[tarea.id]),
            )
        if Notificacion:
            for u in tarea.asignados.all():
                Notificacion.objects.create(
                    user=u,
                    titulo=f"Estado de tarea cambiado",
                    cuerpo=f"{tarea.titulo}: {antes} → {tarea.estado} (Proyecto {tarea.proyecto.nombre})",
                    url=reverse("proyectos:tarea_open", args=[tarea.id]),
                )
        messages.success(request, "Estado actualizado.")

    ref = request.META.get("HTTP_REFERER")
    if ref:
        return redirect(ref)
    return redirect("proyectos:detalle", pk=tarea.proyecto_id)


@login_required
def tarea_eliminar(request, pk):
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=pk)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)
    proyecto_id = tarea.proyecto_id
    titulo = tarea.titulo
    tarea.delete()
    HistorialProyecto.objects.create(
        proyecto_id=proyecto_id, tipo="estado_tarea", actor=request.user,
        descripcion=f"Tarea eliminada: '{titulo}'."
    )
    messages.success(request, "Tarea eliminada.")
    return redirect("proyectos:detalle", pk=proyecto_id)


# ===========================
# Comentarios & Adjuntos
# ===========================
@login_required
def comentario_agregar(request, tarea_id):
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=tarea_id)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)

    if request.method == "POST":
        form = ComentarioForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.tarea = tarea
            c.autor = request.user
            c.save()
            HistorialProyecto.objects.create(
                proyecto=tarea.proyecto,
                tipo="estado_tarea",
                actor=request.user,
                descripcion=f"Comentario en '{tarea.titulo}': {c.cuerpo[:120]}"
            )
            messages.success(request, "Comentario agregado.")
        else:
            messages.error(request, "Revisá el comentario.")
    return redirect("proyectos:detalle", pk=tarea.proyecto_id)


@login_required
def adjunto_subir(request, tarea_id):
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=tarea_id)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)

    if request.method == "POST":
        form = AdjuntoForm(request.POST, request.FILES)
        if form.is_valid():
            a = form.save(commit=False)
            a.tarea = tarea
            a.subido_por = request.user
            a.save()
            HistorialProyecto.objects.create(
                proyecto=tarea.proyecto,
                tipo="estado_tarea",
                actor=request.user,
                descripcion=f"Adjunto subido en '{tarea.titulo}': {a.archivo.name}"
            )
            messages.success(request, "Archivo adjuntado.")
        else:
            messages.error(request, "No se pudo adjuntar el archivo.")
    return redirect("proyectos:detalle", pk=tarea.proyecto_id)


# ===========================
# Kanban
# ===========================
@login_required
def kanban_proyecto(request, pk):
    proyecto = get_object_or_404(_qs_permitidos(request), pk=pk)
    estados = dict(Tarea.ESTADOS)
    qs = proyecto.tareas.select_related("asignado_a")
    cols = {k: [] for k in estados.keys()}
    for t in qs:
        cols.get(t.estado, []).append(t)
    hoy = now().date()
    return render(request, "proyectos/kanban.html", {
        "proyecto": proyecto,
        "estados": estados,
        "cols": cols,
        "hoy": hoy,
    })


# ===========================
# Horas de trabajo
# ===========================
@login_required
def horas_nueva(request):
    """
    Modal de carga de horas. En GET AJAX devolvemos HTML.
    En POST AJAX devolvemos JSON. Se exige SIEMPRE cargar inicio y fin.
    """
    puede_asignar = (
        request.user.has_perm("proyectos.can_manage_proyectos") or request.user.is_staff
    )
    is_ajax = _is_ajax(request)

    preselect_proyecto_id = request.GET.get("proyecto")

    if request.method == "POST":
        # 👇 Inyectamos el usuario logueado si NO puede asignar horas a otros
        if not puede_asignar:
            data = request.POST.copy()
            data["usuario"] = str(request.user.pk)
        else:
            data = request.POST

        form = HoraTrabajoForm(
            data,
            request_user=request.user,
            puede_asignar=puede_asignar,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            if not puede_asignar:
                obj.usuario = request.user  # doble seguridad del lado servidor

            inicio = form.cleaned_data.get("inicio")
            fin = form.cleaned_data.get("fin")

            if not inicio:
                form.add_error("inicio", "Este campo es obligatorio.")
            if not fin:
                form.add_error("fin", "Este campo es obligatorio.")

            if inicio and fin:
                # Aceptamos tanto time objects como strings "HH:MM"
                from datetime import datetime, date
                if isinstance(inicio, str) or isinstance(fin, str):
                    try:
                        ini_dt = datetime.strptime(str(inicio).strip(), "%H:%M")
                        fin_dt = datetime.strptime(str(fin).strip(), "%H:%M")
                        delta_h = (fin_dt - ini_dt).seconds / 3600.0
                    except Exception:
                        form.add_error(None, "Formato de hora inválido. Usá HH:MM.")
                        delta_h = None
                else:
                    ini_dt = datetime.combine(date.today(), inicio)
                    fin_dt = datetime.combine(date.today(), fin)
                    total_secs = (fin_dt - ini_dt).total_seconds()
                    delta_h = total_secs / 3600.0

                if delta_h is not None:
                    if delta_h <= 0:
                        form.add_error(None, "La hora de fin debe ser posterior a la de inicio.")
                    else:
                        obj.horas = round(delta_h, 2)

            if form.errors or getattr(obj, "horas", None) is None:
                if getattr(obj, "horas", None) is None and not form.errors:
                    form.add_error(None, "Debés completar Inicio y Fin para calcular las horas.")
                if is_ajax:
                    html = render_to_string(
                        "proyectos/_horas_form.html",
                        {"form": form, "puede_asignar": puede_asignar},
                        request=request,
                    )
                    return JsonResponse({"ok": False, "html": html}, status=400)
                return render(
                    request,
                    "proyectos/horas_form.html",
                    {"form": form, "titulo": "Cargar horas", "puede_asignar": puede_asignar},
                )

            obj.save()
            if is_ajax:
                return JsonResponse({"ok": True})
            messages.success(request, "Horas cargadas.")
            return redirect("proyectos:horas_mias")

        # form inválido
        if is_ajax:
            html = render_to_string(
                "proyectos/_horas_form.html",
                {"form": form, "puede_asignar": puede_asignar},
                request=request,
            )
            return JsonResponse({"ok": False, "html": html}, status=400)

    else:
        initial = {}
        if preselect_proyecto_id:
            try:
                initial["proyecto"] = int(preselect_proyecto_id)
            except (TypeError, ValueError):
                pass

        # 👇 si NO puede asignar, pre-cargamos su propio usuario (aunque el campo esté oculto)
        if not puede_asignar:
            initial["usuario"] = request.user.pk

        form = HoraTrabajoForm(
            request_user=request.user,
            puede_asignar=puede_asignar,
            initial=initial,
        )
        if is_ajax:
            html = render_to_string(
                "proyectos/_horas_form.html",
                {"form": form, "puede_asignar": puede_asignar},
                request=request,
            )
            return HttpResponse(html)

    return render(
        request,
        "proyectos/horas_form.html",
        {"form": form, "titulo": "Cargar horas", "puede_asignar": puede_asignar},
    )


@login_required
def horas_mias(request):
    qs = (HoraTrabajo.objects
          .select_related("proyecto", "tarea")
          .filter(usuario=request.user))

    agrupado = (
        qs.annotate(
            grupo_nombre=Coalesce("proyecto__nombre", Value("—"), output_field=CharField()),
            pid=Coalesce("proyecto_id", Value(0)),
        )
        .values("pid", "grupo_nombre")
        .annotate(total_horas=Sum("horas"), ultima=Max("fecha"), n_reg=Count("id"))
        .order_by("-ultima", "grupo_nombre")
    )

    return render(request, "proyectos/horas_mias.html", {
        "titulo": "Mis horas",
        "agrupado": agrupado,
    })


@login_required
@permission_required("proyectos.can_manage_economia", raise_exception=True)
def horas_economia_list(request):
    estado = request.GET.get("estado", "todas")
    qs = HoraTrabajo.objects.select_related("usuario", "proyecto", "tarea")
    if estado in {"cargada", "aprobada", "rechazada"}:
        qs = qs.filter(estado=estado)
    return render(request, "proyectos/horas_economia.html", {
        "items": qs,
        "estado": estado,
        "titulo": "Horas de trabajo",
    })


@login_required
@permission_required("proyectos.can_manage_economia", raise_exception=True)
def horas_aprobar(request, pk):
    h = get_object_or_404(HoraTrabajo, pk=pk)
    h.estado = "aprobada"
    h.aprobada_por = request.user
    h.aprobada_en = now()
    h.save(update_fields=["estado", "aprobada_por", "aprobada_en", "actualizado_en"])
    messages.success(request, "Hora aprobada.")
    return redirect(request.META.get("HTTP_REFERER") or "proyectos:horas_economia")


@login_required
@permission_required("proyectos.can_manage_economia", raise_exception=True)
def horas_rechazar(request, pk):
    h = get_object_or_404(HoraTrabajo, pk=pk)
    h.estado = "rechazada"
    h.aprobada_por = request.user
    h.aprobada_en = now()
    h.save(update_fields=["estado", "aprobada_por", "aprobada_en", "actualizado_en"])
    messages.warning(request, "Hora rechazada.")
    return redirect(request.META.get("HTTP_REFERER") or "proyectos:horas_economia")


# ===========================
# Item C: redirección que abre el modal de tarea
# ===========================
@login_required
def tarea_open(request, pk: int):
    """
    Redirige a la página del proyecto con ?open_task=<pk>.
    El front debe detectar ese query param y abrir el modal
    llamando a `tarea_detalle_modal`.
    """
    tarea = get_object_or_404(Tarea.objects.select_related("proyecto"), pk=pk)
    _ = get_object_or_404(_qs_permitidos(request), pk=tarea.proyecto_id)
    url = reverse("proyectos:detalle", args=[tarea.proyecto_id]) + f"?open_task={tarea.id}"
    return redirect(url)
