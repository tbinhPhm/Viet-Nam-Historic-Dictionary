from __future__ import annotations

import json
import threading
from difflib import SequenceMatcher
from pathlib import Path


class UserStore:
    def __init__(self, path: Path, mirror_password_func=None):
        self.path = path
        self._mirror_password_func = mirror_password_func

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"users": []})

    def _read(self) -> dict:
        self._ensure_file()
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"users": []}

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_users(self) -> list[dict]:
        payload = self._read()
        users = payload.get("users", [])
        return list(users) if isinstance(users, list) else []

    def get_user(self, username: str) -> dict | None:
        u = (username or "").strip()
        if not u:
            return None
        for item in self.list_users():
            if str(item.get("username", "")).strip() == u:
                return dict(item)
        return None

    def _public_user(self, user: dict) -> dict:
        return {
            "ID": str(user.get("ID", "") or ""),
            "username": str(user.get("username", "") or ""),
            "avatar_url": str(user.get("avatar_url", "") or ""),
        }

    def get_public_user_by_id(self, user_id: str) -> dict | None:
        uid = (user_id or "").strip()
        if not uid:
            return None
        for item in self.list_users():
            if str(item.get("ID", "") or "").strip() == uid:
                return self._public_user(item)
        return None

    def search_public_users(self, query: str, limit: int = 20) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        q_fold = q.casefold()
        matches: list[tuple[float, dict]] = []
        for item in self.list_users():
            username = str(item.get("username", "") or "")
            user_id = str(item.get("ID", "") or "")
            username_fold = username.casefold()
            user_id_fold = user_id.casefold()
            score = 0.0
            if username_fold == q_fold or user_id_fold == q_fold:
                score = 90.0
            elif username_fold.startswith(q_fold):
                score = 80.0
            elif q_fold in username_fold or q_fold in user_id_fold:
                score = 70.0
            else:
                score = SequenceMatcher(None, q_fold, username_fold).ratio() * 60.0
            if score >= 35.0:
                matches.append((score, self._public_user(item)))
        matches.sort(key=lambda pair: (-pair[0], pair[1].get("username", "").casefold()))
        return [item for _score, item in matches[:limit]]

    def user_exists(self, username: str) -> bool:
        return self.get_user(username) is not None

    def _next_id(self) -> str:
        users = self.list_users()
        max_id = 0
        for item in users:
            raw = str(item.get("ID", "")).strip()
            try:
                n = int(raw)
            except Exception:
                n = 0
            if n > max_id:
                max_id = n
        if max_id == 0 and users:
            max_id = len(users)
        return f"{max_id + 1:06d}"

    def add_user(self, username: str, password: str, email: str) -> None:
        u = (username or "").strip()
        p = (password or "").strip()
        e = (email or "").strip()
        if not u or not p or not e:
            raise ValueError("Username, mật khẩu và email không được để trống.")

        payload = self._read()
        users = payload.get("users", [])
        if not isinstance(users, list):
            users = []
        for item in users:
            if str(item.get("username", "")).strip() == u:
                raise ValueError("Username đã tồn tại.")
        users.append({"ID": self._next_id(), "username": u, "password": p, "email": e, "avatar_url": ""})
        payload["users"] = users
        self._write(payload)

    def verify(self, username: str, password: str) -> bool:
        u = (username or "").strip()
        p = (password or "").strip()
        if not u or not p:
            return False
        for item in self.list_users():
            if str(item.get("username", "")).strip() == u and str(item.get("password", "")).strip() == p:
                return True
        return False

    def login(self, username: str, password: str):
        if not self.verify(username, password):
            return None, None
        user = self.get_user(username) or {}
        user_id = str(user.get("ID", "") or "").strip() or None
        return user_id, user

    def update_password(self, username: str, new_password: str) -> None:
        u = (username or "").strip()
        p = (new_password or "").strip()
        if not u or not p:
            raise ValueError("Username và mật khẩu mới không được để trống.")

        payload = self._read()
        users = payload.get("users", [])
        if not isinstance(users, list):
            users = []

        updated = False
        for item in users:
            if str(item.get("username", "")).strip() == u:
                item["password"] = p
                updated = True
                break
        if not updated:
            raise ValueError("Không tìm thấy tài khoản.")

        payload["users"] = users
        self._write(payload)

        if self._mirror_password_func is not None:
            threading.Thread(target=self._mirror_password_func, args=(u, p), daemon=True).start()

    def update_avatar_url(self, username: str, avatar_url: str) -> None:
        u = (username or "").strip()
        url = (avatar_url or "").strip()
        if not u:
            raise ValueError("Username không được để trống.")
        payload = self._read()
        users = payload.get("users", [])
        if not isinstance(users, list):
            users = []

        updated = False
        for item in users:
            if str(item.get("username", "")).strip() == u:
                item["avatar_url"] = url
                updated = True
                break
        if not updated:
            raise ValueError("Không tìm thấy tài khoản.")

        payload["users"] = users
        self._write(payload)

    def append_search_history(self, username: str, query: str, results_count: int) -> None:
        u = (username or "").strip()
        q = (query or "").strip()
        if not u or not q:
            return

        payload = self._read()
        users = payload.get("users", [])
        if not isinstance(users, list):
            users = []

        for item in users:
            if str(item.get("username", "")).strip() != u:
                continue
            history = item.get("search_history")
            if not isinstance(history, list):
                history = []
            from datetime import datetime

            history.append({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "query": q, "results": int(results_count)})
            item["search_history"] = history[-50:]
            break

        payload["users"] = users
        self._write(payload)

    def get_search_history(self, username: str) -> list[dict]:
        user = self.get_user(username) or {}
        history = user.get("search_history", [])
        return list(history) if isinstance(history, list) else []
