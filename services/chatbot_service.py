from __future__ import annotations

import os
from pathlib import Path

import requests

from config import PROJECT_ROOT


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class ChatbotService:
    PREFERRED_MODELS = (
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
        "qwen/qwen3.6-27b",
    )

    def __init__(self):
        _load_env_file(PROJECT_ROOT / ".env")
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
        self.backup_api_key = os.getenv("GROQ_BACKUP_API_KEY", "").strip()
        self.backup_model = os.getenv("GROQ_BACKUP_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant"
        self._model_cache: dict[str, set[str]] = {}
        self.model = self._resolve_model(self.api_key, self.model)
        self.backup_model = self._resolve_model(self.backup_api_key, self.backup_model)

    def has_api_key(self) -> bool:
        return bool(self.api_key) and self.api_key != "replace_with_new_groq_api_key"

    def has_backup_api_key(self) -> bool:
        return bool(self.backup_api_key) and self.backup_api_key != "replace_with_backup_groq_api_key"

    def answer(self, question: str, context: str) -> str:
        question = (question or "").strip()
        context = (context or "").strip()
        if not question:
            return "B\u1ea1n h\u00e3y nh\u1eadp c\u00e2u h\u1ecfi tr\u01b0\u1edbc nh\u00e9."
        if not context:
            return (
                "M\u00ecnh ch\u1ec9 tr\u1ea3 l\u1eddi c\u00e2u h\u1ecfi li\u00ean quan \u0111\u1ebfn d\u1eef li\u1ec7u "
                "l\u1ecbch s\u1eed trong app. Hi\u1ec7n app ch\u01b0a t\u00ecm th\u1ea5y d\u1eef li\u1ec7u ph\u00f9 h\u1ee3p "
                "v\u1edbi c\u00e2u h\u1ecfi n\u00e0y."
            )

        providers = self._available_providers()
        if not providers:
            return self._fallback_answer(context)

        prompt = (
            "B\u1ea1n l\u00e0 chatbot h\u1ed7 tr\u1ee3 app T\u1eeb \u0111i\u1ec3n L\u1ecbch s\u1eed Vi\u1ec7t Nam.\n"
            "Ch\u1ec9 tr\u1ea3 l\u1eddi d\u1ef1a tr\u00ean ph\u1ea7n d\u1eef li\u1ec7u li\u00ean quan \u0111\u01b0\u1ee3c cung c\u1ea5p.\n"
            "N\u1ebfu d\u1eef li\u1ec7u kh\u00f4ng \u0111\u1ee7, n\u00f3i r\u00f5 app ch\u01b0a c\u00f3 \u0111\u1ee7 d\u1eef li\u1ec7u \u0111\u1ec3 k\u1ebft lu\u1eadn.\n"
            "Tr\u1ea3 l\u1eddi b\u1eb1ng ti\u1ebfng Vi\u1ec7t, ng\u1eafn g\u1ecdn, d\u1ec5 hi\u1ec3u.\n\n"
            f"C\u00e2u h\u1ecfi: {question}\n\n"
            f"D\u1eef li\u1ec7u li\u00ean quan:\n{context}"
        )

        errors: list[str] = []
        for label, api_key, model in providers:
            try:
                return self._call_groq(api_key, model, prompt)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                detail = self._extract_error_detail(exc.response)
                errors.append(f"{label}: HTTP {status} - {detail}")
                continue
            except requests.RequestException as exc:
                errors.append(f"{label}: {exc}")
                continue

        return (
            "C\u1ea3 Groq API ch\u00ednh v\u00e0 backup \u0111\u1ec1u ch\u01b0a tr\u1ea3 l\u1eddi \u0111\u01b0\u1ee3c.\n\n"
            "Chi ti\u1ebft:\n- "
            + "\n- ".join(errors)
            + "\n\nT\u1ea1m th\u1eddi m\u00ecnh tr\u1ea3 k\u1ebft qu\u1ea3 t\u00ecm ki\u1ebfm n\u1ed9i b\u1ed9:\n\n"
            + context
        )

    def _available_providers(self) -> list[tuple[str, str, str]]:
        providers: list[tuple[str, str, str]] = []
        if self.has_api_key():
            providers.append(("Groq chính", self.api_key, self.model))
        if self.has_backup_api_key():
            providers.append(("Groq backup", self.backup_api_key, self.backup_model))
        return providers

    def _resolve_model(self, api_key: str, preferred_model: str) -> str:
        preferred_model = (preferred_model or "").strip()
        if not api_key:
            return preferred_model

        available = self._get_available_model_ids(api_key)
        if not available:
            return preferred_model
        if preferred_model in available:
            return preferred_model

        for candidate in self.PREFERRED_MODELS:
            if candidate in available:
                return candidate

        return sorted(available)[0]

    def _get_available_model_ids(self, api_key: str) -> set[str]:
        cached = self._model_cache.get(api_key)
        if cached is not None:
            return cached

        try:
            response = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            models = {
                str(item.get("id", "") or "").strip()
                for item in payload.get("data", [])
                if str(item.get("id", "") or "").strip()
            }
        except Exception:
            models = set()

        self._model_cache[api_key] = models
        return models

    def _call_groq(self, api_key: str, model: str, prompt: str) -> str:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "B\u1ea1n l\u00e0 tr\u1ee3 l\u00fd l\u1ecbch s\u1eed Vi\u1ec7t Nam trong m\u1ed9t \u1ee9ng d\u1ee5ng h\u1ecdc t\u1eadp.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()

    def _fallback_answer(self, context: str) -> str:
        return "Ch\u01b0a c\u00f3 Groq API key ho\u1eb7c backup key h\u1ee3p l\u1ec7 trong .env. \u0110\u00e2y l\u00e0 k\u1ebft qu\u1ea3 t\u00ecm ki\u1ebfm n\u1ed9i b\u1ed9:\n\n" + context

    def _extract_error_detail(self, response) -> str:
        if response is None:
            return "kh\u00f4ng c\u00f3 ph\u1ea3n h\u1ed3i chi ti\u1ebft"
        try:
            payload = response.json()
            error = payload.get("error", payload)
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or error)
            return str(error)
        except Exception:
            return response.text[:500]
