from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
USE_HEURISTIC_FALLBACK = os.getenv("USE_HEURISTIC_FALLBACK", "true").lower() in ("1", "true", "yes")

AWS_BEDROCK_REGION = os.getenv("AWS_BEDROCK_REGION", "eu-north-1").strip()
AWS_BEDROCK_MODEL_ID = os.getenv(
    "AWS_BEDROCK_MODEL_ID", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
).strip()

JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "90"))
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "15"))
USE_PLAYWRIGHT_FALLBACK = os.getenv("USE_PLAYWRIGHT_FALLBACK", "false").lower() in ("1", "true", "yes")
PLAYWRIGHT_TIMEOUT_SECONDS = int(os.getenv("PLAYWRIGHT_TIMEOUT_SECONDS", "25"))

USER_AGENT = (
    "CandidateFlow-Analyzer/1.0 (+https://candidate-flow.de; recruitment research bot)"
)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "auto").strip().lower()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
LEAD_NOTIFICATION_TO = os.getenv("LEAD_NOTIFICATION_TO", "artur.b@candidate-flow.de").strip()
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "false").lower() in ("1", "true", "yes")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def resend_configured() -> bool:
    return bool(RESEND_API_KEY)


def brevo_configured() -> bool:
    return bool(BREVO_API_KEY)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def resolve_email_provider() -> str | None:
    if EMAIL_DRY_RUN:
        return None
    if EMAIL_PROVIDER != "auto":
        return EMAIL_PROVIDER
    if brevo_configured():
        return "brevo"
    if resend_configured():
        return "resend"
    if smtp_configured():
        return "smtp"
    return None


def email_configured() -> bool:
    return resolve_email_provider() is not None


def resolve_master_key() -> bytes:
    env_key = os.getenv("MASTER_ENCRYPTION_KEY", "").strip()
    if env_key:
        key = base64.b64decode(env_key)
        if len(key) != 32:
            raise ValueError("MASTER_ENCRYPTION_KEY muss 32 Bytes (Base64) sein.")
        return key

    key_file = DATA_DIR / ".encryption_key"
    if key_file.exists():
        return base64.b64decode(key_file.read_text(encoding="utf-8").strip())

    key = os.urandom(32)
    key_file.write_text(base64.b64encode(key).decode("ascii"), encoding="utf-8")
    return key
