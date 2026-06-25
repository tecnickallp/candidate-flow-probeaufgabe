from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

import config
from services.benefits_parser import extract_benefits_from_html
from services.job_validation import (
    has_job_signal,
    is_junk_job_link,
    is_listing_page,
    is_non_job_page,
    looks_like_job_title,
    score_job_link,
)

CAREER_PATHS = [
    "/karriere", "/jobs", "/careers", "/stellen", "/offene-stellen",
    "/career", "/join-us", "/work-with-us", "/jobboerse", "/stellenangebote",
]

CAREER_KEYWORDS = re.compile(
    r"karriere|career|jobs?|stellen|offene\s+stellen|work\s+with\s+us|join\s+us|jobboerse",
    re.I,
)


@dataclass
class CrawlResult:
    homepage_text: str = ""
    career_page_url: str | None = None
    career_text: str = ""
    job_pages: list[tuple[str, str]] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    combined_text: str = ""


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _same_domain(base: str, link: str) -> bool:
    return urlparse(base).netloc.replace("www.", "") == urlparse(link).netloc.replace("www.", "")


def fetch_page(client: httpx.Client, url: str) -> str:
    response = client.get(url, follow_redirects=True, timeout=15.0)
    response.raise_for_status()
    return response.text


def url_exists(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.head(url, follow_redirects=True, timeout=10.0)
        if response.status_code < 400:
            return str(response.url)
    except httpx.HTTPError:
        pass
    try:
        response = client.get(url, follow_redirects=True, timeout=10.0)
        if response.status_code < 400:
            return str(response.url)
    except httpx.HTTPError:
        return None
    return None


def html_to_text(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


def find_career_url(client: httpx.Client, base_url: str, homepage_html: str) -> str | None:
    soup = BeautifulSoup(homepage_html, "html.parser")
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    link_candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        label = anchor.get_text(" ", strip=True)
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        if not _same_domain(base_url, full) or is_non_job_page(full, label):
            continue
        if CAREER_KEYWORDS.search(label) or CAREER_KEYWORDS.search(href):
            score = 2
            if has_job_signal(full, label):
                score += 1
            link_candidates.append((score, full))

    if link_candidates:
        link_candidates.sort(key=lambda x: x[0], reverse=True)
        for _, candidate in link_candidates:
            resolved = url_exists(client, candidate)
            if resolved:
                return resolved

    for path in CAREER_PATHS:
        candidate = urljoin(origin + "/", path.lstrip("/"))
        resolved = url_exists(client, candidate)
        if resolved and not is_non_job_page(resolved):
            return resolved
    return None


def _normalize_job_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").lower()).strip()


def _append_benefits_block(page_text: str, benefits: list[str]) -> str:
    if not benefits:
        return page_text
    block = "=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===\n" + "\n".join(f"- {b}" for b in benefits)
    return f"{page_text}\n\n{block}" if page_text else block


def extract_embedded_job_detail_links(career_html: str, career_url: str) -> list[tuple[str, str]]:
    """Resolve JS-only job tiles (e.g. Divi et_link_options_data) to detail page URLs."""
    links: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    match = re.search(r"var\s+et_link_options_data\s*=\s*(\[.*?\])\s*;", career_html, re.S)
    if match:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            data = []
        soup = BeautifulSoup(career_html, "html.parser")
        for item in data:
            class_name = item.get("class") or ""
            url = (item.get("url") or "").strip()
            if "blurb" not in class_name or not url or url.startswith("#"):
                continue
            full_url = urljoin(career_url, url)
            if is_junk_job_link(full_url) or not _same_domain(career_url, full_url):
                continue
            blurb = soup.select_one(f".{class_name}")
            title = ""
            if blurb:
                heading = blurb.find(["h3", "h4", "h5"])
                title = heading.get_text(" ", strip=True) if heading else ""
            if not title or not looks_like_job_title(title):
                continue
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            links.append((title, full_url))

    for anchor in BeautifulSoup(career_html, "html.parser").find_all("a", href=True):
        href = urljoin(career_url, anchor["href"].strip())
        label = anchor.get_text(" ", strip=True)
        if not label or not looks_like_job_title(label):
            continue
        if is_junk_job_link(href) or not _same_domain(career_url, href):
            continue
        if not re.search(r"bewerb|lp[-_]|/job/|/stelle/", href, re.I):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)
        links.append((label, href))

    return links


def _upsert_job_detail(
    job_pages: list[tuple[str, str]],
    title: str,
    detail_url: str,
    page_text: str,
) -> None:
    key = _normalize_job_title(title)
    for index, (_, text) in enumerate(job_pages):
        existing_title = text.split("\n", 1)[0]
        if _normalize_job_title(existing_title) == key:
            job_pages[index] = (detail_url, page_text)
            return
    job_pages.append((detail_url, page_text))


def find_job_links(base_url: str, career_url: str, career_html: str, limit: int = 8) -> list[str]:
    soup = BeautifulSoup(career_html, "html.parser")
    scored: dict[str, int] = {}

    for title, href in extract_embedded_job_detail_links(career_html, career_url):
        if is_junk_job_link(href):
            continue
        score = score_job_link(href, title, career_url) + 4
        scored[href] = max(scored.get(href, 0), score)

    for anchor in soup.find_all("a", href=True):
        href = urljoin(career_url, anchor["href"].strip())
        label = anchor.get_text(" ", strip=True)
        if not label or not _same_domain(base_url, href):
            continue
        if href.rstrip("/") == career_url.rstrip("/"):
            continue
        if is_junk_job_link(href):
            continue

        score = score_job_link(href, label, career_url)
        if score >= 2:
            scored[href] = max(scored.get(href, 0), score)

    ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
    return [url for url, _ in ranked[:limit]]


def extract_job_entries_from_text(text: str, source_url: str) -> list[tuple[str, str]]:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    entries: list[tuple[str, str]] = []
    seen_titles: set[str] = set()

    for i, line in enumerate(lines):
        if not looks_like_job_title(line):
            continue
        key = line.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        context_lines = [line]
        for follow in lines[i + 1 : i + 6]:
            if looks_like_job_title(follow):
                break
            if follow.lower().startswith(("jetzt bewerben", "kontakt", "social media")):
                break
            if len(follow) > 15 and not is_non_job_page("", follow):
                context_lines.append(follow)
        body = "\n".join(context_lines)
        slug = re.sub(r"[^a-z0-9]+", "-", line.lower())[:48].strip("-")
        entries.append((f"{source_url}#job-{slug}", body))

    return entries


def _append_unique_jobs(target: list[tuple[str, str]], entries: list[tuple[str, str]]) -> None:
    existing = {text.split("\n", 1)[0].lower() for _, text in target}
    for url, text in entries:
        title = text.split("\n", 1)[0].lower()
        if title not in existing:
            target.append((url, text))
            existing.add(title)


def crawl_website(website_url: str, progress_callback=None) -> CrawlResult:
    website_url = normalize_url(website_url)
    result = CrawlResult()
    headers = {"User-Agent": config.USER_AGENT}

    with httpx.Client(headers=headers) as client:
        if progress_callback:
            progress_callback("fetch_homepage")
        homepage_html = ""
        try:
            homepage_html = fetch_page(client, website_url)
            result.homepage_text = html_to_text(homepage_html)
        except httpx.HTTPError:
            result.homepage_text = ""

        if progress_callback:
            progress_callback("fetch_career")
        career_url = None
        if homepage_html:
            career_url = find_career_url(client, website_url, homepage_html)
        if not career_url:
            parsed = urlparse(website_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            for path in CAREER_PATHS:
                candidate = urljoin(origin + "/", path.lstrip("/"))
                resolved = url_exists(client, candidate)
                if resolved and not is_non_job_page(resolved):
                    career_url = resolved
                    break
        result.career_page_url = career_url

        career_html = ""
        if career_url:
            try:
                career_html = fetch_page(client, career_url)
                result.career_text = html_to_text(career_html)
                _append_unique_jobs(
                    result.job_pages,
                    extract_job_entries_from_text(result.career_text, career_url),
                )
            except httpx.HTTPError:
                result.career_text = ""

        if progress_callback:
            progress_callback("fetch_jobs")
        if career_html and career_url:
            embedded_jobs = extract_embedded_job_detail_links(career_html, career_url)
            fetched_urls: set[str] = set()
            max_detail_fetches = config.MAX_CRAWL_PAGES

            def _fetch_job_detail(job_url: str, job_title: str = "") -> None:
                if job_url in fetched_urls or len(fetched_urls) >= max_detail_fetches:
                    return
                if is_junk_job_link(job_url) or is_non_job_page(job_url, job_title):
                    return
                fetched_urls.add(job_url)
                try:
                    page_html = fetch_page(client, job_url)
                    page_text = html_to_text(page_html, 8000)
                    page_benefits = extract_benefits_from_html(page_html)
                except httpx.HTTPError:
                    return

                page_text = _append_benefits_block(page_text, page_benefits)
                title = job_title or next(
                    (ln for ln in page_text.split("\n") if looks_like_job_title(ln)),
                    page_text.split("\n", 1)[0].strip(),
                )
                if looks_like_job_title(title):
                    body = page_text if page_text.startswith(title) else f"{title}\n{page_text}"
                    _upsert_job_detail(result.job_pages, title, job_url, body)
                    return

                if is_listing_page(job_url) or extract_job_entries_from_text(page_text, job_url):
                    _append_unique_jobs(
                        result.job_pages,
                        extract_job_entries_from_text(page_text, job_url),
                    )
                elif has_job_signal(job_url, page_text.split("\n", 1)[0]):
                    result.job_pages.append((job_url, page_text))

            for title, job_url in embedded_jobs:
                _fetch_job_detail(job_url, title)

            job_urls = find_job_links(website_url, career_url, career_html)
            for job_url in job_urls:
                _fetch_job_detail(job_url)

        seen_benefits: set[str] = set()
        for source_html in (homepage_html, career_html):
            if not source_html:
                continue
            for benefit in extract_benefits_from_html(source_html):
                key = benefit.lower()
                if key not in seen_benefits:
                    seen_benefits.add(key)
                    result.benefits.append(benefit)

        for url, text in result.job_pages:
            if "=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===" not in text:
                continue
            block = text.split("=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===", 1)[1]
            for line in block.split("\n"):
                line = line.strip().lstrip("-").strip()
                if not line:
                    continue
                key = line.lower()
                if key not in seen_benefits:
                    seen_benefits.add(key)
                    result.benefits.append(line)

    parts = [f"=== HOMEPAGE ===\n{result.homepage_text}"]
    if result.career_text:
        parts.append(f"=== KARRIERE ({result.career_page_url}) ===\n{result.career_text}")
    for url, text in result.job_pages:
        parts.append(f"=== STELLE ({url}) ===\n{text}")
    if result.benefits:
        parts.append("=== BENEFITS ===\n" + "\n".join(result.benefits))
    result.combined_text = "\n\n".join(parts)[:50000]
    return result
