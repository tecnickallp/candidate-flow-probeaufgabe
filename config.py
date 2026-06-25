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
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "10"))

USER_AGENT = (
    "CandidateFlow-Analyzer/1.0 (+https://candidate-flow.de; recruitment research bot)"
)


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


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
