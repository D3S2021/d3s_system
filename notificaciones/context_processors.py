from django.core.cache import cache

from .models import Notificacion

_CACHE_TTL = 60  # segundos


def notificaciones_ctx(request):
    if not request.user.is_authenticated:
        return {}

    cache_key = f"noti_ctx_{request.user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    qs = (Notificacion.objects
          .filter(user=request.user, leida=False)
          .order_by("-creada"))
    result = {
        "noti_count": qs.count(),
        "noti_unread": list(qs[:10]),
    }
    cache.set(cache_key, result, _CACHE_TTL)
    return result
