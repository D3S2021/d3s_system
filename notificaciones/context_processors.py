from .models import Notificacion

def notificaciones_ctx(request):
    if not request.user.is_authenticated:
        return {}
    qs = (Notificacion.objects
          .filter(user=request.user, leida=False)
          .order_by("-creada"))
    return {
        "noti_count": qs.count(),
        "noti_unread": list(qs[:10]),  # top 10
    }
