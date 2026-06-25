from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from services.benefits_parser import extract_benefits_from_html
from services.job_validation import (
    dedupe_benefits,
    looks_like_job_title,
)
from services.spa_parser import extract_spa_content, is_spa_shell

log = logging.getLogger(__name__)

JOB_TITLE_KEYS = ("title", "jobtitle", "job_title", "position", "stellentitel", "name", "label")
JOB_DESC_KEYS = ("description", "content", "body", "text", "summary", "aufgaben", "tasks")
JOB_BENEFIT_KEYS = ("benefits", "employer_benefits", "perks", "vorteile", "angebote")

EMBEDDED_JSON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("next_data", re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S | re.I)),
    ("nuxt", re.compile(r"window\.__NUXT__\s*=\s*(.+?);\s*</script>", re.S)),
    ("initial_state", re.compile(r"window\.__INITIAL_STATE__\s*=\s*(.+?);\s*</script>", re.S)),
    ("preloaded_state", re.compile(r"window\.__PRELOADED_STATE__\s*=\s*(.+?);\s*</script>", re.S)),
    ("divi_links", re.compile(r"var\s+et_link_options_data\s*=\s*(\[.*?\])\s*;", re.S)),
)


@dataclass
class PageContent:
    jobs: list[tuple[str, str]] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    text: str = ""
    sources: list[str] = field(default_factory=list)

    @property
    def job_count(self) -> int:
        return len(self.jobs)

    def merge(self, other: PageContent) -> PageContent:
        if not other.sources and other.job_count == 0 and not other.text and not other.benefits:
            return self

        jobs = list(self.jobs)
        existing_titles = {_normalize_title(text.split("\n", 1)[0]) for _, text in jobs}
        for url, text in other.jobs:
            title = text.split("\n", 1)[0]
            key = _normalize_title(title)
            if key in existing_titles:
                jobs = _upsert_richer_job(jobs, key, url, text)
            else:
                jobs.append((url, text))
                existing_titles.add(key)

        benefits = dedupe_benefits([*self.benefits, *other.benefits])
        text_parts = [part for part in (self.text, other.text) if part.strip()]
        text = "\n\n".join(text_parts)[:15000]
        sources = [*self.sources, *[source for source in other.sources if source not in self.sources]]
        return PageContent(jobs=jobs, benefits=benefits, text=text, sources=sources)


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").lower()).strip()


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:48].strip("-")
    return slug or "stelle"


def _upsert_richer_job(
    jobs: list[tuple[str, str]],
    title_key: str,
    url: str,
    text: str,
) -> list[tuple[str, str]]:
    updated: list[tuple[str, str]] = []
    replaced = False
    for existing_url, existing_text in jobs:
        existing_title = existing_text.split("\n", 1)[0]
        if _normalize_title(existing_title) != title_key:
            updated.append((existing_url, existing_text))
            continue
        if len(text) > len(existing_text):
            updated.append((url, text))
        else:
            updated.append((existing_url, existing_text))
        replaced = True
    if not replaced:
        updated.append((url, text))
    return updated


