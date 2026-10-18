from __future__ import annotations

import os
from pathlib import Path

import requests

from config import imgbb_api_key, imgbb_endpoint


def upload_file_to_imgbb(file_path: str | os.PathLike, *, api_key: str | None = None) -> str:
    api_key = (api_key or "").strip() or imgbb_api_key()
    if not api_key:
        raise ValueError("Thiếu IMGBB_API_KEY (hoặc data/imgbb_api_key.txt).")

    endpoint = imgbb_endpoint()
    with open(Path(file_path), "rb") as f:
        resp = requests.post(endpoint, params={"key": api_key}, files={"image": f}, timeout=60)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    data = payload.get("data") or {}
    url = str(data.get("url") or data.get("display_url") or "").strip()
    if not url:
        raise ValueError("ImgBB response thiếu url.")
    return url
