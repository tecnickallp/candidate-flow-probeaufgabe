from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, url_for

import config
from models.job import JobStatus
from services.job_queue import job_queue
from services.secrets_store import is_configured, save_api_key
from services.storage import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

app = Flask(__name__)


@app.context_processor
def inject_logos():
    return {
        "logo_dark": url_for("static", filename="img/logo-dark.svg"),
        "logo_light": url_for("static", filename="img/logo-light.svg"),
    }


def validate_url(url: str) -> str | None:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return url


def _fail_stale_job(job: dict) -> dict:
    # Nur verwaiste queued-Jobs (z. B. nach Deploy). running-Jobs können bei Bedrock
    # länger als JOB_TIMEOUT dauern — die beendet job_queue selbst mit Fehler/Timeout.
    if job.get("status") != JobStatus.QUEUED.value:
        return job
    updated_at = job.get("updated_at")
    if not updated_at:
        return job
    try:
        last_update = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return job
    stale_after = timedelta(seconds=config.JOB_TIMEOUT_SECONDS + 120)
    if datetime.now(timezone.utc) - last_update <= stale_after:
        return job
    message = (
        "Analyse abgebrochen (Server-Neustart). "
        "Bitte erneut starten."
    )
    storage.update_job(
        job["id"],
        status=JobStatus.FAILED.value,
        error_message=message,
        progress=message,
    )
    refreshed = storage.get_job(job["id"])
    return refreshed or job


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/styleguide")
def styleguide():
    return render_template("styleguide.html")


@app.route("/settings", methods=["GET"])
def settings_page():
    return render_template(
        "settings.html",
        provider=config.LLM_PROVIDER,
        configured=is_configured(),
    )


@app.route("/results/<analysis_id>")
def results_page(analysis_id: str):
    analysis = storage.get_analysis(analysis_id)
    if not analysis:
        return render_template("404.html"), 404
    return render_template("results.html", analysis=analysis)


@app.route("/api/analyze", methods=["POST"])
def start_analysis():
    data = request.get_json(silent=True) or {}
    company_name = (data.get("company_name") or "").strip()
    website_url = validate_url(data.get("website_url") or "")

    if not company_name:
        return jsonify({"error": "Firmenname ist erforderlich."}), 400
    if not website_url:
        return jsonify({"error": "Bitte eine gültige Website-URL eingeben."}), 400

    job_id = storage.create_job(company_name, website_url)
    log.info("Analysis queued: job_id=%s url=%s", job_id, website_url)
    job_queue.enqueue(job_id)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/api/jobs/<job_id>")
def get_job_status(job_id: str):
    job = storage.get_job(job_id)
    if not job:
        return jsonify({"error": "Job nicht gefunden."}), 404
    job = _fail_stale_job(job)
    payload = {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job.get("progress"),
        "analysis_id": job.get("analysis_id"),
        "error": job.get("error_message"),
    }
    return jsonify(payload)


@app.route("/api/analyses/<analysis_id>")
def get_analysis_json(analysis_id: str):
    analysis = storage.get_analysis(analysis_id)
    if not analysis:
        return jsonify({"error": "Analyse nicht gefunden."}), 404
    return jsonify(analysis)


@app.route("/api/settings/llm")
def get_llm_settings():
    return jsonify({
        "provider": config.LLM_PROVIDER,
        "configured": is_configured(),
    })


@app.route("/health")
def health():
    payload: dict = {"status": "ok", "storage": storage.backend}
    try:
        payload["storage_detail"] = storage.ping()
    except Exception as exc:
        log.exception("Storage health check failed")
        payload["status"] = "degraded"
        payload["storage_error"] = str(exc)
        return jsonify(payload), 503
    if storage.backend == "sqlite":
        payload["warning"] = (
            "SQLite ist auf Render flüchtig. SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY setzen."
        )
    return jsonify(payload), 200


@app.route("/api/settings/llm-key", methods=["PUT"])
def save_llm_key():
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or config.LLM_PROVIDER).strip().lower()
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"error": "API-Key ist erforderlich."}), 400
    try:
        save_api_key(provider, api_key)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"provider": provider, "configured": True})


if __name__ == "__main__":
    app.run(debug=True, port=8000)
