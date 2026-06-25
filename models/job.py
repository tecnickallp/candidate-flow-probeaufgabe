from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


PROGRESS_MESSAGES = {
    "queued": "Analyse wird vorbereitet…",
    "fetch_homepage": "Website wird gescannt…",
    "fetch_career": "Karriereseite wird gesucht…",
    "fetch_jobs": "Stellenanzeigen werden geladen…",
    "extract": "Daten werden extrahiert…",
    "save": "Ergebnisse werden gespeichert…",
}