def html_to_visible_text(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


def extract_job_entries_from_text(text: str, source_url: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    entries: list[tuple[str, str]] = []
    seen_titles: set[str] = set()

    for index, line in enumerate(lines):
        if not looks_like_job_title(line):
            continue
        key = line.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        context_lines = [line]
        for follow in lines[index + 1 : index + 6]:
            if looks_like_job_title(follow):
                break
            if follow.lower().startswith(("jetzt bewerben", "kontakt", "social media")):
                break
            if len(follow) > 15:
                context_lines.append(follow)
        body = "\n".join(context_lines)
        entries.append((f"{source_url}#job-{_slugify(line)}", body))
    return entries


def _format_job_text(title: str, description: str = "", tasks: list[str] | None = None) -> str:
    lines = [title.strip()]
    if description.strip():
        lines.append(description.strip())
    for task in tasks or []:
        task = task.strip()
        if task and task not in lines:
            lines.append(task)
    return "\n".join(lines)


def _pick_string(data: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        for candidate, value in data.items():
            if candidate.lower() == key and isinstance(value, str):
                cleaned = unescape(re.sub(r"\s+", " ", value)).strip()
                if cleaned:
                    return cleaned
    return ""


def _pick_string_list(data: dict, keys: tuple[str, ...]) -> list[str]:
    for key in keys:
        for candidate, value in data.items():
            if candidate.lower() != key:
                continue
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
    return []


def _job_from_object(data: dict, source_url: str) -> tuple[str, str] | None:
    lower_keys = {key.lower() for key in data}
    if not any(key in lower_keys for key in JOB_TITLE_KEYS):
        return None
    if not any(key in lower_keys for key in (*JOB_DESC_KEYS, "tasks", "responsibilities", "qualifications")):
        return None

    title = _pick_string(data, JOB_TITLE_KEYS)
    if not title or not looks_like_job_title(title):
        return None

    description = _pick_string(data, JOB_DESC_KEYS)
    tasks = _pick_string_list(data, ("tasks", "responsibilities", "aufgaben", "activities"))
    benefits = _pick_string_list(data, JOB_BENEFIT_KEYS)
    body = _format_job_text(title, description, tasks)
    if benefits:
        body += "\n\n=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===\n"
        body += "\n".join(f"- {benefit}" for benefit in benefits)
    return f"{source_url}#job-{_slugify(title)}", body


def _looks_like_job_record(data: dict) -> bool:
    lower_keys = {key.lower() for key in data}
    return any(key in lower_keys for key in JOB_TITLE_KEYS) and any(
        key in lower_keys for key in (*JOB_DESC_KEYS, "tasks", "responsibilities", "qualifications")
    )


def _walk_json_for_jobs(value, source_url: str, found: list[tuple[str, str]], depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(value, dict):
        types = value.get("@type") or value.get("type")
        type_text = " ".join(types) if isinstance(types, list) else str(types or "")
        if "jobposting" in type_text.lower():
            job = _job_from_json_ld(value, source_url)
            if job:
                found.append(job)
        elif _looks_like_job_record(value):
            job = _job_from_object(value, source_url)
            if job:
                found.append(job)
        for nested in value.values():
            _walk_json_for_jobs(nested, source_url, found, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _walk_json_for_jobs(item, source_url, found, depth + 1)


def _job_from_json_ld(data: dict, source_url: str) -> tuple[str, str] | None:
    title = str(data.get("title") or "").strip()
    if not title or not looks_like_job_title(title):
        return None
    description = str(data.get("description") or "").strip()
    description = re.sub(r"<[^>]+>", " ", description)
    description = re.sub(r"\s+", " ", unescape(description)).strip()
    url = str(data.get("url") or source_url).strip() or source_url
    body = _format_job_text(title, description)
    return f"{url}#job-{_slugify(title)}", body


def extract_structured_data(html: str, page_url: str) -> PageContent:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[tuple[str, str]] = []
    seen_titles: set[str] = set()

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        batch: list[tuple[str, str]] = []
        _walk_json_for_jobs(payload, page_url, batch)
        for job in batch:
            title_key = _normalize_title(job[1].split("\n", 1)[0])
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            jobs.append(job)

    if not jobs:
        return PageContent()
    return PageContent(jobs=jobs, sources=["structured_data"])


def extract_embedded_json(html: str, page_url: str) -> PageContent:
    jobs: list[tuple[str, str]] = []
    text_parts: list[str] = []
    seen_titles: set[str] = set()

    for source_name, pattern in EMBEDDED_JSON_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        raw = match.group(1).strip()
        if source_name == "divi_links":
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        batch: list[tuple[str, str]] = []
        _walk_json_for_jobs(payload, page_url, batch)
        for job in batch:
            title_key = _normalize_title(job[1].split("\n", 1)[0])
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            jobs.append(job)
        if batch:
            text_parts.append(html_to_visible_text(json.dumps(payload, ensure_ascii=False)[:8000]))
            log.debug("Embedded JSON jobs via %s: %s", source_name, len(batch))

    if not jobs and not text_parts:
        return PageContent()
    return PageContent(
        jobs=jobs,
        text="\n\n".join(text_parts)[:8000],
        sources=["embedded_json"],
    )


def extract_static_html(html: str, page_url: str) -> PageContent:
    text = html_to_visible_text(html)
    jobs = extract_job_entries_from_text(text, page_url)
    benefits = extract_benefits_from_html(html)
    if not jobs and not benefits and len(text) < 80:
        return PageContent(text=text)
    sources = ["static_html"] if jobs or benefits else []
    return PageContent(jobs=jobs, benefits=benefits, text=text, sources=sources)


def extract_js_bundles(client: httpx.Client, html: str, page_url: str) -> PageContent:
    if not is_spa_shell(html) and len(html_to_visible_text(html)) >= 300:
        return PageContent()
    jobs, benefits, text = extract_spa_content(client, html, page_url)
    if not jobs and not text and not benefits:
        return PageContent()
    return PageContent(jobs=jobs, benefits=benefits, text=text, sources=["js_bundle"])


def extract_page_content(
    client: httpx.Client,
    html: str,
    page_url: str,
    *,
    allow_browser: bool = True,
) -> PageContent:
    """Stack-agnostic extraction pipeline — tries multiple strategies and merges results."""
    result = PageContent()

    for extractor in (
        lambda: extract_structured_data(html, page_url),
        lambda: extract_static_html(html, page_url),
        lambda: extract_embedded_json(html, page_url),
        lambda: extract_js_bundles(client, html, page_url),
    ):
        try:
            result = result.merge(extractor())
        except Exception as exc:  # noqa: BLE001
            log.warning("Page extractor failed for %s: %s", page_url, exc)

    needs_browser = (
        allow_browser
        and result.job_count == 0
        and (is_spa_shell(html) or len(result.text) < 300)
    )
    if needs_browser:
        from services.browser_fetch import fetch_rendered_html

        rendered = fetch_rendered_html(page_url)
        if rendered and rendered.strip() and rendered.strip() != html.strip():
            log.info("Retrying extraction with rendered HTML for %s", page_url)
            rendered_result = extract_page_content(
                client,
                rendered,
                page_url,
                allow_browser=False,
            )
            result = result.merge(rendered_result)
            if "browser" not in result.sources:
                result.sources.append("browser")

    return result
