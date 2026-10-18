from __future__ import annotations

import os
import sys
import json
from pathlib import Path


def _resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


PROJECT_ROOT = _resource_root()
UI_DIR = PROJECT_ROOT / "ui"
DATA_DIR = PROJECT_ROOT / "data"

USER_DB_PATH = DATA_DIR / "user.json"
HISTORY_DATA_JSON_PATH = DATA_DIR / "dataLichSuThanhBinh.json"

FIREBASE_SERVICE_ACCOUNT_PATH = PROJECT_ROOT / "tudienlichsuvietnam-firebase-adminsdk-fbsvc-da94ea01c6.json"


def use_firebase() -> bool:
    raw = os.getenv("USE_FIREBASE")
    if raw is None:
        return True
    return raw.strip() == "1"


def auto_sync_user_json_to_firebase() -> bool:
    return os.getenv("AUTO_SYNC_USER_JSON_TO_FIREBASE", "0").strip() == "1"


def avatar_upload_endpoint() -> str:
    return os.getenv("AVATAR_UPLOAD_ENDPOINT", "").strip()


def imgbb_api_key() -> str:
    key = os.getenv("IMGBB_API_KEY", "").strip()
    if key:
        return key

    # Fallback: đọc từ file local để khỏi cần set env
    txt_path = DATA_DIR / "imgbb_api_key.txt"
    if txt_path.exists():
        try:
            return txt_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # Fallback: đọc từ JSON (nếu có)
    json_path = DATA_DIR / "secrets.json"
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            return str((payload or {}).get("imgbb_api_key", "") or "").strip()
        except Exception:
            pass

    return ""


def imgbb_endpoint() -> str:
    return os.getenv("IMGBB_ENDPOINT", "https://api.imgbb.com/1/upload").strip()
