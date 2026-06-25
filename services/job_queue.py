import logging
import queue
import threading
from datetime import datetime, timezone

import httpx

import config
from models.job import PROGRESS_MESSAGES, JobStatus
from services.crawler import crawl_website, normalize_url
from services.extractor import get_extractor
from services.storage import storage

log = logging.getLogger(__name__)


class JobQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True, name="analysis-worker")
        self._worker.start()
        self._recover_orphaned_jobs()

    def enqueue(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._active:
                return
            self._active.add(job_id)
        self._queue.put(job_id)
        log.info("Job %s enqueued", job_id)

    def _recover_orphaned_jobs(self) -> None:
        for job_id in storage.list_resumable_jobs():
            log.info("Re-queue orphaned job %s after server start", job_id)
            storage.update_job(
                job_id,
                status=JobStatus.QUEUED.value,
                progress=PROGRESS_MESSAGES["queued"],
                error_message=None,
            )
            self.enqueue(job_id)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
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
                    self._active.discard(job_id)
                self._queue.task_done()

    def _set_progress(self, job_id: str, key: str) -> None:
        storage.update_job(
            job_id,
            status=JobStatus.RUNNING.value,
            progress=PROGRESS_MESSAGES.get(key, "Analyse läuft…"),
        )

    def _process(self, job_id: str) -> None:
        job = storage.get_job(job_id)
        if not job:
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
        except RuntimeError as exc:
            log.warning("Job %s bedrock error: %s", job_id, exc)
            storage.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=str(exc),
                progress=str(exc),
            )
            return
        except Exception as exc:
            log.exception("Job %s extract failed", job_id)
            storage.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=str(exc),
                progress="Analyse fehlgeschlagen.",
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
