import queue
import threading
from datetime import datetime, timezone

import httpx

import config
from models.job import PROGRESS_MESSAGES, JobStatus
from services.crawler import crawl_website, normalize_url
from services.extractor import get_extractor
from services.storage import storage


class JobQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True, name="analysis-worker")
        self._worker.start()

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._process(job_id)
            except Exception as exc:  # noqa: BLE001
                storage.update_job(
                    job_id,
                    status=JobStatus.FAILED.value,
                    error_message=str(exc),
                    progress="Analyse fehlgeschlagen.",
                )
            finally:
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
        self._set_progress(job_id, "queued")

        def progress(key: str) -> None:
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
        try:
            result = get_extractor().extract(company_name, website_url, crawl.combined_text)
        except RuntimeError as exc:
            storage.update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=str(exc),
                progress=str(exc),
            )
            return

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


job_queue = JobQueue()
