import asyncio
import json
import os
import threading
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from storage_backend import read_json_file

_RUNNER = asyncio.Runner()
_RUN_LOCK = threading.Lock()
_APP_LOCK = threading.Lock()
_APP = None
_APP_USER = None


def _run(coro):
    with _RUN_LOCK:
        return _RUNNER.run(coro)


def _load_users():
    creds_data = read_json_file("config/credentials.json", default={})
    if isinstance(creds_data, dict):
        users = creds_data.get("users", [])
        return users if isinstance(users, list) else []
    if isinstance(creds_data, list):
        return creds_data
    return []


def _resolve_webhook_user_config():
    users = _load_users()
    preferred_username = os.getenv("WDBOT_DEFAULT_USERNAME", "").strip()

    target_user = None
    if preferred_username:
        for user in users:
            if user.get("username") == preferred_username:
                target_user = user
                break

    if not target_user:
        for user in users:
            if user.get("telegram_bot_token") and user.get("telegram_admin_id"):
                target_user = user
                break

    if not target_user and users:
        target_user = users[0]

    if not target_user:
        target_user = {
            "username": preferred_username or "default",
            "password": "",
            "telegram_bot_token": "",
            "telegram_admin_id": "",
        }

    user_config = target_user.copy()

    env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    env_owner = os.getenv("OWNER_ID", "").strip()
    if env_token:
        user_config["telegram_bot_token"] = env_token
    if env_owner:
        user_config["telegram_admin_id"] = env_owner

    if not user_config.get("username"):
        user_config["username"] = preferred_username or "default"

    if not user_config.get("telegram_bot_token"):
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN for webhook mode.")
    if not user_config.get("telegram_admin_id"):
        raise RuntimeError("Missing OWNER_ID/telegram_admin_id for webhook mode.")

    return user_config


def _resolve_bot_token_for_api():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token

    users = _load_users()
    preferred_username = os.getenv("WDBOT_DEFAULT_USERNAME", "").strip()

    if preferred_username:
        for user in users:
            if user.get("username") == preferred_username:
                preferred_token = (user.get("telegram_bot_token") or "").strip()
                if preferred_token:
                    return preferred_token

    for user in users:
        candidate = (user.get("telegram_bot_token") or "").strip()
        if candidate:
            return candidate

    return ""


def _resolve_username_hint():
    preferred_username = os.getenv("WDBOT_DEFAULT_USERNAME", "").strip()
    if preferred_username:
        return preferred_username

    users = _load_users()
    for user in users:
        username = (user.get("username") or "").strip()
        if username:
            return username

    return "default"


def _telegram_api_call(method, payload=None):
    token = _resolve_bot_token_for_api()
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN for webhook mode.")

    url = f"https://api.telegram.org/bot{token}/{method}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )

    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib_error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
            parsed = json.loads(raw)
            raise RuntimeError(parsed.get("description") or f"HTTP {e.code}") from e
        except Exception:
            raise RuntimeError(f"Telegram API HTTP Error: {e.code}") from e
    except Exception as e:
        raise RuntimeError(f"Telegram API request failed: {e}") from e

    try:
        parsed = json.loads(raw)
    except Exception as e:
        raise RuntimeError("Telegram API returned invalid JSON.") from e

    if not parsed.get("ok"):
        raise RuntimeError(parsed.get("description") or f"Telegram API method '{method}' failed.")

    return parsed.get("result")


async def _build_initialized_application():
    user_config = _resolve_webhook_user_config()
    from telegram_bot import create_application_for_user

    app = create_application_for_user(
        user_config,
        ensure_login_on_start=False,
        enable_background_tasks=False,
    )
    if not app:
        raise RuntimeError("Failed to create telegram application for webhook.")

    # For webhook/serverless processing, initialize is enough.
    # We do not start polling/updater here.
    await app.initialize()
    return app, user_config


def _ensure_application():
    global _APP, _APP_USER
    if _APP is not None:
        return _APP, _APP_USER

    with _APP_LOCK:
        if _APP is None:
            _APP, _APP_USER = _run(_build_initialized_application())
    return _APP, _APP_USER


def _webhook_info_to_dict(info):
    if not info:
        return {}

    if isinstance(info, dict):
        return {
            "url": info.get("url", ""),
            "pending_update_count": info.get("pending_update_count", 0),
            "has_custom_certificate": info.get("has_custom_certificate", False),
            "last_error_date": info.get("last_error_date", None),
            "last_error_message": info.get("last_error_message", None),
            "max_connections": info.get("max_connections", None),
            "ip_address": info.get("ip_address", None),
        }

    return {
        "url": getattr(info, "url", ""),
        "pending_update_count": getattr(info, "pending_update_count", 0),
        "has_custom_certificate": getattr(info, "has_custom_certificate", False),
        "last_error_date": getattr(info, "last_error_date", None),
        "last_error_message": getattr(info, "last_error_message", None),
        "max_connections": getattr(info, "max_connections", None),
        "ip_address": getattr(info, "ip_address", None),
    }


def process_update_payload(payload):
    app, user_config = _ensure_application()
    from telegram import Update

    async def _process():
        update = Update.de_json(payload, app.bot)
        if update is None:
            return
        await app.process_update(update)

    _run(_process())
    return {"username": user_config.get("username")}


def set_webhook(webhook_url):
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip() or None
    payload = {"url": webhook_url}
    if secret:
        payload["secret_token"] = secret

    ok = _telegram_api_call("setWebhook", payload=payload)
    info = _telegram_api_call("getWebhookInfo")
    return {"ok": bool(ok), "webhook": _webhook_info_to_dict(info)}


def delete_webhook(drop_pending_updates=False):
    ok = _telegram_api_call(
        "deleteWebhook",
        payload={"drop_pending_updates": bool(drop_pending_updates)},
    )
    info = _telegram_api_call("getWebhookInfo")
    return {"ok": bool(ok), "webhook": _webhook_info_to_dict(info)}


def get_webhook_info():
    username_hint = _resolve_username_hint()
    info = _telegram_api_call("getWebhookInfo")
    me = _telegram_api_call("getMe")
    return {
        "username": username_hint,
        "bot_username": me.get("username") if isinstance(me, dict) else None,
        "bot_id": me.get("id") if isinstance(me, dict) else None,
        "webhook": _webhook_info_to_dict(info),
    }
