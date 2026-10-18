import json
import os
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import Flask, jsonify, request


def init_firebase():
    import firebase_admin
    from firebase_admin import credentials, firestore

    base_dir = Path(__file__).resolve().parents[1]
    service_account = Path(os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", str(base_dir / "tudienlichsuvietnam-firebase-adminsdk-fbsvc-da94ea01c6.json")))
    if not service_account.exists():
        raise FileNotFoundError(f"Missing service account json: {service_account}")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(service_account)))

    return firestore.client()


db = init_firebase()
app = Flask(__name__)


def find_user_doc_by_username(username: str):
    docs = db.collection("users").where("username", "==", username).limit(1).stream()
    for doc in docs:
        return doc.reference, doc.to_dict() or {}
    return None, None


def find_user_doc_by_id(user_id: str):
    docs = db.collection("users").where("ID", "==", user_id).limit(1).stream()
    for doc in docs:
        return doc.reference, doc.to_dict() or {}
    return None, None


def upload_to_imgbb(file_bytes: bytes, filename: str, mimetype: str) -> str:
    import requests

    api_key = os.getenv("IMGBB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing IMGBB_API_KEY")
    endpoint = os.getenv("IMGBB_ENDPOINT", "https://api.imgbb.com/1/upload").strip()

    files = {"image": (filename or "avatar.png", file_bytes, mimetype or "application/octet-stream")}
    resp = requests.post(endpoint, params={"key": api_key}, files=files, timeout=60)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    data = payload.get("data") or {}
    url = str(data.get("url") or data.get("display_url") or "").strip()
    if not url:
        raise RuntimeError("ImgBB response missing url")
    return url


@app.post("/upload-avatar")
def upload_avatar():
    user_id = (request.form.get("user_id") or "").strip()
    username = (request.form.get("username") or "").strip()
    if not user_id and not username:
        return jsonify({"error": "missing user_id or username"}), 400
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "empty filename"}), 400

    ref, data = (find_user_doc_by_id(user_id) if user_id else (None, None))
    if ref is None:
        ref, data = find_user_doc_by_username(username)
    if ref is None:
        return jsonify({"error": "user not found"}), 404

    user_id = str((data or {}).get("ID", "") or "").strip()
    if not user_id:
        user_id = f"{uuid.uuid4().int % 1000000:06d}"
        try:
            ref.update({"ID": user_id})
        except Exception:
            pass

    url = upload_to_imgbb(file.read(), file.filename, file.mimetype or "application/octet-stream")
    ref.update({"avatar_url": url})
    return jsonify({"avatar_url": url})


if __name__ == "__main__":
    # Dev server
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5055")), debug=True)
