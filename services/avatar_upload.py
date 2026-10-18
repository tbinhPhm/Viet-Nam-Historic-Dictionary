from __future__ import annotations

import os
from pathlib import Path

import requests

from config import avatar_upload_endpoint


def upload_avatar_via_endpoint(user_id: str, username: str, file_path: str | os.PathLike) -> str:
    endpoint = avatar_upload_endpoint()
    if not endpoint:
        raise ValueError("Thiếu AVATAR_UPLOAD_ENDPOINT.")

    with open(Path(file_path), "rb") as f:
        resp = requests.post(
            endpoint,
            data={"user_id": (user_id or "").strip(), "username": (username or "").strip()},
            files={"file": f},
            timeout=30,
        )
    resp.raise_for_status()
    data = resp.json() if resp.content else {}
    url = str((data or {}).get("avatar_url", "") or "").strip()
    if not url:
        raise ValueError("Response thiếu avatar_url.")
    return url
