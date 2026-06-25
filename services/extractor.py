from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

import config
from models.analysis import AnalysisResult, JobListing
from services.secrets_store import get_api_key
from services.job_validation import filter_employer_benefits, is_plausible_job, looks_like_job_title

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analysiere den folgenden Website-Text eines Unternehmens.
Extrahiere strukturierte Firmendaten auf Deutsch.

Gib ausschließlich gültiges JSON zurück:
{{
  "industry": "Branche als String",
  "benefits": ["firmenweite Benefits"],
  "vibe": "Vibe/Tonalität der Marke in 2-4 Sätzen",
  "jobs": [
    {{
      "title": "Stellentitel",
      "tasks": ["Aufgabe 1", "Aufgabe 2"],
      "employer_benefits": ["Vorteil 1"]
    }}
  ]
}}

WICHTIG für jobs:
- Nur echte, aktuell ausgeschriebene Stellenanzeigen
- KEINE Über-uns-, Kontakt-, Impressum-, Team- oder Firmenseiten
- KEINE Einträge deren Aufgaben nur E-Mail/Telefon sind
- Wenn keine Stellen gefunden: "jobs": []

WICHTIG für employer_benefits (pro Stelle):
- Wenn im Text "=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===" steht: setze "employer_benefits" auf [] (werden automatisch ergänzt)
- Sonst nur echte Vorteile/Angebote (z. B. Homeoffice, Weiterbildung, Team-Events)
- KEINE Anforderungen oder Voraussetzungen (Führerschein, Berufserfahrung, Studium, "erforderlich", Qualifikationen)
- Anforderungen gehören in "tasks" oder werden weggelassen — niemals unter employer_benefits

Firmenname: {company_name}
Website: {website_url}

