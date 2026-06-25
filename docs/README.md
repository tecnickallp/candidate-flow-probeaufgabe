# Candidate Flow — Lead-Enrichment Mini-Tool

Web-App zur **Arbeitgeber-Analyse**: Firmenname und Website eingeben, die App crawlt die Seite (inkl. Karriere-Bereich), extrahiert strukturierte Firmendaten und zeigt das Ergebnis an. Die Daten werden persistent gespeichert.

**Live-Demo:** [https://candidate-flow-analyzer.onrender.com](https://candidate-flow-analyzer.onrender.com)

**Weitere Docs:** [Deployment](DEPLOY.md) · [Style Guide](STYLE_GUIDE.md)

---

## Tech Stack

| Schicht | Technologie |
|---------|-------------|
| **Backend** | Python 3.12, [Flask](https://flask.palletsprojects.com/) |
| **Frontend** | Jinja2-Templates, Vanilla JavaScript, CSS (Candidate-Flow-Design) |
| **HTTP / Crawling** | [httpx](https://www.python-httpx.org/), [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/), optional [Playwright](https://playwright.dev/python/) |
| **Datenmodell** | [Pydantic](https://docs.pydantic.dev/) |
| **Datenbank** | [Supabase](https://supabase.com/) (PostgreSQL) — Fallback lokal: SQLite |
| **LLM-Extraktion** | [AWS Bedrock](https://aws.amazon.com/bedrock/) (Anthropic Claude, EU-Region) |
| **Verschlüsselung** | AES-GCM-256 (`cryptography`) für gespeicherte API-Keys |
| **Produktion** | [Gunicorn](https://gunicorn.org/), [Render](https://render.com/) (siehe `render.yaml`) |

---

## Angebundene Dienste

| Dienst | Zweck | Konfiguration |
|--------|--------|---------------|
| **Supabase** | Persistente Speicherung von Analysen, Jobs und verschlüsselten Secrets | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| **AWS Bedrock** | LLM-Extraktion über Anthropic Claude (Branche, Benefits, Vibe, Stellen) | `AWS_BEARER_TOKEN_BEDROCK`, `AWS_BEDROCK_REGION`, `AWS_BEDROCK_MODEL_ID` |
| **Render** | Hosting der Web-App (Free Tier) | Blueprint über `render.yaml` |
| **Ziel-Websites** | Gecrawlte Firmenseiten (Homepage, Karriere, Stellen) | Eingabe durch den Nutzer |

**Ohne Supabase:** Die App nutzt SQLite unter `data/app.db`. Lokal ausreichend; auf Render ist dieser Speicher **flüchtig** (Daten gehen bei Neustart verloren).

**Ohne Bedrock-Token:** Mit `USE_HEURISTIC_FALLBACK=true` (Standard in `.env.example`) läuft eine regelbasierte Extraktion — für Demos ok, für echte Analysen `AWS_BEARER_TOKEN_BEDROCK` setzen. Auf Render ist `USE_HEURISTIC_FALLBACK=false`; bei ungültiger Bedrock-JSON-Antwort greift trotzdem automatisch die Heuristik als Fallback.

**Weitere Modelle:** In `services/extractor.py` ist die Extraktion über eine gemeinsame Schnittstelle (`BaseExtractor`) angebunden. Ein zusätzliches Modell lässt sich durch eine neue Extractor-Klasse und einen Eintrag in `get_extractor()` ergänzen — ohne Änderungen am Crawl- oder Speicher-Flow.

---

## Crawling & Extraktion (stack-übergreifend)

Karriereseiten werden nicht nur als statisches HTML gelesen. Die Pipeline in `services/page_extractors.py` kombiniert mehrere Strategien und führt die Ergebnisse zusammen:

| Stufe | Strategie | Typische Stacks |
|-------|-----------|-----------------|
| 1 | **Structured Data** | JSON-LD `JobPosting` (Schema.org, viele ATS/CMS) |
| 2 | **Static HTML** | Klassisches HTML, Benefit-Kacheln (WordPress/Divi, Elementor, …) |
| 3 | **Embedded JSON** | `__NEXT_DATA__` (Next.js), `__NUXT__` (Nuxt), Vue-State, generische Job-JSON |
| 4 | **JS-Bundles** | React/Vite-SPAs — Inhalte aus `/assets/*.js` (`spa_parser.py`) |
| 5 | **Browser-Fallback** *(optional)* | Headless Chromium via Playwright für unbekannte SPAs |

Zusätzlich:

- **Detailseiten** — z. B. Divi-Klicklinks (`et_link_options_data`) oder `/bewerbung-*`-Landingpages mit Benefit-Kacheln
- **Benefits** — HTML-Kacheln (`benefits_parser.py`) werden geparst und per `merge_parsed_benefits_from_crawl()` in die Ergebnisse übernommen (semantische Deduplizierung)
- **LLM** — Bedrock extrahiert Branche, Vibe und Aufgaben; Benefits aus dem Crawl werden bevorzugt direkt gemerged

**Playwright optional aktivieren** (z. B. wenn Stufe 1–4 keine Stellen finden):

```env
USE_PLAYWRIGHT_FALLBACK=true
PLAYWRIGHT_TIMEOUT_SECONDS=25
```

Build-Command ergänzen: `pip install -r requirements.txt && playwright install chromium`

Ohne Playwright funktionieren u. a. klassische HTML-Seiten, WordPress/Divi und viele React-SPAs mit eingebetteten Job-Texten im JS-Bundle.

---

## Lokal starten

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env    # Windows — unter macOS/Linux: cp .env.example .env
# Keys in .env eintragen (optional Supabase + AWS_BEARER_TOKEN_BEDROCK)
python app.py
```

Die App läuft unter **http://localhost:8000**.

Health-Check: **http://localhost:8000/health** — zeigt Speicher-Backend (`supabase` oder `sqlite`) und Datensatz-Anzahl.

---

## Seite bedienen — Schritt für Schritt

### 1. Landingpage öffnen (`/`)

**Produktion:** [https://candidate-flow-analyzer.onrender.com](https://candidate-flow-analyzer.onrender.com)  
**Lokal:** http://localhost:8000

- Kurze Headline und Formular mit zwei Feldern:
  - **Firmenname** (z. B. „Muster GmbH“)
  - **Website-URL** (z. B. `https://beispiel.de` — `https://` wird bei Bedarf ergänzt)
- Optional: **Einstellungen** (oben rechts) für den Bedrock-Bearer-Token

### 2. Analyse starten

- Button **„Analyse starten“** klicken.
- Ein **Ladebildschirm** erscheint (Grid, Scanline, Candidate-Flow-Logo).
- Fortschritt wird live angezeigt, z. B.:
  - Website wird gescannt
  - Karriereseite wird gesucht
  - Stellenanzeigen werden geladen
  - Daten werden extrahiert
  - Ergebnisse werden gespeichert

**Hinweis Render (Free Tier):** Nach Inaktivität kann der erste Request 30–60 Sekunden dauern (Cold Start). Die Statuszeile weist darauf hin.

### 3. Hintergrund-Ablauf (automatisch)

Während der Ladebildschirm läuft, passiert im Backend:

1. **Job anlegen** — Eintrag in `analysis_jobs` (Status `queued`)
2. **Crawl** — Homepage, Karriere-Pfade (`/karriere`, `/jobs`, …), Stellen-Detailseiten; mehrstufige Inhaltserkennung (HTML, JSON, JS-Bundles)
3. **Extraktion** — AWS Bedrock (Anthropic Claude) wertet den Text aus; Heuristik als Fallback bei JSON-Fehlern
4. **Benefits-Merge** — Geparste Kacheln/Vorteile aus dem Crawl werden den Stellen zugeordnet
5. **Speichern** — Ergebnis in Tabelle `analyses`
6. **Abschluss** — Job-Status `completed`, Weiterleitung zur Ergebnisseite

Das Frontend pollt alle 1,5 Sekunden `/api/jobs/<job_id>` bis die Analyse fertig ist.

### 4. Ergebnisseite (`/results/<id>`)

Strukturierte Darstellung:

| Bereich | Inhalt |
|---------|--------|
| **Kopf** | Firmenname, Website-Link, Branche |
| **Benefits** | Firmenweite Vorteile (Liste) |
| **Vibe & Tonalität** | Kurzbeschreibung des Marken-Tons |
| **Offene Stellen** | Pro Stelle: Titel, Aufgaben, Arbeitgebervorteile |

**Neue Analyse** — Button oben rechts zurück zur Startseite.

### 5. Einstellungen (`/settings`) — optional

Für Betreiber/Reviewer, nicht für Endnutzer im Alltag:

- Bedrock-Bearer-Token verschlüsselt speichern (AES-GCM, Tabelle `encrypted_secrets`)
- Alternativ Token direkt in `.env` oder Render-Environment setzen (`AWS_BEARER_TOKEN_BEDROCK`)

### 6. Gespeicherte Daten prüfen

**Mit Supabase:** Dashboard → Table Editor → Tabellen `analyses` und `analysis_jobs`.

**Lokal (SQLite):**

```bash
python view_db.py
```

Öffnet eine Web-UI unter http://127.0.0.1:8080/ für `data/app.db`.

---

## Seiten & API (Überblick)

| Route | Beschreibung |
|-------|--------------|
| `/` | Landingpage + Analyse-Formular |
| `/results/<id>` | Ergebnisseite |
| `/settings` | Bedrock-Token-Verwaltung |
| `/styleguide` | Design-Referenz (intern) |
| `/health` | Status & Speicher-Backend |
| `POST /api/analyze` | Analyse starten → `{ job_id }` |
| `GET /api/jobs/<id>` | Job-Status & Fortschritt |
| `GET /api/analyses/<id>` | Analyse als JSON |

---

## Projektstruktur (kurz)

```
app.py                 # Flask-App, Routen
config.py              # Umgebungsvariablen
services/
  crawler.py           # Website- & Karriere-Crawl
  page_extractors.py   # Stack-übergreifende Extraktions-Pipeline
  benefits_parser.py   # Benefit-Kacheln aus HTML
  spa_parser.py        # React/Vite-Inhalte aus JS-Bundles
  browser_fetch.py     # Optional: Playwright-Rendering
  extractor.py         # Bedrock / Heuristik-Extraktion
  job_validation.py    # Stellen- & Benefit-Validierung, Deduplizierung
  job_queue.py         # Hintergrund-Jobs
  storage.py           # Supabase / SQLite
  secrets_store.py     # Verschlüsselte API-Keys
templates/             # HTML (index, results, settings, …)
static/                # CSS, JS, Logo
supabase/schema.sql    # DB-Schema für Supabase
render.yaml            # Render-Blueprint
```

---

## Typische Fehler

| Symptom | Ursache / Lösung |
|---------|------------------|
| „Server antwortet nicht“ | Render Cold Start — Seite neu laden, erneut starten |
| „Website nicht erreichbar“ | URL prüfen, Seite muss öffentlich erreichbar sein |
| „LLM-API-Key nicht konfiguriert“ | `AWS_BEARER_TOKEN_BEDROCK` in `.env` oder `/settings` setzen, oder `USE_HEURISTIC_FALLBACK=true` |
| „Ungültige JSON-Antwort vom Modell“ | Bedrock-Antwort abgeschnitten — nach Deploy greift Heuristik-Fallback; ggf. erneut analysieren |
| Keine Stellen gefunden | Seite evtl. rein clientseitig gerendert — `USE_PLAYWRIGHT_FALLBACK=true` + Chromium im Build |
| Keine Benefit-Kacheln | Detailseite/Landingpage wird nicht erreicht — Karriere-Link prüfen; bei Divi/Elementor werden Klick-URLs mitgeladen |
| Analyse dauert sehr lange | Normal bei Bedrock und vielen Stellen (1–4 Min.); Free Tier kann länger brauchen |
| Daten verschwinden nach Deploy | Supabase konfigurieren — SQLite auf Render ist flüchtig |
| „Analyse abgebrochen (Server-Neustart)“ | Deploy/Reboot während laufender Analyse — erneut starten |

---

## Produktion deployen

Schritt-für-Schritt-Anleitung: **[DEPLOY.md](DEPLOY.md)**

Kurzfassung: Repo auf GitHub → Render Blueprint (`render.yaml`) → Supabase-Schema ausführen → Environment-Variablen setzen → Live-URL testen.
