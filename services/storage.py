from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

import httpx

import config

log = logging.getLogger(__name__)

T = TypeVar("T")

_TRANSIENT_HTTP_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY,
  company_name TEXT NOT NULL,
  website_url TEXT NOT NULL,
  industry TEXT,
  benefits TEXT DEFAULT '[]',
  vibe TEXT,
  jobs TEXT DEFAULT '[]',
  analyzed_at TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS analysis_jobs (
  id TEXT PRIMARY KEY,
  company_name TEXT NOT NULL,
  website_url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress TEXT,
  analysis_id TEXT,
  error_message TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS encrypted_secrets (
  id TEXT PRIMARY KEY,
  secret_name TEXT NOT NULL UNIQUE,
  provider TEXT NOT NULL,
  ciphertext BLOB NOT NULL,
  nonce BLOB NOT NULL,
  created_at TEXT,
  updated_at TEXT
);
"""


def _bytea_to_db(value: bytes) -> str:
    """PostgREST/Supabase bytea JSON format."""
    return "\\x" + value.hex()


def _bytea_from_db(value: Any) -> bytes:
    if isinstance(value, str):
        if value.startswith("\\x"):
            return bytes.fromhex(value[2:])
        return bytes.fromhex(value)
    return bytes(value)


def _create_supabase_client():
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions

    # HTTP/2-Verbindungen zu Supabase brechen auf Render gelegentlich ab (RemoteProtocolError).
    http_client = httpx.Client(http2=False, timeout=30.0)
    options = SyncClientOptions(httpx_client=http_client)
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY, options=options)


class Storage:
    def __init__(self) -> None:
        self._supabase = None
        if config.supabase_configured():
            self._supabase = _create_supabase_client()
            log.info("Storage backend: Supabase")
        else:
            config.DATA_DIR.mkdir(exist_ok=True)
            self._db_path = config.DATA_DIR / "app.db"
            self._init_sqlite()
            log.warning(
                "Storage backend: SQLite (%s) — auf Render flüchtig; SUPABASE_* setzen für Persistenz",
                self._db_path,
            )

    @property
    def backend(self) -> str:
        return "supabase" if self._supabase else "sqlite"

    def _reset_supabase_client(self) -> None:
        if config.supabase_configured():
            self._supabase = _create_supabase_client()
            log.info("Supabase client recreated after connection error")

    def _execute_supabase(self, operation: Callable[[], T], *, op_name: str) -> T:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return operation()
            except _TRANSIENT_HTTP_ERRORS as exc:
                last_exc = exc
                log.warning(
                    "Supabase %s failed (attempt %s/3): %s",
                    op_name,
                    attempt + 1,
                    exc,
                )
                if attempt < 2:
                    self._reset_supabase_client()
                    time.sleep(0.4 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def ping(self) -> dict[str, Any]:
        """Connectivity check and row counts for health/debug."""
        if self._supabase:
            analyses = self._execute_supabase(
                lambda: self._supabase.table("analyses").select("id", count="exact").limit(1).execute(),
                op_name="ping analyses",
            )
            jobs = self._execute_supabase(
                lambda: self._supabase.table("analysis_jobs").select("id", count="exact").limit(1).execute(),
                op_name="ping jobs",
            )
            return {
                "backend": "supabase",
                "ok": True,
                "analyses_count": analyses.count or 0,
                "jobs_count": jobs.count or 0,
            }
        with sqlite3.connect(self._db_path) as conn:
            analyses_count = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            jobs_count = conn.execute("SELECT COUNT(*) FROM analysis_jobs").fetchone()[0]
        return {
            "backend": "sqlite",
            "ok": True,
            "analyses_count": analyses_count,
            "jobs_count": jobs_count,
            "path": str(self._db_path),
        }

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_job(self, company_name: str, website_url: str) -> str:
        job_id = str(uuid.uuid4())
        now = self._now()
        row = {
            "id": job_id,
            "company_name": company_name,
            "website_url": website_url,
            "status": "queued",
            "progress": "Analyse wird vorbereitet…",
            "analysis_id": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        if self._supabase:
            try:
                self._execute_supabase(
                    lambda: self._supabase.table("analysis_jobs").insert(row).execute(),
                    op_name=f"insert job {job_id}",
                )
            except Exception:
                log.exception("Supabase insert failed for analysis_jobs id=%s", job_id)
                raise
        else:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO analysis_jobs
                    (id, company_name, website_url, status, progress, analysis_id, error_message, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["id"], row["company_name"], row["website_url"], row["status"],
                        row["progress"], row["analysis_id"], row["error_message"],
                        row["created_at"], row["updated_at"],
                    ),
                )
        return job_id

    def update_job(self, job_id: str, **fields: Any) -> None:
        fields["updated_at"] = self._now()
        if self._supabase:
            self._execute_supabase(
                lambda: self._supabase.table("analysis_jobs").update(fields).eq("id", job_id).execute(),
                op_name=f"update job {job_id}",
            )
        else:
            cols = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [job_id]
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(f"UPDATE analysis_jobs SET {cols} WHERE id = ?", vals)

    def get_job(self, job_id: str) -> Optional[dict]:
        if self._supabase:
            res = self._execute_supabase(
                lambda: self._supabase.table("analysis_jobs").select("*").eq("id", job_id).limit(1).execute(),
                op_name=f"get job {job_id}",
            )
            return res.data[0] if res.data else None
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_resumable_jobs(self) -> list[str]:
        statuses = ("queued", "running")
        if self._supabase:
            res = self._execute_supabase(
                lambda: (
                    self._supabase.table("analysis_jobs")
                    .select("id")
                    .in_("status", list(statuses))
                    .order("created_at")
                    .execute()
                ),
                op_name="list resumable jobs",
            )
            return [row["id"] for row in res.data or []]
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id FROM analysis_jobs WHERE status IN (?, ?) ORDER BY created_at",
                statuses,
            ).fetchall()
            return [row[0] for row in rows]

    def save_analysis(self, data: dict) -> str:
        analysis_id = str(uuid.uuid4())
        now = self._now()
        row = {
            "id": analysis_id,
            "company_name": data["company_name"],
            "website_url": data["website_url"],
            "industry": data.get("industry") or "",
            "benefits": data.get("benefits") or [],
            "vibe": data.get("vibe") or "",
            "jobs": data.get("jobs") or [],
            "analyzed_at": data.get("analyzed_at") or now,
            "created_at": now,
        }
        if self._supabase:
            try:
                self._execute_supabase(
                    lambda: self._supabase.table("analyses").insert(row).execute(),
                    op_name=f"insert analysis {analysis_id}",
                )
            except Exception:
                log.exception("Supabase insert failed for analyses company=%s", row["company_name"])
                raise
        else:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO analyses
                    (id, company_name, website_url, industry, benefits, vibe, jobs, analyzed_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["id"], row["company_name"], row["website_url"], row["industry"],
                        json.dumps(row["benefits"], ensure_ascii=False),
                        row["vibe"],
                        json.dumps(row["jobs"], ensure_ascii=False),
                        row["analyzed_at"], row["created_at"],
                    ),
                )
        return analysis_id

    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        if self._supabase:
            res = self._execute_supabase(
                lambda: self._supabase.table("analyses").select("*").eq("id", analysis_id).limit(1).execute(),
                op_name=f"get analysis {analysis_id}",
            )
            row = res.data[0] if res.data else None
        else:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
                row = dict(row) if row else None
        if not row:
            return None
        if isinstance(row.get("benefits"), str):
            row["benefits"] = json.loads(row["benefits"])
        if isinstance(row.get("jobs"), str):
            row["jobs"] = json.loads(row["jobs"])
        return row

    def upsert_secret(self, secret_name: str, provider: str, nonce: bytes, ciphertext: bytes) -> None:
        now = self._now()
        row = {
            "id": str(uuid.uuid4()),
            "secret_name": secret_name,
            "provider": provider,
            "nonce": nonce,
            "ciphertext": ciphertext,
            "created_at": now,
            "updated_at": now,
        }
        if self._supabase:
            existing = self._execute_supabase(
                lambda: (
                    self._supabase.table("encrypted_secrets")
                    .select("id")
                    .eq("secret_name", secret_name)
                    .limit(1)
                    .execute()
                ),
                op_name=f"get secret {secret_name}",
            )
            payload = {
                "provider": provider,
                "nonce": _bytea_to_db(nonce),
                "ciphertext": _bytea_to_db(ciphertext),
                "updated_at": now,
            }
            if existing.data:
                self._execute_supabase(
                    lambda: (
                        self._supabase.table("encrypted_secrets")
                        .update(payload)
                        .eq("secret_name", secret_name)
                        .execute()
                    ),
                    op_name=f"update secret {secret_name}",
                )
            else:
                payload.update({"secret_name": secret_name, "created_at": now})
                self._execute_supabase(
                    lambda: self._supabase.table("encrypted_secrets").insert(payload).execute(),
                    op_name=f"insert secret {secret_name}",
                )
        else:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO encrypted_secrets (id, secret_name, provider, ciphertext, nonce, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(secret_name) DO UPDATE SET
                      provider=excluded.provider,
                      ciphertext=excluded.ciphertext,
                      nonce=excluded.nonce,
                      updated_at=excluded.updated_at""",
                    (row["id"], secret_name, provider, ciphertext, nonce, now, now),
                )

    def get_secret(self, secret_name: str) -> Optional[tuple[bytes, bytes]]:
        if self._supabase:
            res = self._execute_supabase(
                lambda: (
                    self._supabase.table("encrypted_secrets")
                    .select("*")
                    .eq("secret_name", secret_name)
                    .limit(1)
                    .execute()
                ),
                op_name=f"fetch secret {secret_name}",
            )
            if not res.data:
                return None
            item = res.data[0]
            return _bytea_from_db(item["nonce"]), _bytea_from_db(item["ciphertext"])
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT nonce, ciphertext FROM encrypted_secrets WHERE secret_name = ?",
                (secret_name,),
            ).fetchone()
            return (row[0], row[1]) if row else None


storage = Storage()
