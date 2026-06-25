from __future__ import annotations

import logging

import config

log = logging.getLogger(__name__)


def fetch_rendered_html(url: str) -> str | None:
    """Optional headless-browser fallback for JS-heavy sites (React, Vue, Angular, …)."""
    if not config.USE_PLAYWRIGHT_FALLBACK:
        return None

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright not installed — browser fallback skipped")
        return None

    timeout_ms = config.PLAYWRIGHT_TIMEOUT_SECONDS * 1000
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=config.USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.wait_for_timeout(1500)
                return page.content()
            finally:
                browser.close()
    except PlaywrightTimeoutError:
        log.warning("Playwright timeout for %s", url)
    except Exception as exc:  # noqa: BLE001
        log.warning("Playwright failed for %s: %s", url, exc)
    return None
