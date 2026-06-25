from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from services.job_validation import (
    dedupe_benefits,
    filter_employer_benefits,
    has_gender_inclusive_marking,
    has_job_type_fallback,
    looks_like_job_title,
)

CARD_TITLE_RE = re.compile(
    r'className:"text-(?:2|3)xl text-primary",children:"([^"]{8,140})"',
    re.I,
)
STRONG_ITEM_RE = re.compile(
    r'i\.jsx\("strong",\{children:"([^"]{3,80}:)"\}\),"?\s*"([^"]{5,400})"',
    re.S,
)
SPAN_TEXT_RE = re.compile(r'i\.jsx\("span",\{children:"([^"]{15,400})"\}\)')
SUBTITLE_RE = re.compile(r'className:"text-lg",children:"([^"]{8,200})"')

UI_NOISE_RE = re.compile(
    r"^(className|aria-|data-|opacity|transition|flex |grid |container |absolute |relative )",
    re.I,
)
SECTION_STOP_RE = re.compile(
    r"(Einblick in unseren|Dein Browser|Jetzt bewerben|Kontakt|Impressum|Datenschutz|"
    r"video/|\.mp4|type:\"video)",
    re.I,
)


def is_spa_shell(html: str) -> bool:
    if not html or len(html) < 200:
        return False
    soup = BeautifulSoup(html, "html.parser")
    visible_text = soup.get_text(" ", strip=True)
    if len(visible_text) > 500:
        return False
    has_app_root = bool(soup.find(id="root") or soup.find(id="app"))
    has_js_bundle = bool(soup.find("script", src=re.compile(r"\.js(?:\?|$)", re.I)))
    return has_app_root and has_js_bundle


def fetch_js_bundle_text(client: httpx.Client, html: str, page_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    bundles: list[str] = []
    seen: set[str] = set()

    for script in soup.find_all("script", src=True):
        src = urljoin(page_url, script["src"].strip())
        if src in seen:
            continue
        if not re.search(r"\.js(?:\?|$)", src, re.I):
            continue
        seen.add(src)
        try:
            response = client.get(src, timeout=20.0)
            response.raise_for_status()
            bundles.append(response.text)
        except httpx.HTTPError:
            continue

    return "\n".join(bundles)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:48].strip("-")
    return slug or "stelle"


def _is_jobish_title(title: str) -> bool:
    if looks_like_job_title(title):
        return True
    lower = title.lower()
    return bool(
        re.search(r"\bazubi\b|\bausbildung\b|\bauszubildend", lower)
        and has_gender_inclusive_marking(title)
    )


def _clean_js_text(text: str) -> str:
    text = text.replace('\\"', '"').strip().strip('"')
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_ui_noise(text: str) -> bool:
    if UI_NOISE_RE.search(text):
        return True
    if text.startswith("i.jsx(") or text.startswith("children:"):
        return True
    if re.search(r"^(top-|left-|right-|bottom-|sm:|md:|lg:)", text):
        return True
    return False


