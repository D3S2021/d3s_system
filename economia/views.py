from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q, Value, DecimalField, CharField
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import now
from django.db.models.functions import Coalesce, Cast

from proyectos.models import HoraTrabajo

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from datetime import date
import re

from .forms import GastoForm, GastoOwnEditForm, CategoriaQuickForm
from .models import Transaccion, Categoria, PlanMensual
from notificaciones.models import Notificacion


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def _safe_int(v, default: int):
    """
    Convierte cadenas como '2%C2%A0025', '2 025', '2,025' → 2025.
    Quita todo lo que no sea dígito. Si queda vacío, devuelve default.
    """
    if v is None:
        return default
    s = str(v).replace("\u00A0", " ")  # NBSP a espacio normal
    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else default


def _to_decimal(x) -> Decimal:
    """Convierte a Decimal tolerando None/str con separadores."""
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    s = str(x).strip()
    # tolera "1.234,56" o "1234,56" o "1,234.56"
    if "," in s and "." in s:
        # uso el último separador como decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def dashboard_economia(request):
    """Panel principal de Economía: totales del mes + últimas + pendientes."""
    hoy = now().date()
    year = hoy.year
    month = hoy.month

    aprobados_mes = Transaccion.objects.filter(
        estado="aprobado", fecha__year=hoy.year, fecha__month=hoy.month
    )
    total_ingresos = (
        aprobados_mes.filter(categoria__tipo="ingreso").aggregate(s=Sum("monto"))["s"] or 0
    )
    total_gastos = (
        aprobados_mes.filter(categoria__tipo="gasto").aggregate(s=Sum("monto"))["s"] or 0
    )
    saldo = total_ingresos - total_gastos

    ultimas = (
        Transaccion.objects.select_related("categoria", "usuario")
        .filter(estado="aprobado")
        .order_by("-fecha", "-id")[:10]
    )

    pendientes = (
        Transaccion.objects.select_related("categoria", "usuario")
        .filter(estado="pendiente")
        .order_by("-fecha", "-id")[:20]
    )

    if request.method == "POST":
        aprobar_ids = request.POST.getlist("aprobar")
        rechazar_ids = request.POST.getlist("rechazar")

        if aprobar_ids:
            Transaccion.objects.filter(
                id__in=aprobar_ids, estado="pendiente"
            ).update(estado="aprobado", validado_por=request.user, validado_en=now())

        if rechazar_ids:
            Transaccion.objects.filter(
                id__in=rechazar_ids, estado="pendiente"
            ).update(estado="rechazado", validado_por=request.user, validado_en=now())

        return redirect("economia:dashboard")

    return render(
        request,
        "economia/dashboard.html",
        {
            "total_ingresos": total_ingresos,
            "total_gastos": total_gastos,
            "saldo": saldo,
            "ultimas": ultimas,
            "pendientes": pendientes,
            "year": year,
            "month": month,
        },
    )


# ---------------------------------------------------------------------------
# Nueva transacción (cargadores y validadores)
# ---------------------------------------------------------------------------

@login_required
def nueva_transaccion(request):
    """
    GET:
      - Si viene desde el modal (fetch), devolvemos SOLO el formulario (partial).
      - Si entran por URL directa, devolvemos la página completa.
    POST:
      - Si es válido -> guardamos y redirigimos a 'perfil'.
      - Si hay errores -> devolvemos el partial (si fetch) o la página completa (si normal).
    """
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or request.headers.get("HX-Request") == "true"

    if request.method == "POST":
        form = GastoForm(request.POST, user=request.user)
        if form.is_valid():
            tx = form.save(commit=False)
            tx.usuario = request.user
            tx.estado = "pendiente"

            # Si no puede cargar ingresos, forzamos "gasto" sin categoría explícita
            if not request.user.has_perm("economia.can_add_ingresos"):
                tx.categoria = None

            tx.save()
            messages.success(request, "✅ Transacción enviada para validación.")
            return redirect("perfil")
    else:
        form = GastoForm(user=request.user)

    if is_ajax:
        html = render_to_string("economia/_form_transaccion.html", {"form": form}, request=request)
        return HttpResponse(html)

    return render(request, "economia/nueva_transaccion.html", {"form": form})


