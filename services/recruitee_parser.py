from __future__ import annotations

import json
import logging
import re
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx

from services.job_validation import looks_like_job_title

log = logging.getLogger(__name__)

RECRUITEE_MARKER_RE = re.compile(
    r'recruitee-careers|RTWidget|\.recruitee\.com|recruitee\.com/api/offers',
    re.I,
)
RECRUITEE_SLUG_RE = re.compile(r"https?://([a-z0-9-]+)\.recruitee\.com", re.I)
RTWIDGET_COMPANIES_RE = re.compile(
    r"RTWidget\s*\(\s*\{.*?\"companies\"\s*:\s*\[\s*(\d+)\s*\]",
    re.S,
)


def is_recruitee_page(html: str) -> bool:
    return bool(html and RECRUITEE_MARKER_RE.search(html))


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:48].strip("-")
    return slug or "stelle"


def _clean_text(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _slug_candidates_from_domain(page_url: str) -> list[str]:
    host = urlparse(page_url).netloc.replace("www.", "")
    base = host.split(".")[0].lower()
    parts = [part for part in re.split(r"[-_]", base) if part]
    candidates: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"[^a-z0-9-]", "", value.lower()).strip("-")
        if value and value not in candidates:
            candidates.append(value)

    add(base.replace("-", ""))
    add(base)
    if len(parts) >= 2:
        add("".join(parts))
        add("".join(parts[:2]))
        add("".join(parts[:-1]))
    if parts:
        add(parts[0])
    return candidates


def discover_recruitee_slugs(html: str, page_url: str) -> list[str]:
    slugs = RECRUITEE_SLUG_RE.findall(html)
    slugs.extend(_slug_candidates_from_domain(page_url))
    unique: list[str] = []
    seen: set[str] = set()
    for slug in slugs:
        key = slug.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(slug.lower())
    return unique


def _offer_to_job(offer: dict, slug: str, source_url: str) -> tuple[str, str] | None:
    title = _clean_text(str(offer.get("title") or offer.get("position_name") or ""))
    if not title or not looks_like_job_title(title):
        if not title or not re.search(r"m/w/d|ausbildung|praktikum|trainee", title, re.I):
            return None

    description = _clean_text(str(offer.get("description") or offer.get("description_html") or ""))
    location = _clean_text(str(offer.get("location") or offer.get("city") or ""))
    department = _clean_text(str(offer.get("department") or ""))
    employment = _clean_text(str(offer.get("employment_type") or offer.get("employmentType") or ""))

    offer_slug = str(offer.get("slug") or offer.get("id") or _slugify(title)).strip()
    detail_url = f"https://{slug}.recruitee.com/o/{offer_slug}"

    lines = [title]
    if location:
        lines.append(f"Standort: {location}")
    if department:
        lines.append(f"Bereich: {department}")
    if employment:
        lines.append(f"Beschäftigungsart: {employment}")
    if description:
        lines.append(description[:4000])

    return f"{detail_url}#job-{_slugify(title)}", "\n".join(lines)


def fetch_recruitee_offers(client: httpx.Client, slug: str) -> list[tuple[str, str]]:
    api_url = f"https://{slug}.recruitee.com/api/offers/"
    try:
        response = client.get(api_url, timeout=15.0, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        log.debug("Recruitee API failed for %s: %s", slug, exc)
        return []

    offers = payload.get("offers") if isinstance(payload, dict) else payload
    if not isinstance(offers, list):
        return []

    jobs: list[tuple[str, str]] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        job = _offer_to_job(offer, slug, api_url)
        if job:
            jobs.append(job)
    if jobs:
        log.info("Recruitee API returned %s jobs for slug %s", len(jobs), slug)
    return jobs


def extract_recruitee_content(
    client: httpx.Client,
    html: str,
    page_url: str,
) -> tuple[list[tuple[str, str]], str]:
    if not is_recruitee_page(html):
        return [], ""

    for slug in discover_recruitee_slugs(html, page_url):
        jobs = fetch_recruitee_offers(client, slug)
        if jobs:
            return jobs, f"Recruitee Karriereseite ({slug}.recruitee.com)"

    company_match = RTWIDGET_COMPANIES_RE.search(html)
    if company_match:
        log.debug("Recruitee widget company id %s found but no public slug resolved", company_match.group(1))

    return [], ""
