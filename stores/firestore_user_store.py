from __future__ import annotations

import json
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

from config import FIREBASE_SERVICE_ACCOUNT_PATH
from services.imgbb import upload_file_to_imgbb


def init_firestore():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not FIREBASE_SERVICE_ACCOUNT_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy service account: {FIREBASE_SERVICE_ACCOUNT_PATH}")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(FIREBASE_SERVICE_ACCOUNT_PATH)))

    return firestore.client()


class FirestoreUserStore:
    """
    Schema: collection `users` dùng document id random (Firestore auto-id).
    Trả về `ID` = doc id để app dùng làm user_id.
    """

    def __init__(self):
        self.db = init_firestore()

    def _ensure_id(self, ref, data: dict) -> dict:
        doc_id = str(getattr(ref, "id", "") or "").strip()
        if doc_id:
            data["ID"] = doc_id
        return data

    def _get_user_doc(self, username: str):
        u = (username or "").strip()
        if not u:
            return None, None
        docs = self.db.collection("users").where("username", "==", u).limit(1).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            data = self._ensure_id(doc.reference, data)
            return doc.reference, data
        return None, None

    def _get_user_doc_by_id(self, user_id: str):
        uid = (user_id or "").strip()
        if not uid:
            return None, None
        doc = self.db.collection("users").document(uid).get()
        if not doc.exists:
            return None, None
        data = doc.to_dict() or {}
        ref = doc.reference
        data = self._ensure_id(ref, data)
        return ref, data

    def get_user(self, username: str) -> dict | None:
        _, data = self._get_user_doc(username)
        return data if data else None

    def _public_user(self, ref, data: dict) -> dict:
        safe = self._ensure_id(ref, data or {})
        return {
            "ID": str(safe.get("ID", "") or ""),
            "username": str(safe.get("username", "") or ""),
            "avatar_url": str(safe.get("avatar_url", "") or ""),
        }

    def get_public_user_by_id(self, user_id: str) -> dict | None:
        ref, data = self._get_user_doc_by_id(user_id)
        if ref is None or not data:
            return None
        return self._public_user(ref, data)

    def search_public_users(self, query: str, limit: int = 20) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []

        q_fold = q.casefold()
        matches: list[tuple[float, dict]] = []
        seen: set[str] = set()

        ref, data = self._get_user_doc_by_id(q)
        if ref is not None and data:
            item = self._public_user(ref, data)
            seen.add(item["ID"])
            matches.append((100.0, item))

        for doc in self.db.collection("users").stream():
            data = doc.to_dict() or {}
            username = str(data.get("username", "") or "")
            doc_id = str(getattr(doc, "id", "") or "")
            if doc_id in seen:
                continue
            username_fold = username.casefold()
            doc_id_fold = doc_id.casefold()
            score = 0.0
            if username_fold == q_fold or doc_id_fold == q_fold:
                score = 90.0
            elif username_fold.startswith(q_fold):
                score = 80.0
            elif q_fold in username_fold or q_fold in doc_id_fold:
                score = 70.0
            else:
                score = SequenceMatcher(None, q_fold, username_fold).ratio() * 60.0
            if score >= 35.0:
                item = self._public_user(doc.reference, data)
                seen.add(item["ID"])
                matches.append((score, item))
        matches.sort(key=lambda pair: (-pair[0], pair[1].get("username", "").casefold()))
        return [item for _score, item in matches[:limit]]

    def user_exists(self, username: str) -> bool:
        ref, _ = self._get_user_doc(username)
        return ref is not None

    def add_user(self, username: str, password: str, email: str) -> None:
        u = (username or "").strip()
        p = (password or "").strip()
        e = (email or "").strip()
        if not u or not p or not e:
            raise ValueError("Username, mật khẩu và email không được để trống.")
        if self.user_exists(u):
            raise ValueError("Username đã tồn tại.")

        doc_ref = self.db.collection("users").document()  # random id
        doc_ref.set({"username": u, "password": p, "email": e, "avatar_url": ""})

    def verify(self, username: str, password: str) -> bool:
        ref, data = self._get_user_doc(username)
        if ref is None:
            return False
        return str(data.get("password", "")).strip() == (password or "").strip()

    def login(self, username: str, password: str):
        ref, data = self._get_user_doc(username)
        if ref is None:
            return None, None
        if str(data.get("password", "")).strip() != (password or "").strip():
            return None, None
        return getattr(ref, "id", None), data

    def update_password(self, username: str, new_password: str) -> None:
        ref, _ = self._get_user_doc(username)
        if ref is None:
            raise ValueError("Không tìm thấy tài khoản.")
        p = (new_password or "").strip()
        if not p:
            raise ValueError("Mật khẩu mới không được để trống.")
        ref.update({"password": p})

    def update_password_by_id(self, user_id: str, new_password: str) -> None:
        ref, _ = self._get_user_doc_by_id(user_id)
        if ref is None:
            raise ValueError("Không tìm thấy tài khoản.")
        p = (new_password or "").strip()
        if not p:
            raise ValueError("Mật khẩu mới không được để trống.")
        ref.update({"password": p})

    def update_avatar_url(self, username: str, avatar_url: str) -> None:
        ref, _ = self._get_user_doc(username)
        if ref is None:
            raise ValueError("Không tìm thấy tài khoản.")
        ref.update({"avatar_url": (avatar_url or "").strip()})

    def update_avatar_url_by_id(self, user_id: str, avatar_url: str) -> None:
        ref, _ = self._get_user_doc_by_id(user_id)
        if ref is None:
            raise ValueError("Không tìm thấy tài khoản.")
        ref.update({"avatar_url": (avatar_url or "").strip()})

    def append_search_history(self, username: str, query: str, results_count: int) -> None:
        ref, _data = self._get_user_doc(username)
        if ref is None:
            return
        ref.collection("search_history").add({"ts": datetime.now(), "query": (query or "").strip(), "results": int(results_count)})

    def append_search_history_by_id(self, user_id: str, query: str, results_count: int) -> None:
        ref, _data = self._get_user_doc_by_id(user_id)
        if ref is None:
            return
        ref.collection("search_history").add({"ts": datetime.now(), "query": (query or "").strip(), "results": int(results_count)})

    def get_search_history(self, username: str) -> list[dict]:
        ref, data = self._get_user_doc(username)
        if ref is None or not data:
            return []
        docs = ref.collection("search_history").order_by("ts", direction="DESCENDING").limit(50).stream()
        out: list[dict] = []
        for doc in docs:
            d = doc.to_dict() or {}
            ts = d.get("ts")
            if ts is not None:
                d["ts"] = str(ts).replace("T", " ")[:19]
            out.append(d)
        return list(reversed(out))

    def get_search_history_by_id(self, user_id: str) -> list[dict]:
        ref, data = self._get_user_doc_by_id(user_id)
        if ref is None or not data:
            return []
        docs = ref.collection("search_history").order_by("ts", direction="DESCENDING").limit(50).stream()
        out: list[dict] = []
        for doc in docs:
            d = doc.to_dict() or {}
            ts = d.get("ts")
            if ts is not None:
                d["ts"] = str(ts).replace("T", " ")[:19]
            out.append(d)
        return list(reversed(out))

    def upload_avatar_and_get_url_by_id(self, user_id: str, file_path: str) -> str:
        ref, _ = self._get_user_doc_by_id(user_id)
        if ref is None:
            raise ValueError("Không tìm thấy tài khoản.")
        url = upload_file_to_imgbb(file_path)
        ref.update({"avatar_url": url})
        return url


