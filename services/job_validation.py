from __future__ import annotations

import re

NON_JOB_RE = re.compile(
    r"\b(über\s*uns|ueber\s*uns|about\s*us|about|kontakt|contact|impressum|"
    r"datenschutz|privacy|agb|team|news|blog|presse|standort|anfahrt|"
    r"referenzen|partner|leistungen|services|produkte|philosophie|historie|"
    r"wir\s+über|unternehmen|firmengeschichte|startseite|home|"
    r"stories|menschen|mitarbeiter\s*stories|aktuelles|"
    r"social\s*media|menü|menu)\b",
    re.I,
)

# Geschlechtsneutralitäts-Formulierungen (AGG / Gleichstellung) — starkes Signal für DE-Stellen
GENDER_INCLUSIVE_RE = re.compile(
    r"(?:"
    r"\(\s*m\s*/\s*w\s*/\s*d\s*\)|"
    r"\(\s*w\s*/\s*m\s*/\s*d\s*\)|"
    r"\(\s*d\s*/\s*m\s*/\s*w\s*\)|"
    r"\(\s*m\s*/\s*f\s*/\s*d\s*\)|"
    r"\(\s*f\s*/\s*m\s*/\s*d\s*\)|"
    r"\(\s*all\s+genders\s*\)|"
    r"\(\s*gn\s*\)|"
    r"\(\s*divers\s*\)|"
    r"\(\s*divers\s*/\s*all\s+genders\s*\)|"
    r"\bm\s*/\s*w\s*/\s*d\b|"
    r"\bw\s*/\s*m\s*/\s*d\b|"
    r"\bd\s*/\s*m\s*/\s*w\b|"
    r"\bm\s*-\s*w\s*-\s*d\b|"
    r"\bmwd\b"
    r")",
    re.I,
)

# Fallback ohne m/w/d: Ausbildung, Praktikum etc.
JOB_TYPE_FALLBACK_RE = re.compile(
    r"\b(ausbildung|auszubildend|praktikum|werkstudent|duales\s+studium|trainee)\b",
    re.I,
)

JOB_TITLE_LINE_RE = re.compile(
    GENDER_INCLUSIVE_RE.pattern + r"|" + JOB_TYPE_FALLBACK_RE.pattern.strip("()"),
    re.I,
)

JOB_SIGNAL_RE = re.compile(
    r"stellenangebot|stellenanzeige|job(?:\s|-)?(?:id|nr)?|vacancy|vacancies|"
    r"position|ausschreibung|/jobs/|/stellen/|/karriere/|/job/|"
    + GENDER_INCLUSIVE_RE.pattern
    + r"|vollzeit|teilzeit|praktikum|ausbildung|initiativ|festanstellung|"
    r"werkstudent|fachkraft|monteur|mechaniker|techniker|kaufmann|helfer|"
    r"bewerb|apply|career|obermonteur|servicetechniker|projektleiter|bauleiter",
    re.I,
)

LISTING_PAGE_RE = re.compile(
    r"jobs-bei|stellenangebot|job-list|offene-stellen|vacancies|karriere/jobs",
    re.I,
)

CONTACT_LINE_RE = re.compile(
    r"@|mailto:|tel:|\+?\d[\d\s/().-]{7,}|info@|kontakt@",
    re.I,
)

JOB_REQUIREMENT_RE = re.compile(
    r"führerschein|fuehrerschein|driver'?s?\s*licen[cs]e|klasse\s*[abc]\d?|"
    r"\berforderlich\b|\bvoraussetzung|\bmitbringen\b|bewerbungsunterlagen|"
    r"mindestens\s+\d+\s+jahre\s+(?:berufserfahrung|erfahrung)|"
    r"(?:abgeschlossene[rn]?\s+)?(?:ausbildung|studium)\s+(?:als|im\s+bereich)|"
    r"eigenes\s+werkzeug|schwer(?:es)?\s+heben",
    re.I,
)


def is_job_requirement(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    return bool(JOB_REQUIREMENT_RE.search(text))


def filter_employer_benefits(items: list[str]) -> list[str]:
    seen: set[str] = set()
    filtered: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned or is_job_requirement(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(cleaned)
    return filtered


def has_gender_inclusive_marking(text: str) -> bool:
    return bool(GENDER_INCLUSIVE_RE.search(text))


def has_job_type_fallback(text: str) -> bool:
    return bool(JOB_TYPE_FALLBACK_RE.search(text))


def is_non_job_page(url: str, label: str = "") -> bool:
    combined = f"{url} {label}".lower()
    return bool(NON_JOB_RE.search(combined))


def has_job_signal(url: str, label: str = "") -> bool:
    combined = f"{url} {label}"
    return bool(JOB_SIGNAL_RE.search(combined))


def is_listing_page(url: str) -> bool:
    return bool(LISTING_PAGE_RE.search(url))


SECTION_HEADING_RE = re.compile(
    r"^(jobs?\s+bei|shk-jobs|stellenangebote|offene\s+stellen|karriere|unsere\s+stellen)\b",
    re.I,
)


def looks_like_job_title(line: str) -> bool:
    line = line.strip()
    if not line or len(line) < 10 or len(line) > 120:
        return False
    if SECTION_HEADING_RE.search(line):
        return False
    if is_non_job_page("", line) or CONTACT_LINE_RE.search(line):
        return False
    if "|" in line and not (has_gender_inclusive_marking(line) or has_job_type_fallback(line)):
        return False
    return has_gender_inclusive_marking(line) or has_job_type_fallback(line)


def score_job_link(url: str, label: str, career_url: str | None = None) -> int:
    if is_non_job_page(url, label):
        return -1
    score = 0
    if is_listing_page(url):
        score += 3
    if has_gender_inclusive_marking(label):
        score += 5
    elif has_job_type_fallback(label):
        score += 3
    if has_job_signal(url, label):
        score += 2
    lower_label = label.lower()
    if any(k in lower_label for k in ("bewerb", "apply", "details", "anzeige", "jetzt")):
        score += 2
    words = label.split()
    if 2 <= len(words) <= 14:
        score += 1
    if career_url:
        from urllib.parse import urlparse

        career_depth = urlparse(career_url).path.count("/")
        link_depth = urlparse(url).path.count("/")
        if link_depth > career_depth:
            score += 1
    return score


def is_plausible_job(title: str, tasks: list[str], url: str = "") -> bool:
    if not looks_like_job_title(title) and not has_job_signal(url, title):
        return False
    if is_non_job_page(url, title):
        return False
    if CONTACT_LINE_RE.search(title):
        return False
    contact_like = sum(1 for t in tasks if CONTACT_LINE_RE.search(t))
    if tasks and contact_like >= max(1, len(tasks) // 2):
        return False
    return True
