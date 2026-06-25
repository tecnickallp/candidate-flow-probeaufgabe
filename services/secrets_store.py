from __future__ import annotations

import os

import config
from services import crypto
from services.storage import storage

SECRET_NAMES = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
}

ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def save_api_key(provider: str, api_key: str) -> None:
    provider = provider.lower().strip()
    secret_name = SECRET_NAMES.get(provider)
    if not secret_name:
        raise ValueError(f"Unbekannter Provider: {provider}")
    nonce, ciphertext = crypto.encrypt(api_key.strip())
    storage.upsert_secret(secret_name, provider, nonce, ciphertext)


def get_api_key(provider: str | None = None) -> str | None:
    provider = (provider or config.LLM_PROVIDER).lower().strip()
    env_var = ENV_KEYS.get(provider)
    if env_var:
        value = os.getenv(env_var, "").strip()
        if value:
            return value
    secret_name = SECRET_NAMES.get(provider)
    if not secret_name:
        return None
    stored = storage.get_secret(secret_name)
    if not stored:
        return None
    nonce, ciphertext = stored
    return crypto.decrypt(nonce, ciphertext)


def is_configured(provider: str | None = None) -> bool:
    return get_api_key(provider) is not None