def _extract_strong_items(chunk: str, limit: int = 8) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for match in STRONG_ITEM_RE.finditer(chunk):
        label = _clean_js_text(match.group(1))
        rest = _clean_js_text(match.group(2))
        if SECTION_STOP_RE.search(rest):
            break
        item = f"{label} {rest}".strip()
        if len(item) < 12 or _is_ui_noise(item):
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _extract_span_items(chunk: str, limit: int = 8) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for match in SPAN_TEXT_RE.finditer(chunk):
        text = _clean_js_text(match.group(1))
        if SECTION_STOP_RE.search(text):
            break
        if len(text) < 15 or _is_ui_noise(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def _slice_between(
    chunk: str,
    start_keywords: tuple[str, ...],
    end_keywords: tuple[str, ...],
    max_len: int = 3500,
) -> str:
    start = 0
    for keyword in start_keywords:
        idx = chunk.find(keyword)
        if idx >= 0:
            start = idx
            break
    end = min(len(chunk), start + max_len)
    for keyword in end_keywords:
        idx = chunk.find(keyword, start + len(keyword) + 5)
        if idx >= 0:
            end = min(end, idx)
    return chunk[start:end]


def _extract_tasks_from_chunk(chunk: str) -> list[str]:
    section = _slice_between(
        chunk,
        ("Deine Aufgaben", "Aufgaben als Azubi", "Aufgaben:", "Deine Tätigkeiten", "Tätigkeiten:"),
        ("Anforderungen:", "Was wir bieten", "Deine Benefits", "Einblick in unseren"),
    )
    tasks = _extract_strong_items(section, limit=6)
    if len(tasks) < 2:
        tasks.extend(_extract_span_items(section, limit=6))
    seen: set[str] = set()
    unique: list[str] = []
    for task in tasks:
        key = task.lower()
        if key not in seen:
            seen.add(key)
            unique.append(task)
    return unique[:6]


def _extract_benefits_from_chunk(chunk: str) -> list[str]:
    section = _slice_between(
        chunk,
        ("Was wir bieten", "Deine Benefits", "Unsere Benefits", "Das bieten wir", "Benefits:"),
        ("Anforderungen:", "Einblick in unseren", "Dein Browser", "video/", ".mp4"),
    )
    if section == chunk[: min(len(chunk), 3500)]:
        section = _slice_between(
            chunk,
            ("Work-Life-Balance:", "Top-Ausstattung:", "Spannende Projekte:"),
            ("Einblick in unseren", "Dein Browser", "video/", ".mp4"),
        )
    benefits = _extract_strong_items(section, limit=10)
    return filter_employer_benefits(benefits)


def _find_job_title_positions(js: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    seen_titles: set[str] = set()

    for match in CARD_TITLE_RE.finditer(js):
        title = _clean_js_text(match.group(1))
        if not _is_jobish_title(title):
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        found.append((title, match.start()))

    found.sort(key=lambda item: item[1])
    return found


def extract_jobs_from_spa_js(js: str, source_url: str) -> list[tuple[str, str]]:
    if not js:
        return []

    titles = _find_job_title_positions(js)
    if not titles:
        return []

    jobs: list[tuple[str, str]] = []
    for index, (title, start) in enumerate(titles):
        end = titles[index + 1][1] if index + 1 < len(titles) else start + 7000
        chunk = js[start:end]

        subtitle_match = SUBTITLE_RE.search(chunk[:800])
        subtitle = _clean_js_text(subtitle_match.group(1)) if subtitle_match else ""
        tasks = _extract_tasks_from_chunk(chunk)
        benefits = _extract_benefits_from_chunk(chunk)

        lines = [title]
        if subtitle:
            lines.append(subtitle)
        if tasks:
            lines.extend(tasks)
        if benefits:
            lines.append("")
            lines.append("=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===")
            lines.extend(f"- {benefit}" for benefit in benefits)

        slug = _slugify(title)
        jobs.append((f"{source_url}#job-{slug}", "\n".join(lines)))

    return jobs


def extract_shared_benefits_from_spa_js(js: str) -> list[str]:
    if not js:
        return []
    karriere_idx = js.lower().find("werde teil unseres motivierten teams")
    if karriere_idx < 0:
        karriere_idx = js.lower().find('to:"/karriere"')
    search_area = js[karriere_idx : karriere_idx + 80000] if karriere_idx >= 0 else js
    benefits = _extract_benefits_from_chunk(search_area)
    return dedupe_benefits(benefits)


def spa_js_to_text(js: str) -> str:
    literals = re.findall(r'children:"([^"]{12,220})"', js)
    lines: list[str] = []
    seen: set[str] = set()
    for literal in literals:
        text = _clean_js_text(literal)
        if _is_ui_noise(text):
            continue
        if not re.search(
            r"karriere|aufgaben|anforderung|benefit|vorteil|ausbildung|azubi|metall|schwei|"
            r"m/w/d|stelle|bewerb|urlaub|bezahlung|projekt",
            text,
            re.I,
        ):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(text)
    return "\n".join(lines[:120])


def extract_spa_content(
    client: httpx.Client,
    html: str,
    page_url: str,
) -> tuple[list[tuple[str, str]], list[str], str]:
    js = fetch_js_bundle_text(client, html, page_url)
    if not js:
        return [], [], ""

    jobs = extract_jobs_from_spa_js(js, page_url)
    benefits = extract_shared_benefits_from_spa_js(js)
    text = spa_js_to_text(js)
    return jobs, benefits, text
