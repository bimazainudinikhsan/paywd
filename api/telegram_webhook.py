import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from vercel_webhook_runtime import (
    process_update_payload,
)


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
        try:
            self._send_json(
                200,
                {
                    "ok": True,
                    "message": "Telegram webhook endpoint is ready.",
                },
            )
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
