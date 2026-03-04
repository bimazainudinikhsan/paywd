import asyncio
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from storage_backend import read_json_file
from telegram_bot import create_application_for_user

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


async def _build_initialized_application():
    user_config = _resolve_webhook_user_config()
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

    async def _process():
        update = Update.de_json(payload, app.bot)
        if update is None:
            return
        await app.process_update(update)

    _run(_process())
    return {"username": user_config.get("username")}


def set_webhook(webhook_url):
    app, _ = _ensure_application()
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip() or None

    async def _set():
        ok = await app.bot.set_webhook(url=webhook_url, secret_token=secret)
        info = await app.bot.get_webhook_info()
        return ok, info

    ok, info = _run(_set())
    return {"ok": bool(ok), "webhook": _webhook_info_to_dict(info)}


def delete_webhook(drop_pending_updates=False):
    app, _ = _ensure_application()

    async def _delete():
        ok = await app.bot.delete_webhook(drop_pending_updates=drop_pending_updates)
        info = await app.bot.get_webhook_info()
        return ok, info

    ok, info = _run(_delete())
    return {"ok": bool(ok), "webhook": _webhook_info_to_dict(info)}


def get_webhook_info():
    app, user_config = _ensure_application()

    async def _info():
        info = await app.bot.get_webhook_info()
        me = await app.bot.get_me()
        return info, me

    info, me = _run(_info())
    return {
        "username": user_config.get("username"),
        "bot_username": getattr(me, "username", None),
        "bot_id": getattr(me, "id", None),
        "webhook": _webhook_info_to_dict(info),
    }
