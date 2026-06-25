from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag

BENEFIT_SECTION_RE = re.compile(
    r"unsere?\s+angebote?|unser\s+angebot|unsere\s+benefits?|deine\s+vorteile|das\s+bieten\s+wir|"
    r"was\s+wir\s+bieten|dein\s+plus|unser\s+plus|benefits?|vorteile|"
    r"warum\s+(?:bei\s+uns|zu\s+uns|.+?arbeiten)|employee\s+benefits?",
    re.I,
)

BENEFIT_CLASS_RE = re.compile(
    r"benefit|vorteil|angebot|icon-box|feature|perk|offer|advantage|card",
    re.I,
)

SKIP_TITLE_RE = re.compile(
    r"^(jetzt\s+bewerben|mehr\s+erfahren|kontakt|social\s+media|"
    r"stellenangebote|offene\s+stellen|karriere)$",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _format_benefit(title: str, description: str | None = None) -> str | None:
    title = _clean(title)
    if not title or len(title) < 4 or len(title) > 140:
        return None
    if SKIP_TITLE_RE.match(title):
        return None
    if description:
        description = _clean(description)
        if description and description.lower() != title.lower():
            if len(description) > 220:
                description = description[:217] + "..."
            return f"{title} — {description}"
    return title


def _heading_text(tag: Tag) -> str:
    return _clean(tag.get_text(" ", strip=True))


def _title_and_desc(container: Tag) -> tuple[str, str]:
    for heading_tag in ("h2", "h3", "h4", "h5", "strong", "span"):
        heading = container.find(heading_tag, class_=re.compile(r"title|heading", re.I))
        if heading:
            title = _heading_text(heading)
            break
    else:
        heading = container.find(["h3", "h4", "h5", "strong"])
        title = _heading_text(heading) if heading else ""

    desc_el = container.find("p")
    if not desc_el:
        desc_el = container.find(class_=re.compile(r"description|text|content|subtitle", re.I))
    description = _heading_text(desc_el) if desc_el else ""
    return title, description


def _extract_from_icon_boxes(soup: BeautifulSoup) -> list[str]:
    benefits: list[str] = []
    seen: set[str] = set()

    selectors = [
        ".elementor-widget-icon-box",
        ".elementor-widget-heading + .elementor-widget-text-editor",
        "[class*='icon-box']",
        "[class*='benefit']",
        "[class*='vorteil']",
        "[class*='feature-box']",
        "[class*='offer-card']",
        "[class*='angebot']",
    ]
    for selector in selectors:
        for box in soup.select(selector):
            title, description = _title_and_desc(box)
            benefit = _format_benefit(title, description)
            if benefit and benefit.lower() not in seen:
                seen.add(benefit.lower())
                benefits.append(benefit)
    return benefits


def _extract_heading_paragraph_pairs(container: Tag) -> list[str]:
    benefits: list[str] = []
    seen: set[str] = set()

    for heading in container.find_all(["h3", "h4", "h5"]):
        title = _heading_text(heading)
        if not title or len(title) < 4:
            continue
        if BENEFIT_SECTION_RE.fullmatch(title):
            continue

        description = ""
        for sibling in heading.find_next_siblings():
            if sibling.name in ("h2", "h3", "h4", "h5"):
                break
            if sibling.name == "p":
                description = _heading_text(sibling)
                break
            if isinstance(sibling, Tag):
                paragraph = sibling.find("p")
                if paragraph:
                    description = _heading_text(paragraph)
                    break

        benefit = _format_benefit(title, description)
        if benefit and benefit.lower() not in seen:
            seen.add(benefit.lower())
            benefits.append(benefit)

    return benefits


def _find_benefit_container(heading: Tag) -> Tag | None:
    best: Tag | None = None
    best_score = 0
    node: Tag | None = heading
    for _ in range(7):
        if node is None:
            break
        icon_boxes = len(node.select(".elementor-widget-icon-box, [class*='icon-box']"))
        headings = len(node.find_all(["h3", "h4", "h5"]))
        score = icon_boxes * 3 + headings
        if score > best_score:
            best_score = score
            best = node
        node = node.parent
    return best if best_score >= 2 else None


def _extract_from_section_headings(soup: BeautifulSoup) -> list[str]:
    benefits: list[str] = []
    seen: set[str] = set()

    for heading in soup.find_all(["h1", "h2", "h3"]):
        label = _heading_text(heading)
        if not label or not BENEFIT_SECTION_RE.search(label):
            continue
        container = _find_benefit_container(heading)
        if not container:
            continue

        section_items = _extract_from_icon_boxes(
            BeautifulSoup(str(container), "html.parser")
        )
        if len(section_items) < 2:
            section_items = _extract_from_elementor_columns(container)
        if len(section_items) < 2:
            section_items = _extract_from_divi_blurbs(container)
        if len(section_items) < 1:
            section_items = _extract_heading_paragraph_pairs(container)

        for item in section_items:
            if item.lower() not in seen:
                seen.add(item.lower())
                benefits.append(item)

    return benefits


def _extract_from_elementor_columns(container: Tag) -> list[str]:
    benefits: list[str] = []
    seen: set[str] = set()

    for column in container.select(".elementor-column, .e-con-inner > .e-con"):
        title_el = column.find(["h3", "h4", "h5", "strong"])
        if not title_el:
            continue
        title = _heading_text(title_el)
        if _looks_like_job_title(title):
            continue
        desc_el = column.find("p")
        description = _heading_text(desc_el) if desc_el else ""
        benefit = _format_benefit(title, description)
        if benefit and benefit.lower() not in seen:
            seen.add(benefit.lower())
            benefits.append(benefit)

    return benefits


def _extract_from_divi_blurbs(container: Tag) -> list[str]:
    benefits: list[str] = []
    seen: set[str] = set()

    for blurb in container.select(".et_pb_blurb"):
        heading = blurb.find(["h4", "h3", "h5", "strong"])
        paragraph = blurb.find("p")
        title = _heading_text(heading) if heading else ""
        if _looks_like_job_title(title):
            continue
        description = _heading_text(paragraph) if paragraph else ""
        benefit = _format_benefit(title, description)
        if benefit and benefit.lower() not in seen:
            seen.add(benefit.lower())
            benefits.append(benefit)

    return benefits


def _looks_like_job_title(title: str) -> bool:
    lower = title.lower()
    return bool(
        re.search(r"\(m/w/d\)|\(w/m/d\)|\(gn\)|\(divers\)|m-w-d", lower)
        or re.search(r"\b(vollzeit|teilzeit|ausbildung|praktikum|werkstudent)\b", lower)
    )


def _extract_from_list_items(soup: BeautifulSoup) -> list[str]:
    benefits: list[str] = []
    seen: set[str] = set()

    for lst in soup.find_all(["ul", "ol"]):
        parent = lst.find_parent(["section", "div"])
        if not parent:
            continue
        context = _heading_text(parent.find(["h2", "h3", "h4"]) or lst.find_previous(["h2", "h3", "h4"]) or lst)
        if not BENEFIT_SECTION_RE.search(context):
            continue
        for item in lst.find_all("li", recursive=False):
            text = _clean(item.get_text(" ", strip=True))
            benefit = _format_benefit(text)
            if benefit and benefit.lower() not in seen:
                seen.add(benefit.lower())
                benefits.append(benefit)

    return benefits


def extract_benefits_from_html(html: str) -> list[str]:
    if not html or len(html) < 100:
        return []

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    collected: list[str] = []
    seen: set[str] = set()

    for extractor in (
        _extract_from_section_headings,
        _extract_from_icon_boxes,
        _extract_from_list_items,
    ):
        for item in extractor(soup):
            key = item.lower()
            if key not in seen:
                seen.add(key)
                collected.append(item)

    return collected[:25]
