from __future__ import annotations

import json
import logging
import re
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from services.job_validation import (
    has_gender_inclusive_marking,
    has_job_type_fallback,
    looks_like_job_title,
)

log = logging.getLogger(__name__)

JOB_BOARD_VAR_RE = re.compile(
    r"window\['job_board_[^']+'\]\s*=\s*(\{.*?\})\s*;",
    re.S,
)
JOB_BOARD_MARKER_RE = re.compile(
    r'data-pattern="o-job-board"|window\[\'job_board_',
    re.I,
)
JOB_BOARD_API_PATHS = (
    "/api/jobs",
    "/api/jobs/search",
    "/api/job-board/jobs",
    "/api/public/jobs",
    "/api/v1/jobs",
)

JOB_RECORD_KEYS = ("title", "jobTitle", "job_title", "position", "name", "label", "stellentitel")
JOB_DESC_KEYS = ("description", "content", "body", "text", "summary", "aufgaben", "tasks")
JOB_LOCATION_KEYS = ("location", "city", "standort", "ort", "place")
JOB_COMPANY_KEYS = ("company", "employer", "unternehmen", "organization")

NAV_CATEGORY_RE = re.compile(
    r"^(?:"
    r"ausbildung(?:\s*&\s*duales\s+studium)?|"
    r"studentisches\s+praktikum|"
    r"werkstudierendentätigkeit|werkstudent|"
    r"traineeprogramm|direkteinstieg|"
    r"mehr\s+infos\s+zum\s+praktikum|"
    r"initiativbewerbung|"
    r"job-?abo|"
    r"berufe@edeka|"
    r"für\s+(?:schüler|studierende|berufseinsteiger|berufserfahrene|mitarbeiter)"
    r")\s*$",
    re.I,
)


def is_job_board_page(html: str) -> bool:
    if not html:
        return False
    return bool(JOB_BOARD_MARKER_RE.search(html))


def extract_job_board_config(html: str) -> dict | None:
    match = JOB_BOARD_VAR_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:48].strip("-")
    return slug or "stelle"


def _clean_text(text: str) -> str:
    text = unescape(re.sub(r"\s+", " ", text or "")).strip()
    return text


def _format_job_body(title: str, description: str = "", meta: list[str] | None = None) -> str:
    lines = [title.strip()]
    for item in meta or []:
        cleaned = _clean_text(item)
        if cleaned and cleaned not in lines:
            lines.append(cleaned)
    if description.strip():
        lines.append(_clean_text(description))
    return "\n".join(lines)


def _job_from_record(data: dict, source_url: str) -> tuple[str, str] | None:
    lower = {key.lower(): value for key, value in data.items() if isinstance(key, str)}
    title = ""
    for key in JOB_RECORD_KEYS:
        value = lower.get(key.lower())
        if isinstance(value, str) and value.strip():
            title = _clean_text(value)
            break
    if not title or not looks_like_job_title(title):
        if not title or not (has_gender_inclusive_marking(title) or has_job_type_fallback(title)):
            return None

    description = ""
    for key in JOB_DESC_KEYS:
        value = lower.get(key.lower())
        if isinstance(value, str) and value.strip():
            description = _clean_text(re.sub(r"<[^>]+>", " ", value))
            break

    meta: list[str] = []
    for keys, prefix in (
        (JOB_LOCATION_KEYS, "Standort"),
        (JOB_COMPANY_KEYS, "Unternehmen"),
    ):
        for key in keys:
            value = lower.get(key.lower())
            if isinstance(value, str) and value.strip():
                meta.append(f"{prefix}: {_clean_text(value)}")
                break
            if isinstance(value, dict):
                label = _clean_text(str(value.get("name") or value.get("label") or ""))
                if label:
                    meta.append(f"{prefix}: {label}")
                    break

    detail_url = source_url
    for key in ("url", "link", "detailUrl", "detail_url", "jobUrl", "job_url"):
        value = lower.get(key.lower())
        if isinstance(value, str) and value.strip().startswith("http"):
            detail_url = value.strip()
            break

    body = _format_job_body(title, description, meta)
    return f"{detail_url}#job-{_slugify(title)}", body


def _walk_job_records(value, source_url: str, found: list[tuple[str, str]], depth: int = 0) -> None:
    if depth > 10:
        return
    if isinstance(value, dict):
        job = _job_from_record(value, source_url)
        if job:
            found.append(job)
        for nested in value.values():
            _walk_job_records(nested, source_url, found, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _walk_job_records(item, source_url, found, depth + 1)


def _extract_jobs_from_api_payload(payload, source_url: str) -> list[tuple[str, str]]:
    jobs: list[tuple[str, str]] = []
    _walk_job_records(payload, source_url, jobs)
    return jobs


def fetch_job_board_api_jobs(
    client: httpx.Client,
    page_url: str,
    html: str,
) -> list[tuple[str, str]]:
    if not is_job_board_page(html):
        return []

    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": page_url,
        "Origin": origin,
    }

    for path in JOB_BOARD_API_PATHS:
        api_url = urljoin(origin + "/", path.lstrip("/"))
        for params in (
            None,
            {"limit": "100", "offset": "0"},
            {"pageSize": "100", "page": "1"},
        ):
            try:
                response = client.get(api_url, headers=headers, params=params, timeout=15.0)
            except httpx.HTTPError:
                continue
            if response.status_code >= 400:
                continue
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and not response.text.strip().startswith(("{", "[")):
                continue
            try:
                payload = response.json()
            except json.JSONDecodeError:
                continue
            jobs = _extract_jobs_from_api_payload(payload, page_url)
            if jobs:
                log.info("Job board API returned %s jobs from %s", len(jobs), api_url)
                return jobs
    return []


def _is_nav_category(title: str) -> bool:
    return bool(NAV_CATEGORY_RE.match(title.strip()))


def extract_jobs_from_job_board_html(html: str, page_url: str) -> list[tuple[str, str]]:
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one('[data-pattern="o-job-board"], .o-job-board')
    search_roots = [container] if container else [soup]

    jobs: list[tuple[str, str]] = []
    seen_titles: set[str] = set()

    for root in search_roots:
        if root is None:
            continue
        for anchor in root.find_all("a", href=True):
            title = _clean_text(anchor.get_text(" ", strip=True))
            if not title or _is_nav_category(title):
                continue
            if not looks_like_job_title(title):
                continue
            key = title.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            href = urljoin(page_url, anchor["href"].strip())
            jobs.append((f"{href}#job-{_slugify(title)}", title))

        for element in root.find_all(["h2", "h3", "h4", "strong", "span", "td", "li"]):
            title = _clean_text(element.get_text(" ", strip=True))
            if not title or _is_nav_category(title):
                continue
            if not looks_like_job_title(title):
                continue
            key = title.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            jobs.append((f"{page_url}#job-{_slugify(title)}", title))

    return jobs


def extract_job_board_content(
    client: httpx.Client,
    html: str,
    page_url: str,
) -> tuple[list[tuple[str, str]], list[str], str]:
    if not is_job_board_page(html):
        return [], [], ""

    config = extract_job_board_config(html) or {}
    text_parts: list[str] = []
    if config.get("textConfig", {}).get("headline"):
        text_parts.append(str(config["textConfig"]["headline"]))

    jobs = fetch_job_board_api_jobs(client, page_url, html)
    if not jobs:
        jobs = extract_jobs_from_job_board_html(html, page_url)

    return jobs, [], "\n".join(text_parts)
