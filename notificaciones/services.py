import json
import requests
from django.conf import settings
from django.utils import timezone
from .models import WhatsAppConfig, WhatsAppTemplate, WhatsAppMessageLog

def _get_graph_version():
    return getattr(settings, "WHATSAPP_GRAPH_VERSION", "v20.0")

def send_whatsapp_template(to_e164: str, template_name: str, language: str = "es", components=None):
    """
    Envía una plantilla de WhatsApp (Cloud API) y deja traza en WhatsAppMessageLog.
    - to_e164: número destino en formato E.164 (+549...)
    - template_name: nombre EXACTO de la plantilla aprobada en Meta
    - language: ej. 'es' o 'es_AR'
    - components: lista de componentes de la plantilla (header/body/buttons), opcional
    Devuelve (ok: bool, resp_json: dict, log: WhatsAppMessageLog)
    """
    cfg = WhatsAppConfig.objects.filter(enabled=True).first()
    if not cfg or not cfg.phone_number_id or not cfg.token:
        log = WhatsAppMessageLog.objects.create(
            to=to_e164, status="failed", error="Config WhatsApp inválida/incompleta"
        )
        return False, {"error": "missing_config"}, log

    # Buscar plantilla registrada (opcional)
    tpl = WhatsAppTemplate.objects.filter(name=template_name, active=True).first()

    url = f"https://graph.facebook.com/{_get_graph_version()}/{cfg.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {cfg.token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }
    if components:
        payload["template"]["components"] = components

    log = WhatsAppMessageLog.objects.create(
        to=to_e164,
        template=tpl,
        payload=payload,
        status="created",
    )

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
        data = r.json() if r.content else {}
        ok = r.ok and "messages" in data

        log.response = data
        if ok:
            log.status = "sent"
            try:
                mid = data["messages"][0]["id"]
                log.provider_message_id = mid
            except Exception:
                pass
        else:
            log.status = "failed"
            log.error = f"HTTP {r.status_code}: {data}"
        log.last_update = timezone.now()
        log.save(update_fields=["response", "status", "provider_message_id", "last_update", "error"])
        return ok, data, log

    except Exception as e:
        log.status = "failed"
        log.error = str(e)
        log.last_update = timezone.now()
        log.save(update_fields=["status", "error", "last_update"])
        return False, {"error": str(e)}, log