Text:
{text}
"""


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        raise NotImplementedError


def condense_crawl_text_for_llm(text: str, max_chars: int = 18000) -> str:
    """Reduce crawl payload for the LLM — benefits are merged from crawl separately."""
    if len(text) <= max_chars:
        return text

    parts: list[str] = []
    for section in re.split(r"(?=^=== )", text, flags=re.M):
        section = section.strip()
        if not section:
            continue
        if section.startswith("=== HOMEPAGE") or section.startswith("=== KARRIERE"):
            parts.append(section[:6000])
            continue
        if section.startswith("=== STELLE"):
            header, _, body = section.partition("\n")
            lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
            title = next((ln for ln in lines if looks_like_job_title(ln)), lines[0] if lines else "")
            benefits_marker = "=== UNSERE ANGEBOTE / BENEFITS (Stelle) ==="
            if benefits_marker in body:
                benefits_block = body.split(benefits_marker, 1)[1].split("\n=== ", 1)[0].strip()
                task_lines = [
                    ln
                    for ln in lines[1:8]
                    if ln != title
                    and not ln.startswith("=== ")
                    and benefits_marker not in ln
                    and len(ln) > 10
                ]
                condensed_body = "\n".join([title, *task_lines[:4]])
                if benefits_block:
                    condensed_body += f"\n\n{benefits_marker}\n{benefits_block[:2500]}"
            else:
                condensed_body = "\n".join(lines[:12])[:1500]
            parts.append(f"{header}\n{condensed_body}")
            continue
        if section.startswith("=== BENEFITS"):
            parts.append(section[:4000])
            continue
        parts.append(section[:2000])

    condensed = "\n\n".join(parts)
    return condensed[:max_chars]


def _normalize_job_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").lower()).strip()


def _benefits_from_job_block(chunk: str) -> list[str]:
    if "=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===" not in chunk:
        return []
    offer_block = chunk.split("=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===", 1)[1]
    benefits: list[str] = []
    for line in offer_block.split("\n"):
        line = line.strip().lstrip("-").strip()
        if line and not line.startswith("==="):
            benefits.append(line)
    return filter_employer_benefits(benefits)


def merge_parsed_benefits_from_crawl(result: AnalysisResult, crawl_text: str) -> AnalysisResult:
    block_pattern = r"=== STELLE \(([^)]+)\) ===\n([\s\S]*?)(?=\n=== STELLE \(|\n=== BENEFITS ===|\Z)"
    crawl_benefits_by_title: dict[str, list[str]] = {}

    for match in re.finditer(block_pattern, crawl_text):
        chunk = match.group(2)
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        title = next((ln for ln in lines if looks_like_job_title(ln)), "")
        if not title:
            continue
        parsed = _benefits_from_job_block(chunk)
        if parsed:
            crawl_benefits_by_title[_normalize_job_title(title)] = parsed

    for job in result.jobs:
        parsed = crawl_benefits_by_title.get(_normalize_job_title(job.title))
        if not parsed:
            continue
        merged = list(job.employer_benefits)
        seen = {benefit.lower() for benefit in merged}
        for benefit in parsed:
            if benefit.lower() not in seen:
                merged.append(benefit)
                seen.add(benefit.lower())
        job.employer_benefits = filter_employer_benefits(merged)

    company_benefits = list(result.benefits)
    company_seen = {benefit.lower() for benefit in company_benefits}
    for job in result.jobs:
        for benefit in job.employer_benefits:
            if benefit.lower() not in company_seen:
                company_benefits.append(benefit)
                company_seen.add(benefit.lower())

    result.benefits = filter_employer_benefits(company_benefits)
    return result


def _benefits_from_text(text: str) -> list[str]:
    match = re.search(r"=== BENEFITS ===\n([\s\S]*?)(?=\n=== |\Z)", text)
    if not match:
        return []
    benefits: list[str] = []
    seen: set[str] = set()
    for line in match.group(1).split("\n"):
        line = line.strip()
        if not line or line.lower() in seen:
            continue
        seen.add(line.lower())
        benefits.append(line)
    return benefits


class HeuristicExtractor(BaseExtractor):
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        lower = text.lower()
        industry = "Unbekannt"
        for label, keywords in {
            "IT & Software": ["software", "digital", "tech", "entwicklung"],
            "Handwerk": ["handwerk", "meister", "shk", "elektro"],
            "Einzelhandel": ["filiale", "retail", "supermarkt", "verkauf"],
            "Gesundheit": ["pflege", "klinik", "medizin", "health"],
            "Logistik": ["logistik", "transport", "spedition", "lager"],
        }.items():
            if any(k in lower for k in keywords):
                industry = label
                break

        benefits = filter_employer_benefits(_benefits_from_text(text))
        if not benefits:
            for phrase in [
                "homeoffice", "flexible arbeitszeiten", "weiterbildung", "team-events",
                "betriebliche altersvorsorge", "urlaub", "firmenwagen", "kita", "bonus",
            ]:
                if phrase in lower:
                    benefits.append(phrase.capitalize())
        if not benefits:
            benefits = ["Attraktives Arbeitsumfeld", "Teamorientierte Kultur"]
        benefits = filter_employer_benefits(benefits)

        vibe = (
            "Das Unternehmen kommuniziert professionell und arbeitgeberorientiert. "
            "Die Tonalität wirkt sachlich und einladend."
        )
        if "du " in lower or "dein " in lower:
            vibe += " Die Ansprache erfolgt persönlich in Du-Form."
        if "wir " in lower:
            vibe += " Teamgeist und gemeinsame Werte stehen im Vordergrund."

        jobs: list[JobListing] = []
        block_pattern = r"=== STELLE \(([^)]+)\) ===\n([\s\S]*?)(?=\n=== STELLE \(|\Z)"
        for match in re.finditer(block_pattern, text):
            job_url = match.group(1).split("#")[0]
            chunk = match.group(2)
            lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
            title = next((ln for ln in lines if looks_like_job_title(ln)), "")
            if not title:
                title = next((ln for ln in lines if 4 < len(ln) < 120 and is_plausible_job(ln, [], job_url)), "")
            if not title:
                continue
            job_benefits: list[str] = []
            if "=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===" in chunk:
                offer_block = chunk.split("=== UNSERE ANGEBOTE / BENEFITS (Stelle) ===", 1)[1]
                for ln in offer_block.split("\n"):
                    ln = ln.strip().lstrip("-").strip()
                    if ln and not ln.startswith("==="):
                        job_benefits.append(ln)
            job_benefits = filter_employer_benefits(job_benefits) or filter_employer_benefits(benefits[:5])
            tasks = [
                ln
                for ln in lines[1:10]
                if len(ln) > 12
                and not ln.startswith("=== ")
                and not re.search(r"@|tel:", ln, re.I)
            ][:5]
            if not is_plausible_job(title, tasks, job_url):
                continue
            if not tasks:
                tasks = ["Aufgaben gemäß Stellenbeschreibung auf der Karriereseite"]
            jobs.append(JobListing(title=title, tasks=tasks, employer_benefits=job_benefits))

        return AnalysisResult(
            company_name=company_name,
            website_url=website_url,
            industry=industry,
            benefits=benefits,
            vibe=vibe,
            jobs=jobs,
        )


class OpenAIExtractor(BaseExtractor):
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        from openai import OpenAI

        api_key = get_api_key("openai")
        if not api_key:
            raise RuntimeError("LLM-API-Key nicht konfiguriert")
        client = OpenAI(api_key=api_key)
        prompt = EXTRACTION_PROMPT.format(
            company_name=company_name, website_url=website_url, text=text[:30000]
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du extrahierst strukturierte Recruiting-Daten. Antworte nur mit JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return _payload_to_result(payload, company_name, website_url)


class AnthropicExtractor(BaseExtractor):
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        import anthropic

        api_key = get_api_key("anthropic")
        if not api_key:
            raise RuntimeError("LLM-API-Key nicht konfiguriert")
        client = anthropic.Anthropic(api_key=api_key)
        prompt = EXTRACTION_PROMPT.format(
            company_name=company_name, website_url=website_url, text=text[:30000]
        )
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        payload = json.loads(_extract_json(raw))
        return _payload_to_result(payload, company_name, website_url)


class BedrockExtractor(BaseExtractor):
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        import os

        api_key = get_api_key("bedrock")
        if not api_key:
            raise RuntimeError("LLM-API-Key nicht konfiguriert")
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key

        client = boto3.client(
            "bedrock-runtime",
            region_name=config.AWS_BEDROCK_REGION,
            config=Config(
                connect_timeout=15,
                read_timeout=config.JOB_TIMEOUT_SECONDS,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )
        prompt = EXTRACTION_PROMPT.format(
            company_name=company_name,
            website_url=website_url,
            text=condense_crawl_text_for_llm(text),
        )
        try:
            response = client.converse(
                modelId=config.AWS_BEDROCK_MODEL_ID,
                system=[{"text": "Du extrahierst strukturierte Recruiting-Daten. Antworte nur mit JSON."}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 8192, "temperature": 0.2},
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "ClientError")
            message = exc.response.get("Error", {}).get("Message", str(exc))
            raise RuntimeError(f"AWS Bedrock ({code}): {message}") from exc
        except BotoCoreError as exc:
            raise RuntimeError(f"AWS Bedrock: {exc}") from exc

        raw = response["output"]["message"]["content"][0]["text"]
        stop_reason = response.get("stopReason") or response.get("output", {}).get("stopReason")
        if stop_reason == "max_tokens":
            log.warning("Bedrock response truncated (max_tokens); attempting JSON repair")

        try:
            payload = _parse_model_json(raw)
        except json.JSONDecodeError as exc:
            log.warning(
                "Bedrock JSON parse failed (len=%s): %s",
                len(raw),
                raw[:300].replace("\n", " "),
            )
            if config.USE_HEURISTIC_FALLBACK:
                result = HeuristicExtractor().extract(company_name, website_url, text)
                return merge_parsed_benefits_from_crawl(result, text)
            raise RuntimeError("AWS Bedrock: Ungültige JSON-Antwort vom Modell.") from exc
        return _payload_to_result(payload, company_name, website_url)


class GeminiExtractor(BaseExtractor):
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        import google.generativeai as genai

        api_key = get_api_key("gemini")
        if not api_key:
            raise RuntimeError("LLM-API-Key nicht konfiguriert")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = EXTRACTION_PROMPT.format(
            company_name=company_name, website_url=website_url, text=text[:30000]
        )
        response = model.generate_content(prompt)
        payload = json.loads(_extract_json(response.text))
        return _payload_to_result(payload, company_name, website_url)


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _repair_truncated_json(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        return raw
    raw = raw[start:]
    raw = re.sub(r',\s*"[^"\n\\]*(?:\\.[^"\n\\]*)*$', "", raw)
    raw = re.sub(r",\s*$", "", raw)
    raw += "]" * max(0, raw.count("[") - raw.count("]"))
    raw += "}" * max(0, raw.count("{") - raw.count("}"))
    return raw


def _parse_model_json(raw: str) -> dict:
    cleaned = _extract_json(raw)
    for candidate in (cleaned, _repair_truncated_json(cleaned)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        for candidate in (match.group(0), _repair_truncated_json(match.group(0))):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("No valid JSON object in model response", cleaned, 0)


def _payload_to_result(payload: dict, company_name: str, website_url: str) -> AnalysisResult:
    jobs = []
    for item in payload.get("jobs") or []:
        title = item.get("title") or ""
        tasks = item.get("tasks") or []
        if not is_plausible_job(title, tasks):
            continue
        jobs.append(
            JobListing(
                title=title,
                tasks=tasks,
                employer_benefits=filter_employer_benefits(item.get("employer_benefits") or []),
            )
        )
    company_benefits = filter_employer_benefits(payload.get("benefits") or [])
    for job in jobs:
        for benefit in job.employer_benefits:
            if benefit.lower() not in {b.lower() for b in company_benefits}:
                company_benefits.append(benefit)
    return AnalysisResult(
        company_name=company_name,
        website_url=website_url,
        industry=payload.get("industry") or "",
        benefits=company_benefits,
        vibe=payload.get("vibe") or "",
        jobs=jobs,
    )


def get_extractor() -> BaseExtractor:
    provider = config.LLM_PROVIDER
    if provider == "openai" and get_api_key("openai"):
        return OpenAIExtractor()
    if provider == "anthropic" and get_api_key("anthropic"):
        return AnthropicExtractor()
    if provider == "gemini" and get_api_key("gemini"):
        return GeminiExtractor()
    if provider == "bedrock" and get_api_key("bedrock"):
        return BedrockExtractor()
    if config.USE_HEURISTIC_FALLBACK:
        return HeuristicExtractor()
    raise RuntimeError("LLM-API-Key nicht konfiguriert. Bitte unter /settings hinterlegen.")
