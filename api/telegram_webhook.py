import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from vercel_webhook_runtime import (
    delete_webhook,
    get_webhook_info,
    process_update_payload,
    set_webhook,
)


def _build_base_url(headers):
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
    if public_base_url:
        return public_base_url.rstrip("/")

    host = headers.get("x-forwarded-host") or headers.get("host")
    proto = headers.get("x-forwarded-proto", "https")
    if host:
        return f"{proto}://{host}"
    return ""


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        if secret:
            incoming_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if incoming_secret != secret:
                self._send_json(403, {"ok": False, "error": "Invalid webhook secret token."})
                return

        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            length = 0

        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "Invalid JSON payload."})
            return

        try:
            result = process_update_payload(payload)
            self._send_json(200, {"ok": True, "result": result})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query or "")
        action = (query.get("action", [""])[0] or "").strip().lower()

        try:
            if action == "set":
                explicit_url = (query.get("url", [""])[0] or "").strip()
                if explicit_url:
                    webhook_url = explicit_url
                else:
                    base_url = _build_base_url(self.headers)
                    if not base_url:
                        self._send_json(400, {"ok": False, "error": "Cannot determine base URL."})
                        return
                    webhook_url = f"{base_url}/api/telegram-webhook"

                result = set_webhook(webhook_url)
                self._send_json(200, {"ok": True, "action": "set", "webhook_url": webhook_url, "result": result})
                return

            if action == "delete":
                drop_pending = (query.get("drop_pending", ["false"])[0] or "").lower() in ("1", "true", "yes")
                result = delete_webhook(drop_pending_updates=drop_pending)
                self._send_json(200, {"ok": True, "action": "delete", "result": result})
                return

            if action == "info":
                result = get_webhook_info()
                self._send_json(200, {"ok": True, "action": "info", "result": result})
                return

            self._send_json(
                200,
                {
                    "ok": True,
                    "message": "Telegram webhook endpoint is ready.",
                    "usage": {
                        "POST": "/api/telegram-webhook (Telegram updates)",
                        "GET": [
                            "/api/telegram-webhook?action=info",
                            "/api/telegram-webhook?action=set",
                            "/api/telegram-webhook?action=delete",
                        ],
                    },
                },
            )
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

