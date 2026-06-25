import logging
import threading
from datetime import datetime, timezone

import httpx

import config
from models.job import PROGRESS_MESSAGES, JobStatus
from services.crawler import crawl_website, normalize_url
from services.extractor import get_extractor, merge_parsed_benefits_from_crawl
from services.storage import storage

log = logging.getLogger(__name__)


class JobQueue:
    def __init__(self) -> None:
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._fail_orphaned_jobs()

    def enqueue(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._running:
                log.info("Job %s already running, skip duplicate enqueue", job_id)
                return
            self._running.add(job_id)

        def run() -> None:
            try:
                self._process(job_id)
            except Exception as exc:  # noqa: BLE001
                log.exception("Job %s failed", job_id)
                storage.update_job(
                    job_id,
                    status=JobStatus.FAILED.value,
                    error_message=str(exc),
                    progress="Analyse fehlgeschlagen.",
                )
            finally:
                with self._lock:
                    self._running.discard(job_id)

        thread = threading.Thread(target=run, daemon=True, name=f"analysis-{job_id[:8]}")
        thread.start()
        log.info("Job %s background thread started", job_id)

    def _fail_orphaned_jobs(self) -> None:
        message = "Analyse abgebrochen (Server-Neustart). Bitte erneut starten."
        for job_id in storage.list_resumable_jobs():
            log.info("Mark orphaned job %s as failed after server start", job_id)
            storage.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=message,
                progress=message,
            )

    def _set_progress(self, job_id: str, key: str) -> None:
        storage.update_job(
            job_id,
            status=JobStatus.RUNNING.value,
            progress=PROGRESS_MESSAGES.get(key, "Analyse läuft…"),
        )

    def _process(self, job_id: str) -> None:
        job = storage.get_job(job_id)
        if not job:
            log.warning("Job %s not found in storage", job_id)
            return
        if job.get("status") == JobStatus.FAILED.value:
            log.info("Job %s already failed, skip processing", job_id)
            return

        company_name = job["company_name"]
        website_url = normalize_url(job["website_url"])
        log.info("Job %s started for %s", job_id, website_url)
        self._set_progress(job_id, "queued")

        def progress(key: str) -> None:
            log.info("Job %s progress: %s", job_id, key)
            self._set_progress(job_id, key)

        try:
            crawl = crawl_website(website_url, progress_callback=progress)
        except httpx.HTTPError as exc:
            storage.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=f"Website nicht erreichbar: {exc}",
                progress="Website konnte nicht geladen werden.",
            )
            return

        progress("extract")
        log.info(
            "Job %s calling Bedrock model %s (read_timeout=%ss)",
            job_id,
            config.AWS_BEDROCK_MODEL_ID,
            config.JOB_TIMEOUT_SECONDS,
        )
        try:
            result = get_extractor().extract(company_name, website_url, crawl.combined_text)
            result = merge_parsed_benefits_from_crawl(result, crawl.combined_text)
        except RuntimeError as exc:
            log.warning("Job %s bedrock error: %s", job_id, exc)
            storage.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=str(exc),
                progress=str(exc),
            )
            return

        log.info("Job %s extract completed", job_id)
        progress("save")
        payload = result.to_storage_dict()
        payload["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        analysis_id = storage.save_analysis(payload)
        storage.update_job(
            job_id,
            status=JobStatus.COMPLETED.value,
            analysis_id=analysis_id,
            progress="Analyse abgeschlossen.",
        )
        log.info("Job %s completed -> %s", job_id, analysis_id)


job_queue = JobQueue()
