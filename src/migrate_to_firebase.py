import json
import sys
from pathlib import Path

# Load .env before importing storage backend (it initializes at import-time).
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

from storage_backend import PROJECT_ROOT, json_storage


def discover_local_json_files():
    files = []

    creds_path = PROJECT_ROOT / "config" / "credentials.json"
    if creds_path.exists():
        files.append(creds_path)

    data_dir = PROJECT_ROOT / "data"
    if data_dir.exists():
        files.extend(sorted(data_dir.glob("*.json")))

    return files


def to_relative_path(path_obj):
    return str(path_obj.relative_to(PROJECT_ROOT)).replace("\\", "/")


def main():
    if not json_storage.is_remote_enabled():
        print("[!] Firebase backend is not enabled.")
        print("[i] Set FIREBASE_DATABASE_URL and FIREBASE service-account env vars first.")
        return 1

    files = discover_local_json_files()
    if not files:
        print("[i] No local JSON files found in config/credentials.json or data/*.json")
        return 0

    uploaded = 0
    failed = 0

    for file_path in files:
        rel_path = to_relative_path(file_path)
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            if json_storage.write_json(rel_path, payload):
                print(f"[+] Uploaded: {rel_path} -> {json_storage.db_path_for(rel_path)}")
                uploaded += 1
            else:
                print(f"[!] Failed upload: {rel_path}")
                failed += 1
        except Exception as e:
            print(f"[!] Failed read/upload {rel_path}: {e}")
            failed += 1

    print(f"[*] Migration finished. Uploaded={uploaded}, Failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
