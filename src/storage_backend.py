import base64
import json
import os
import re
from pathlib import Path

try:
    import firebase_admin
    from firebase_admin import credentials, db
except Exception:
    firebase_admin = None
    credentials = None
    db = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class JsonStorageBackend:
    """
    JSON storage backend with Firebase Realtime Database primary storage
    and local-file fallback.
    """

    def __init__(self):
        self.mode = os.getenv("WDBOT_STORAGE_MODE", "firebase").strip().lower()
        self.firebase_root = os.getenv("FIREBASE_RTDB_ROOT", "wdbot").strip("/") or "wdbot"
        self._remote_enabled = False
        self._init_error = None
        self._warned_fallback = False
        self._init_firebase()

    def _init_firebase(self):
        if self.mode not in ("firebase", "auto"):
            return

        if firebase_admin is None:
            self._init_error = "firebase-admin package not installed."
            return

        db_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()
        if not db_url:
            self._init_error = "FIREBASE_DATABASE_URL is not set."
            return

        service_account = self._load_service_account_json()
        if not service_account:
            self._init_error = (
                "Firebase credentials not found. "
                "Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_B64 or FIREBASE_SERVICE_ACCOUNT_PATH."
            )
            return

        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account)
                firebase_admin.initialize_app(cred, {"databaseURL": db_url})
            self._remote_enabled = True
            self._init_error = None
        except Exception as e:
            self._init_error = f"Failed to initialize Firebase: {e}"

    def _load_service_account_json(self):
        raw_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        if raw_json:
            try:
                return json.loads(raw_json)
            except Exception:
                return None

        raw_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "").strip()
        if raw_b64:
            try:
                decoded = base64.b64decode(raw_b64).decode("utf-8")
                return json.loads(decoded)
            except Exception:
                return None

        cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
        if cred_path:
            p = Path(cred_path)
            if not p.is_absolute():
                p = PROJECT_ROOT / cred_path
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    return None
        return None

    def _warn_fallback_once(self):
        if not self._warned_fallback and self.mode in ("firebase", "auto") and self._init_error:
            print(f"[!] Firebase storage disabled: {self._init_error} Falling back to local JSON files.")
            self._warned_fallback = True

    def _encode_key(self, key):
        key = str(key)
        return (
            key.replace("__DOT__", "__ESC_DOT__")
            .replace("__HASH__", "__ESC_HASH__")
            .replace("__DOLLAR__", "__ESC_DOLLAR__")
            .replace("__LBRACK__", "__ESC_LBRACK__")
            .replace("__RBRACK__", "__ESC_RBRACK__")
            .replace("__SLASH__", "__ESC_SLASH__")
            .replace(".", "__DOT__")
            .replace("#", "__HASH__")
            .replace("$", "__DOLLAR__")
            .replace("[", "__LBRACK__")
            .replace("]", "__RBRACK__")
            .replace("/", "__SLASH__")
        )

    def _decode_key(self, key):
        key = str(key)
        return (
            key.replace("__SLASH__", "/")
            .replace("__RBRACK__", "]")
            .replace("__LBRACK__", "[")
            .replace("__DOLLAR__", "$")
            .replace("__HASH__", "#")
            .replace("__DOT__", ".")
            .replace("__ESC_SLASH__", "__SLASH__")
            .replace("__ESC_RBRACK__", "__RBRACK__")
            .replace("__ESC_LBRACK__", "__LBRACK__")
            .replace("__ESC_DOLLAR__", "__DOLLAR__")
            .replace("__ESC_HASH__", "__HASH__")
            .replace("__ESC_DOT__", "__DOT__")
        )

    def _encode_for_firebase(self, value):
        if isinstance(value, dict):
            return {self._encode_key(k): self._encode_for_firebase(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._encode_for_firebase(v) for v in value]
        return value

    def _decode_from_firebase(self, value):
        if isinstance(value, dict):
            return {self._decode_key(k): self._decode_from_firebase(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._decode_from_firebase(v) for v in value]
        return value

    def _local_path(self, rel_path):
        return PROJECT_ROOT / rel_path.replace("\\", "/")

    def _sanitize_segment(self, segment):
        # Firebase RTDB keys cannot contain . # $ [ ]
        return re.sub(r"[.#$\[\]]", "_", segment)

    def db_path_for(self, rel_path):
        normalized = rel_path.replace("\\", "/").strip("/")
        if normalized.endswith(".json"):
            normalized = normalized[:-5]
        segments = [self._sanitize_segment(s) for s in normalized.split("/") if s]
        if segments:
            return f"{self.firebase_root}/" + "/".join(segments)
        return self.firebase_root

    def is_remote_enabled(self):
        return self._remote_enabled

    def read_json(self, rel_path, default=None):
        if self._remote_enabled:
            try:
                value = db.reference(self.db_path_for(rel_path)).get()
                if value is None:
                    return default
                return self._decode_from_firebase(value)
            except Exception as e:
                print(f"[!] Firebase read failed for {rel_path}: {e}")

        self._warn_fallback_once()
        local_path = self._local_path(rel_path)
        if not local_path.exists():
            return default
        try:
            return json.loads(local_path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, rel_path, data):
        if self._remote_enabled:
            try:
                payload = self._encode_for_firebase(data)
                db.reference(self.db_path_for(rel_path)).set(payload)
                return True
            except Exception as e:
                print(f"[!] Firebase write failed for {rel_path}: {e}")

        self._warn_fallback_once()
        local_path = self._local_path(rel_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            local_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            print(f"[!] Local JSON write failed for {rel_path}: {e}")
            return False

    def exists(self, rel_path):
        if self._remote_enabled:
            try:
                return db.reference(self.db_path_for(rel_path)).get() is not None
            except Exception:
                pass
        self._warn_fallback_once()
        return self._local_path(rel_path).exists()


json_storage = JsonStorageBackend()


def read_json_file(rel_path, default=None):
    return json_storage.read_json(rel_path, default=default)


def write_json_file(rel_path, data):
    return json_storage.write_json(rel_path, data)


def json_exists(rel_path):
    return json_storage.exists(rel_path)