@login_required
def editar_mia_desde_perfil(request, pk):
    """
    Edición de una transacción propia (solo si está pendiente).
    El formulario no muestra categoría para usuarios no-validadores.
    """
    tx = get_object_or_404(Transaccion, pk=pk)

    if tx.usuario_id != request.user.id or tx.estado != "pendiente":
        return HttpResponseForbidden("No tenés permisos para editar esta transacción.")

    if request.method == "POST":
        form = GastoForm(request.POST, instance=tx, user=request.user)
        if "categoria" in form.fields:
            del form.fields["categoria"]
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Transacción actualizada correctamente.")
            return redirect("perfil")
    else:
        form = GastoForm(instance=tx, user=request.user)
        if "categoria" in form.fields:
            del form.fields["categoria"]

    return render(
        request,
        "economia/nueva_transaccion.html",
        {"form": form, "modo_edicion": True, "tx": tx},
    )


@login_required
def editar_transaccion(request, pk):
    """
    Edición general:
    - Validador: usa GastoForm completo.
    - Dueño: solo si pendiente y con permiso can_edit_own_transactions (usa GastoOwnEditForm).
    """
    tx = get_object_or_404(Transaccion.objects.select_related("categoria"), pk=pk)
    is_validator = request.user.has_perm("economia.can_validate_transactions")
    is_owner = tx.usuario_id == request.user.id

    if is_validator:
        FormClass = GastoForm
    else:
        if not (
            is_owner
            and tx.estado == "pendiente"
            and request.user.has_perm("economia.can_edit_own_transactions")
        ):
            return HttpResponseForbidden("No tenés permisos para editar esta transacción.")
        FormClass = GastoOwnEditForm

    if request.method == "POST":
        form = FormClass(request.POST, instance=tx, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Transacción actualizada.")
            return redirect("economia:transacciones" if is_validator else "perfil")
    else:
        form = FormClass(instance=tx, user=request.user)

    return render(request, "economia/editar_transaccion.html", {"form": form, "tx": tx})


@login_required
def cambiar_estado_transaccion(request, pk):
    """
    Cambio de estado individual (aprobado / pendiente / rechazado)
    — Solo para validadores.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Método inválido.")
    if not request.user.has_perm("economia.can_validate_transactions"):
        return HttpResponseForbidden("No tenés permisos para cambiar estados.")

    nuevo = request.POST.get("estado")
    if nuevo not in {"pendiente", "aprobado", "rechazado"}:
        return HttpResponseBadRequest("Estado inválido.")

    tx = get_object_or_404(Transaccion, pk=pk)

    if nuevo == "aprobado":
        cat_id = request.POST.get("categoria_id")
        try:
            categoria = Categoria.objects.get(pk=cat_id, activo=True)
        except (Categoria.DoesNotExist, ValueError, TypeError):
            messages.error(request, "Debes seleccionar una categoría para aprobar.")
            return redirect("economia:transacciones")

        tx.categoria = categoria
        tx.validado_por = request.user
        tx.validado_en = now()
        tx.estado = "aprobado"
        tx.save(update_fields=["categoria", "estado", "validado_por", "validado_en"])
        messages.success(request, "✅ Transacción aprobada y categorizada.")
        return redirect("economia:transacciones")

    # Rechazo o volver a pendiente
    tx.estado = nuevo
    tx.validado_por = request.user
    tx.validado_en = now()
    tx.save(update_fields=["estado", "validado_por", "validado_en"])
    messages.success(request, "Estado actualizado.")
    return redirect("economia:transacciones")


@login_required
def eliminar_transaccion(request, pk):
    """
    Eliminación:
    - Validador: puede borrar cualquier transacción.
    - Dueño: solo propias, en estado pendiente, y con permiso can_delete_own_transactions.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Método inválido.")

    tx = get_object_or_404(Transaccion, pk=pk)
    is_validator = request.user.has_perm("economia.can_validate_transactions")
    is_owner = tx.usuario_id == request.user.id

    if is_validator:
        tx.delete()
        messages.success(request, "🗑️ Transacción eliminada.")
        return redirect("economia:transacciones")

    if is_owner and tx.estado == "pendiente" and request.user.has_perm(
        "economia.can_delete_own_transactions"
    ):
        tx.delete()
        messages.success(request, "🗑️ Tu transacción pendiente fue eliminada.")
        return redirect("perfil")

    return HttpResponseForbidden("No tenés permisos para eliminar esta transacción.")


# ---------------------------------------------------------------------------
# Transacciones pendientes (bandeja para validador)
# ---------------------------------------------------------------------------

@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def transacciones_pendientes(request):
    """
    Bandeja de 'Transacciones pendientes' (solo validadores).
    Permite aprobar con categorización o rechazar con comentario (y notificación).
    """
    categorias_gasto = Categoria.objects.filter(activo=True, tipo="gasto").order_by("nombre")

    if request.method == "POST":
        tx_id = request.POST.get("tx_id")
        accion = request.POST.get("accion")  # 'aprobar' | 'rechazar'
        tx = get_object_or_404(Transaccion, pk=tx_id, estado="pendiente")

        if accion == "aprobar":
            cat_id = request.POST.get("categoria_id")
            try:
                categoria = Categoria.objects.get(pk=cat_id, activo=True, tipo="gasto")
            except (Categoria.DoesNotExist, ValueError, TypeError):
                messages.error(request, "Debés seleccionar una categoría para aprobar.")
                return redirect("economia:pendientes")

            tx.categoria = categoria
            tx.estado = "aprobado"
            tx.validado_por = request.user
            tx.validado_en = now()
            tx.save(update_fields=["categoria", "estado", "validado_por", "validado_en"])
            messages.success(request, "Transacción aprobada y categorizada.")

        elif accion == "rechazar":
            comentario = (request.POST.get("comentario") or "").strip()
            if not comentario:
                messages.error(request, "Debés indicar un comentario/motivo para rechazar.")
                return redirect("economia:pendientes")

            # Atómico: crear notificación y borrar transacción
            with transaction.atomic():
                if tx.usuario_id:
                    titulo = f"TU TRANSACCIÓN DE ${tx.monto:,.2f} FUE RECHAZADA"
                    cuerpo = (
                        f"Monto: ${tx.monto:,.2f}\n"
                        f"Fecha: {tx.fecha:%Y-%m-%d}\n"
                        f"Motivo: {comentario}"
                    )
                    notif = Notificacion.objects.create(
                        user=tx.usuario,
                        titulo=titulo,
                        cuerpo=cuerpo,
                        url="",  # se completa con su id
                    )
                    notif.url = reverse("notificaciones:detalle", args=[notif.id])
                    notif.save(update_fields=["url"])

                tx.delete()

            messages.warning(request, "Transacción rechazada y eliminada.")

        return redirect("economia:pendientes")

    pendientes = (
        Transaccion.objects.select_related("usuario", "categoria")
        .filter(estado="pendiente")
        .order_by("-fecha", "-id")
    )

    return render(
        request,
        "economia/pendientes.html",
        {"pendientes": pendientes, "categorias_gasto": categorias_gasto},
    )


# ---------------------------------------------------------------------------
# Planificación mensual
# ---------------------------------------------------------------------------
from django.db.models.functions import Cast
from django.db.models import CharField
from django.utils.timezone import now
from django.contrib import messages
from django.shortcuts import render, redirect

from .models import Categoria, PlanMensual

def planificar_mes(request):
    """
    Cargar/editar montos esperados por categoría para el mes/año.
    TODO se maneja como ENTEROS y se evita leer el DecimalField desde la BD.
    """
    hoy = now().date()

    def _safe_int(v, d):
        if v is None:
            return d
        s = "".join(ch for ch in str(v) if ch.isdigit())
        return int(s) if s else d

    year = _safe_int(request.GET.get("year"), hoy.year)
    month = _safe_int(request.GET.get("month"), hoy.month)

    cats_gasto = list(Categoria.objects.filter(activo=True, tipo="gasto").order_by("nombre"))
    cats_ing   = list(Categoria.objects.filter(activo=True, tipo="ingreso").order_by("nombre"))

    # ---------- helpers sólo enteros ----------
    def parse_int(raw) -> int:
        s = (raw or "").strip()
        s = (s.replace(" ", "")
               .replace("\u00a0", "")
               .replace(".", "")
               .replace(",", ""))
        return int(s) if s.isdigit() else 0

    # 1) NO leemos instancias de PlanMensual => evitamos converter Decimal de SQLite.
    #    Traemos sólo categoria_id y el monto casteado a texto, y lo parseamos a int.
    planes_rows = (
        PlanMensual.objects
        .filter(year=year, month=month)
        .annotate(me_txt=Cast("monto_esperado", output_field=CharField()))
        .values("categoria_id", "me_txt")
    )
    planes_map = {r["categoria_id"]: parse_int(r["me_txt"]) for r in planes_rows}

    # 2) Último plan histórico por categoría, también casteado a texto.
    def ultimo_plan_categoria(cat_id: int) -> int:
        v = (
            PlanMensual.objects
            .filter(categoria_id=cat_id)
            .order_by("-year", "-month")
            .annotate(me_txt=Cast("monto_esperado", output_field=CharField()))
            .values_list("me_txt", flat=True)
            .first()
        )
        return parse_int(v)

    if request.method == "POST":
        # IMPORTANTÍSIMO: no usamos get_or_create (trae instancia y dispara converter).
        for cat in cats_gasto + cats_ing:
            key = f"esperado_{cat.id}"
            val = parse_int(request.POST.get(key))

            qs = PlanMensual.objects.filter(year=year, month=month, categoria=cat)
            updated = qs.update(monto_esperado=val, actualizado_en=now())
            if not updated:
                PlanMensual.objects.create(
                    year=year,
                    month=month,
                    categoria=cat,
                    monto_esperado=val,
                    creado_por=request.user,
                )

        messages.success(request, "Plan mensual guardado.")
        return redirect("economia:resumen")

    # 3) Armamos items para el template (todo en int)
    def build_items(cats):
        items = []
        for c in cats:
            esperado = planes_map.get(c.id, ultimo_plan_categoria(c.id))
            items.append({"cat": c, "esperado": esperado})
        return items

    cats_gasto_plans = build_items(cats_gasto)
    cats_ing_plans   = build_items(cats_ing)

    return render(
        request,
        "economia/planificar_mes.html",
        {
            "year": year,
            "month": month,
            "cats_gasto_plans": cats_gasto_plans,
            "cats_ing_plans": cats_ing_plans,
        },
    )


# ---------------------------------------------------------------------------
# Resumen por categorías (Plan vs Real)
# ---------------------------------------------------------------------------

@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def resumen_categorias(request):
    """
    Resumen por categorías del MES seleccionado con comparación contra plan.
    Solo se muestran categorías con movimiento REAL (> 0).
    """
    hoy = now().date()
    year = _safe_int(request.GET.get("year"), hoy.year)
    month = _safe_int(request.GET.get("month"), hoy.month)

    qs_mes = Transaccion.objects.filter(
        estado="aprobado", fecha__year=year, fecha__month=month
    )

    dec_out = DecimalField(max_digits=12, decimal_places=2)
    gastos_real = (
        qs_mes.filter(categoria__tipo="gasto")
        .values("categoria__id", "categoria__nombre")
        .annotate(
            total=Coalesce(
                Sum(Cast("monto", output_field=dec_out)),
                Value(Decimal("0.00")),
                output_field=dec_out,
            )
        )
        .order_by("categoria__nombre")
    )
    ingresos_real = (
        qs_mes.filter(categoria__tipo="ingreso")
        .values("categoria__id", "categoria__nombre")
        .annotate(
            total=Coalesce(
                Sum(Cast("monto", output_field=dec_out)),
                Value(Decimal("0.00")),
                output_field=dec_out,
            )
        )
        .order_by("categoria__nombre")
    )

    # Plan del mes: casteo a texto y luego a Decimal en Python
    planes_qs = (
        PlanMensual.objects
        .filter(year=year, month=month)
        .select_related("categoria")
        .annotate(monto_txt=Cast("monto_esperado", output_field=CharField()))
        .values("categoria_id", "monto_txt")
    )
    planes = {p["categoria_id"]: _to_decimal(p["monto_txt"]) for p in planes_qs}

    def _mk_row(nombre: str, plan, real):
        plan = _to_decimal(plan)
        real = _to_decimal(real)
        if plan > 0:
            progress_pct = int((real / plan) * 100)
            is_over = real > plan
            over_amount = (real - plan) if is_over else Decimal("0")
        else:
            progress_pct = 0
            is_over = False
            over_amount = Decimal("0")
        return {
            "nombre": nombre,
            "plan": plan,
            "real": real,
            "progress_pct": progress_pct,
            "is_over": is_over,
            "over_amount": over_amount,
        }

    def _merge(lista_real):
        items = []
        for row in lista_real:
            real = _to_decimal(row["total"])
            if real <= 0:
                continue
            cat_id = row["categoria__id"]
            nombre = row["categoria__nombre"]
            plan = planes.get(cat_id, Decimal("0"))
            items.append(_mk_row(nombre, plan, real))
        items.sort(key=lambda x: x["nombre"].lower())
        return items

    gastos = _merge(gastos_real)
    ingresos = _merge(ingresos_real)

    return render(
        request,
        "economia/resumen_categorias.html",
        {
            "year": year,
            "month": month,
            "months": range(1, 13),
            "gastos": gastos,
            "ingresos": ingresos,
        },
    )


# ---------------------------------------------------------------------------
# Lista de transacciones (solo aprobadas)
# ---------------------------------------------------------------------------

@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def lista_transacciones(request):
    hoy = now().date()

    raw_year = request.GET.get("year")
    raw_month = request.GET.get("month")

    year = _safe_int(raw_year, hoy.year) if raw_year not in (None, "") else hoy.year
    month = _safe_int(raw_month, hoy.month) if raw_month not in (None, "") else hoy.month
    if not (1 <= int(month) <= 12):
        month = hoy.month

    q = request.GET.get("q")

    qs_base = (
        Transaccion.objects.select_related("categoria", "usuario")
        .filter(estado="aprobado", fecha__year=year, fecha__month=month)
    )

    if q:
        qs_base = qs_base.filter(
            Q(descripcion__icontains=q)
            | Q(categoria__nombre__icontains=q)
            | Q(usuario__username__icontains=q)
        )

    gastos_qs = qs_base.filter(categoria__tipo="gasto").order_by("-fecha", "-id")
    ingresos_qs = qs_base.filter(categoria__tipo="ingreso").order_by("-fecha", "-id")

    total_gastos = gastos_qs.aggregate(s=Sum("monto"))["s"] or 0
    total_ingresos = ingresos_qs.aggregate(s=Sum("monto"))["s"] or 0

    page_g = request.GET.get("page_g")
    page_i = request.GET.get("page_i")
    gastos_page = Paginator(gastos_qs, 25).get_page(page_g)
    ingresos_page = Paginator(ingresos_qs, 25).get_page(page_i)

    return render(
        request,
        "economia/transacciones.html",
        {
            "year": year,
            "month": month,
            "months": range(1, 13),
            "gastos": gastos_page,
            "ingresos": ingresos_page,
            "total_gastos": total_gastos,
            "total_ingresos": total_ingresos,
            "q_f": q or "",
        },
    )


# ---------------------------------------------------------------------------
# Cierre de caja
# ---------------------------------------------------------------------------
@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def cierre_caja(request):
    hoy = now().date()

    raw_year = request.GET.get("year")
    raw_month = request.GET.get("month")

    # 👉 en vez de mostrar mensajes, marcamos este hint para el template
    show_hint = False
    if raw_year in (None, "") or raw_month in (None, ""):
        year, month = hoy.year, hoy.month
        show_hint = True
    else:
        year = _safe_int(raw_year, hoy.year)
        month = _safe_int(raw_month, hoy.month)
        if not (1 <= month <= 12):
            month = hoy.month
            show_hint = True

    qs_mes = Transaccion.objects.filter(estado="aprobado", fecha__year=year, fecha__month=month)
    total_ingresos = qs_mes.filter(categoria__tipo="ingreso").aggregate(s=Sum("monto"))["s"] or 0
    total_gastos   = qs_mes.filter(categoria__tipo="gasto").aggregate(s=Sum("monto"))["s"] or 0
    saldo = total_ingresos - total_gastos

    # ===== HORAS: por persona y proyecto =====
    from calendar import monthrange
    from collections import defaultdict
    from datetime import date

    first_day = date(year, month, 1)
    last_day  = date(year, month, monthrange(year, month)[1])

    try:
        desde = date.fromisoformat(request.GET.get("desde")) if request.GET.get("desde") else first_day
    except ValueError:
        desde = first_day
    try:
        hasta = date.fromisoformat(request.GET.get("hasta")) if request.GET.get("hasta") else last_day
    except ValueError:
        hasta = last_day

    estado = (request.GET.get("estado") or "todas").lower()
    horas_base = HoraTrabajo.objects.select_related("usuario", "proyecto").filter(fecha__range=(desde, hasta))
    if estado in {"cargada", "aprobada", "rechazada"}:
        horas_base = horas_base.filter(estado=estado)

    horas_qs = (
        horas_base
        .values(
            "usuario_id",
            "usuario__first_name",
            "usuario__last_name",
            "usuario__username",
            "proyecto_id",
            "proyecto__nombre",
        )
        .annotate(total_horas=Sum("horas"))
        .order_by("usuario__first_name", "usuario__last_name", "proyecto__nombre")
    )

    horas_por_persona = []
    bucket = defaultdict(list)
    totales_persona = defaultdict(float)

    for row in horas_qs:
        persona = f"{row['usuario__first_name']} {row['usuario__last_name']}".strip() or row["usuario__username"]
        clave = (row["usuario_id"], persona, row["usuario__username"])
        bucket[clave].append({
            "proyecto_id": row["proyecto_id"],
            "proyecto": row["proyecto__nombre"] or "—",
            "horas": float(row["total_horas"] or 0.0),
        })
        totales_persona[clave] += float(row["total_horas"] or 0.0)

    for (uid, nombre, username), proyectos in bucket.items():
        horas_por_persona.append({
            "persona_id": uid,
            "persona": nombre,
            "username": username,
            "proyectos": proyectos,
            "total_persona": round(totales_persona[(uid, nombre, username)], 2),
        })

    total_horas_general = round(sum(p["total_persona"] for p in horas_por_persona), 2)

    ctx = {
        "year": year,
        "month": month,
        "months": range(1, 13),
        "total_ingresos": total_ingresos,
        "total_gastos": total_gastos,
        "saldo": saldo,
        "desde": desde,
        "hasta": hasta,
        "estado": estado,
        "horas_por_persona": horas_por_persona,
        "total_horas_general": total_horas_general,
        "show_hint": show_hint,  # 👈 para mostrar la aclaración en el template
    }
    return render(request, "economia/cierre_caja.html", ctx)


# ---------------------------------------------------------------------------
# Categorías: alta/baja rápida
# ---------------------------------------------------------------------------

@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def categoria_nueva(request, tipo: str):
    """Alta rápida de categoría (gasto/ingreso) desde Planificar mes."""
    tipo = (tipo or "").lower()
    if tipo not in {"gasto", "ingreso"}:
        messages.error(request, "Tipo de categoría inválido.")
        return redirect("economia:planificar_mes")

    hoy = now().date()
    year = request.GET.get("year") or hoy.year
    month = request.GET.get("month") or hoy.month

    if request.method == "POST":
        form = CategoriaQuickForm(request.POST, tipo=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Categoría de {tipo} creada.")
            url = f"{reverse('economia:planificar_mes')}?year={year}&month={month}"
            return redirect(url)
    else:
        form = CategoriaQuickForm(tipo=tipo)

    return render(
        request,
        "economia/categoria_nueva.html",
        {"form": form, "tipo": tipo, "year": year, "month": month},
    )


@login_required
@permission_required("economia.can_validate_transactions", raise_exception=True)
def categoria_eliminar(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Método inválido.")

    cat = get_object_or_404(Categoria, pk=pk)
    # Soft delete
    if not cat.activo:
        messages.info(request, "La categoría ya estaba desactivada.")
    else:
        cat.activo = False
        cat.save(update_fields=["activo"])
        messages.success(request, f"Categoría '{cat.nombre}' eliminada.")

    year = request.GET.get("year")
    month = request.GET.get("month")
    if year and month:
        return redirect(f"{reverse('economia:planificar_mes')}?year={year}&month={month}")
    return redirect("economia:planificar_mes")
