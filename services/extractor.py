from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

import config
from models.analysis import AnalysisResult, JobListing
from services.secrets_store import get_api_key
from services.job_validation import is_plausible_job, looks_like_job_title

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

Firmenname: {company_name}
Website: {website_url}

Text:
{text}
"""


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, company_name: str, website_url: str, text: str) -> AnalysisResult:
        raise NotImplementedError


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

        benefits = _benefits_from_text(text)
        if not benefits:
            for phrase in [
                "homeoffice", "flexible arbeitszeiten", "weiterbildung", "team-events",
                "betriebliche altersvorsorge", "urlaub", "firmenwagen", "kita", "bonus",
            ]:
                if phrase in lower:
                    benefits.append(phrase.capitalize())
        if not benefits:
            benefits = ["Attraktives Arbeitsumfeld", "Teamorientierte Kultur"]

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
            tasks = [ln for ln in lines[1:10] if len(ln) > 12 and not ln.startswith("=== STELLE") and not re.search(r"@|tel:", ln, re.I)][:5]
            if not is_plausible_job(title, tasks, job_url):
                continue
            if not tasks:
                tasks = ["Aufgaben gemäß Stellenbeschreibung auf der Karriereseite"]
            jobs.append(JobListing(title=title, tasks=tasks, employer_benefits=benefits[:3]))

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
            company_name=company_name, website_url=website_url, text=text[:20000]
        )
        try:
            response = client.converse(
                modelId=config.AWS_BEDROCK_MODEL_ID,
                system=[{"text": "Du extrahierst strukturierte Recruiting-Daten. Antworte nur mit JSON."}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.2},
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "ClientError")
            message = exc.response.get("Error", {}).get("Message", str(exc))
            raise RuntimeError(f"AWS Bedrock ({code}): {message}") from exc
        except BotoCoreError as exc:
            raise RuntimeError(f"AWS Bedrock: {exc}") from exc

        raw = response["output"]["message"]["content"][0]["text"]
        try:
            payload = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
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
    return raw


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
                employer_benefits=item.get("employer_benefits") or [],
            )
        )
    return AnalysisResult(
        company_name=company_name,
        website_url=website_url,
        industry=payload.get("industry") or "",
        benefits=payload.get("benefits") or [],
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