def sync_user_json_to_firebase(json_path: Path) -> int:
    store = FirestoreUserStore()
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    users = payload.get("users", [])
    if not isinstance(users, list):
        return 0
    count = 0
    for user in users:
        if not isinstance(user, dict):
            continue
        username = str(user.get("username", "") or "").strip()
        if not username:
            continue
        ref, _ = store._get_user_doc(username)
        if ref is None:
            ref = store.db.collection("users").document()
        ref.set(
            {
                "username": username,
                "password": str(user.get("password", "") or ""),
                "email": str(user.get("email", "") or ""),
                "avatar_url": str(user.get("avatar_url", "") or ""),
            },
            merge=True,
        )
        history = user.get("search_history", [])
        if isinstance(history, list):
            for item in history[-50:]:
                q = str(item.get("query", "") or "").strip()
                if not q:
                    continue
                results = int(item.get("results", 0) or 0)
                ts_raw = str(item.get("ts", "") or "").strip()
                ts_value = datetime.now()
                if ts_raw:
                    try:
                        ts_value = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts_value = datetime.now()
                ref.collection("search_history").add({"ts": ts_value, "query": q, "results": results})
        count += 1
    return count


def delete_firestore_users_with_6digit_doc_ids() -> list[str]:
    store = FirestoreUserStore()
    deleted: list[str] = []
    for doc in store.db.collection("users").stream():
        doc_id = str(getattr(doc, "id", "") or "").strip()
        if not (doc_id.isdigit() and len(doc_id) == 6):
            continue
        ref = doc.reference
        try:
            for hdoc in ref.collection("search_history").stream():
                try:
                    hdoc.reference.delete()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            ref.delete()
            deleted.append(doc_id)
        except Exception:
            pass
    return deleted
