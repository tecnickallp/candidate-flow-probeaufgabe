from __future__ import annotations

import logging
import re

import config

log = logging.getLogger(__name__)

JOB_BOARD_WAIT_SELECTORS = (
    '[data-pattern="o-job-board"] a',
    ".o-job-board a",
    ".o-job-board [class*='title']",
    ".o-job-board table tr",
)


def _wait_for_job_board_content(page) -> None:
    for selector in JOB_BOARD_WAIT_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=8000)
            return
        except Exception:  # noqa: BLE001
            continue
    try:
        page.wait_for_function(
            """() => {
                const root = document.querySelector('[data-pattern="o-job-board"], .o-job-board');
                if (!root) return false;
                const text = root.innerText || '';
                return /m\\s*\\/\\s*w\\s*\\/\\s*d|ausbildung|praktikum|trainee/i.test(text)
                    && !/Verbindung zur Stellenb.rse ein Fehler/i.test(text);
            }""",
            timeout=8000,
        )
    except Exception:  # noqa: BLE001
        page.wait_for_timeout(2500)


def fetch_rendered_html(
    url: str,
    *,
    expect_job_board: bool = False,
    force: bool = False,
) -> str | None:
    """Optional headless-browser fallback for JS-heavy sites (React, Vue, Angular, …)."""
    if not force and not config.USE_PLAYWRIGHT_FALLBACK:
        return None

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright not installed — browser fallback skipped")
        return None

    timeout_ms = config.PLAYWRIGHT_TIMEOUT_SECONDS * 1000
    browser_headers = {
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    extra_http_headers=browser_headers,
                )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if expect_job_board or re.search(r"stellenb.o.rse|job-board|jobboard", url, re.I):
                    _wait_for_job_board_content(page)
                else:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    page.wait_for_timeout(1500)
                return page.content()
            finally:
                browser.close()
    except PlaywrightTimeoutError:
        log.warning("Playwright timeout for %s", url)
    except Exception as exc:  # noqa: BLE001
        log.warning("Playwright failed for %s: %s", url, exc)
    return None
