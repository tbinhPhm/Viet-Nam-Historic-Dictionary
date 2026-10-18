from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path

from config import HISTORY_DATA_JSON_PATH, PROJECT_ROOT


_WS_RE = re.compile(r"\s+")


class HistoryData:
    def __init__(self, json_path: str | os.PathLike = HISTORY_DATA_JSON_PATH):
        base_dir = PROJECT_ROOT
        self.json_path = (base_dir / Path(json_path)).resolve()

        self.dataset: dict = self._load_json()
        self.su_kien: list[dict] = list(self.dataset.get("su_kien", []) or [])

        # Pre-compute fields used for searching to avoid repeatedly normalizing
        # every event text on each query.
        for event in self.su_kien:
            event["_tieu_de_norm"] = self._normalize_text(str(event.get("tieu_de", "")))
            event["_mo_ta_norm"] = self._normalize_text(str(event.get("mo_ta", "")))
            event["_nam_bat_dau_int"] = self._as_int(event.get("nam_bat_dau"))
            event["_nam_ket_thuc_int"] = self._as_int(event.get("nam_ket_thuc"))

        self._search_cache: OrderedDict[str, list[dict]] = OrderedDict()
        self._search_cache_max = 128

    def _load_json(self) -> dict:
        try:
            return json.loads(self.json_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(f"Không tìm thấy file JSON: {self.json_path}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"File JSON lỗi định dạng: {self.json_path}") from exc

    @staticmethod
    def _normalize_text(value: str) -> str:
        text = _WS_RE.sub(" ", (value or "").strip()).lower()
        text = text.replace("đ", "d").replace("Đ", "d")
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return text

    @staticmethod
    def _as_int(value) -> int | None:
        try:
            return int(str(value).strip())
        except Exception:
            return None

    def search_by_year(self, year: int) -> list[dict]:
        results: list[dict] = []
        for event in self.su_kien:
            start = event.get("_nam_bat_dau_int")
            end = event.get("_nam_ket_thuc_int")
            if start is None and end is None:
                continue
            if end is None:
                end = start
            if start is None:
                start = end
            if start <= year <= end:
                results.append(event)
        return results

    def search_by_keyword(self, keyword: str) -> list[dict]:
        key = self._normalize_text(keyword)
        if not key:
            return []
        results: list[dict] = []
        for event in self.su_kien:
            title = str(event.get("_tieu_de_norm", ""))
            desc = str(event.get("_mo_ta_norm", ""))
            if key in title or key in desc:
                results.append(event)
        return results

    def search(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []

        cache_key = self._normalize_text(q)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            self._search_cache.move_to_end(cache_key)
            return cached

        year = self._as_int(q)
        if year is not None:
            results = self.search_by_year(year)
        else:
            results = self.search_by_keyword(q)

        self._search_cache[cache_key] = results
        self._search_cache.move_to_end(cache_key)
        if len(self._search_cache) > self._search_cache_max:
            self._search_cache.popitem(last=False)
        return results

    @staticmethod
    def format_events(events: list[dict]) -> str:
        if not events:
            return "Không tìm thấy sự kiện phù hợp."

        parts: list[str] = []
        for event in events:
            title = str(event.get("tieu_de", "")).strip()
            desc = str(event.get("mo_ta", "")).strip()
            start = event.get("nam_bat_dau")
            end = event.get("nam_ket_thuc")

            start_int = HistoryData._as_int(start)
            if start_int is not None:
                start = f"{abs(start_int)} TCN" if start_int < 0 else str(start_int)
            end_int = HistoryData._as_int(end)
            if end_int is not None:
                end = f"{abs(end_int)} TCN" if end_int < 0 else str(end_int)

            if start is not None and end is not None and str(start).strip() == str(end).strip():
                end = None

            year_part = ""
            if start is not None and end is not None:
                year_part = f" ({start}–{end})"
            elif start is not None:
                year_part = f" ({start})"
            elif end is not None:
                year_part = f" ({end})"

            header = (title or "Sự kiện") + year_part
            parts.append(f"{header}\n{desc}".strip())

        return "\n\n---\n\n".join(parts)
