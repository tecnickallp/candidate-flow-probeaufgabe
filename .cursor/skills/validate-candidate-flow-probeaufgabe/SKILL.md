---
name: validate-candidate-flow-probeaufgabe
description: >-
  Prüft, ob das Lead-Enrichment Mini-Tool die Candidate-Flow-Probeaufgabe erfüllt
  (Landingpage-Design, Ladebildschirm, Website-Analyse/Agent, Ergebnisseite,
  Datenbank-Speicherung, E-Mail an artur.b@candidate-flow.de). Nutzen bei Review,
  Audit, Abnahme oder wenn der User fragt, ob die Anforderungen erfüllt sind.
---

# Candidate Flow Probeaufgabe – Anforderungsprüfung

Systematische Abnahme eines **Lead-Enrichment Mini-Tools** gegen die offizielle Probeaufgabe.
Ergebnis ist ein strukturierter Prüfbericht mit Status pro Anforderung.

## Original-Anforderungen (wörtlich)

> **Das Ziel der Aufgabe:**
> Wir haben das Onboarding für unsere Kunden (vom Handwerksbetrieb bis zum Mittelständler) auf unter 7 Minuten verkürzt. Dafür brauchten wir maximale Automatisierung bei der Datenerfassung. Deine Aufgabe ist es, einen Teil davon zu bauen – also ein „Lead-Enrichment Mini-Tool“, welches für einen Handwerker ohne großes technisches Know-How intuitiv nutzbar ist.
>
> **Deine Aufgabe im Detail:**
> Baue eine kleine Web-Applikation (Frontend + Backend/Automatisierung), idealerweise mit Claude Code oder anderen dir bekannten Tools, die folgende Anforderungen erfüllt:
>
> **Das Frontend (Candidate Flow Design):**
> Erstelle eine simple Landingpage, die sich exakt am Design von candidate-flow.de orientiert (Farben, Fonts, Look & Feel). Die Seite soll nur eine kurze, knackige Headline haben und ein Eingabefeld für einen Firmennamen sowie eine Website-URL.
> Wichtig: Wenn der User auf „Analyse starten“ klickt, soll ein futuristischer Ladebildschirm erscheinen, in dessen Mitte das Candidate Flow Logo integriert ist.
>
> **Die Daten-Extraktion (Backend/Agent):**
> Während der Ladebildschirm läuft, soll im Hintergrund die angegebene Website analysiert werden, inklusive Karriere-Seite. Extrahiere alle relevanten Firmendaten, also Branche, Benefits und Vibe/Tonalität, sowie aktuell ausgeschriebene Stellen mit Aufgaben und Arbeitgebervorteilen der Stelle.
>
> **Die Ergebnisseite & Speicherung:**
> Nach der Analyse soll eine Ergebnisseite die gefundenen Daten strukturiert und logisch aufbereitet anzeigen. Die extrahierten Daten müssen im Hintergrund in einer Datenbank (z. B. Supabase, Firebase, Airtable o. ä.) gespeichert werden, damit wir später damit weiterarbeiten können.
>
> **Die E-Mail-Automatisierung:**
> Sobald die Analyse abgeschlossen und gespeichert ist, soll automatisch an die E-Mail-Adresse artur.b@candidate-flow.de gesendet werden, die zusammenfasst, dass ein neuer Lead erfolgreich erfasst wurde. Dieses Tool soll später nicht verwendet werden, es dient lediglich der Probeaufgabe.

## Kontext für die Bewertung

| Aspekt | Erwartung |
|--------|-----------|
| **Produkt** | Lead-Enrichment Mini-Tool (Teil des Kunden-Onboardings) |
| **Zielgruppe** | Handwerker / Mittelständler ohne technisches Know-How |
| **UX** | Intuitiv: Firmenname + URL eingeben → Analyse → Ergebnis |
| **E-Mail** | Nur Probeaufgabe – Bestätigung an `artur.b@candidate-flow.de` |

## Prüfablauf

1. **Projekt erkunden** – Struktur, Stack, Entry-Points (`app.py`, `main.py`, `package.json`, etc.)
2. **Code-Suche** – Siehe [Suchhinweise](#suchhinweise) unten
3. **Laufzeit prüfen** (wenn möglich) – App starten, Flow durchspielen
4. **Design abgleichen** – Mit [reference-design.md](reference-design.md) und https://candidate-flow.de
5. **E-Mail prüfen** – Code-Nachweis + optional Log/Mailtrap/SMTP-Test
6. **Bericht erstellen** – Template unten ausfüllen, keine Anforderung überspringen

## Status-Kriterien

| Status | Bedeutung |
|--------|-----------|
| ✅ Erfüllt | Vollständig implementiert und nachweisbar |
| ⚠️ Teilweise | Vorhanden, aber unvollständig oder abweichend |
| ❌ Nicht erfüllt | Fehlt oder nicht funktionsfähig |
| 🔍 Nicht prüfbar | Kein Zugang / App startet nicht – Begründung angeben |

## Prüf-Checkliste

### 0. Produktkontext & UX

| ID | Kriterium | Prüfschritte |
|----|-----------|--------------|
| P1 | Lead-Enrichment Mini-Tool (nicht generische Demo-App) | Flow: Firmendaten eingeben → Analyse → angereicherte Firmendaten |
| P2 | Intuitiv für Nicht-Techniker | Klare Labels, wenig Schritte, verständliche Fehlermeldungen, kein Setup-Zwang |

### 1. Frontend – Landingpage

| ID | Kriterium | Prüfschritte |
|----|-----------|--------------|
| F1 | Design orientiert sich an candidate-flow.de | CSS/Fonts/Farben vs. Referenz (Outfit/Inter, dunkle Sektionen, Akzentfarbe, Logo) |
| F2 | Simple Landingpage (kein Feature-Bloat) | Nur Headline + Formular, keine langen Marketing-Sektionen als Kern |
| F3 | Kurze, knackige Headline | Eine dominante H1, nicht mehrere Hero-Blöcke |
| F4 | Eingabefeld Firmenname | Input mit Label/Placeholder, Validierung optional |
| F5 | Eingabefeld Website-URL | URL-Input, wird ans Backend übergeben |
| F6 | Button „Analyse starten“ | Exakter oder semantisch gleicher CTA-Text |

### 2. Frontend – Ladebildschirm

| ID | Kriterium | Prüfschritte |
|----|-----------|--------------|
| L1 | Erscheint nach Klick auf „Analyse starten“ | JS-Event → Overlay/Route/View-Wechsel |
| L2 | Futuristisches Erscheinungsbild | Animationen, Glow, Partikel, Gradient, Scan-Lines o. ä. |
| L3 | Candidate-Flow-Logo zentriert | Logo-Bild/SVG in der Mitte des Overlays |
| L4 | Läuft während Backend-Analyse | Parallel zum API-Call, nicht nur Fake-Timeout |

### 3. Backend / Agent – Daten-Extraktion

| ID | Kriterium | Prüfschritte |
|----|-----------|--------------|
| B1 | Website wird analysiert | HTTP-Fetch/Crawl der eingegebenen URL |
| B2 | Karriere-Seite einbezogen | Suche nach /karriere, /jobs, /careers, Link-Following |
| B3 | Branche extrahiert | Feld `industry` / `branche` in Response oder DB |
| B4 | Benefits extrahiert | Firmenweite Vorteile als Liste/Text |
| B5 | Vibe/Tonalität extrahiert | Stil, Sprache, Kultur-Beschreibung |
| B6 | Stellen mit Aufgaben | Job-Titel + Tasks/Responsibilities pro Stelle |
| B7 | Stellen mit Arbeitgebervorteilen | Job-spezifische Benefits pro Stelle |
| B8 | Läuft im Hintergrund während Loading | Async Endpoint, Frontend wartet auf Completion |

### 4. Ergebnisseite & Speicherung

| ID | Kriterium | Prüfschritte |
|----|-----------|--------------|
| R1 | Dedizierte Ergebnisseite | Route/Template nach Analyse (nicht nur JSON in Konsole) |
| R2 | Strukturierte Darstellung | Sektionen: Firma, Branche, Benefits, Vibe, Stellenliste |
| R3 | Logische Aufbereitung | Lesbar, gruppiert, nicht roher HTML-Dump |
| R4 | Persistente Speicherung | Echter DB-/BaaS-Client, kein nur In-Memory |
| R5 | Alle extrahierten Felder gespeichert | Insert/Upsert mit vollständigem Analyse-Objekt |
| R6 | Nachweisbarer DB-Zugriff | Env-Vars, SDK-Import, Migration/Schema, oder erfolgreicher Test-Insert |

### 5. E-Mail-Automatisierung

| ID | Kriterium | Prüfschritte |
|----|-----------|--------------|
| E1 | E-Mail wird automatisch versendet | Trigger nach erfolgreicher Analyse + Speicherung (nicht manuell) |
| E2 | Empfänger ist artur.b@candidate-flow.de | Hardcoded oder per Env, muss exakt diese Adresse sein |
| E3 | Inhalt: neuer Lead erfolgreich erfasst | Zusammenfassung mit Firmenname und/oder Kerndaten des Leads |
| E4 | Versand erst nach DB-Speicherung | Reihenfolge: Analyse → Save → E-Mail (nicht vor Persistenz) |

## Suchhinweise

Im Repo gezielt suchen:

```
# Landing & Loading
Analyse starten|analyse-start|startAnalysis
loading|loader|overlay|spinner
logo|candidate-flow|candidate_flow

# Formular
company|firmenname|company_name|companyName
website|url|website_url

# Extraktion
career|karriere|jobs|scrape|crawl|extract|analyze|analyse
industry|branche|benefits|vibe|tonal|tonality|stellen|positions

# Speicherung
supabase|firebase|airtable|postgres|sqlite|mongodb|prisma|drizzle
insert|upsert|save_analysis|store

# E-Mail
artur.b@candidate-flow.de|send_mail|sendmail|smtp|resend|mailgun|ses
email|notify|notification|lead.*erfass
```

Relevante Dateitypen: `*.html`, `*.css`, `*.js`, `*.ts`, `*.tsx`, `*.py`, `.env.example`, `requirements.txt`, `package.json`.

## Laufzeit-Tests

```bash
# Python/Flask (typisch)
pip install -r requirements.txt
python app.py

# Node (falls vorhanden)
npm install && npm run dev
```

Manueller Test-Flow:
1. Landingpage öffnen → Design-Eindruck, Intuitivität (P2)
2. Firmenname + URL eingeben → „Analyse starten“
3. Ladebildschirm mit Logo sichtbar?
4. Ergebnisseite mit allen Datenfeldern?
5. DB-Eintrag prüfen (Dashboard, CLI oder Log)
6. E-Mail-Versand prüfen (Log, Mailtrap, SMTP-Console oder Mock mit Nachweis)

Test-URL-Vorschlag: eine echte Firmenseite mit Karriere-Bereich (z. B. mittelständischer Arbeitgeber).

## Bericht-Template

```markdown
# Probeaufgabe Candidate Flow – Prüfbericht

**Datum:** YYYY-MM-DD
**Projekt:** [Pfad/Repo-Name]
**Stack:** [z. B. Flask + Vanilla JS + Supabase + SMTP]

## Zusammenfassung

| Bereich | Status | Erfüllung |
|---------|--------|-----------|
| Produktkontext & UX | ✅/⚠️/❌ | X/2 |
| Frontend Landingpage | ✅/⚠️/❌ | X/6 |
| Ladebildschirm | ✅/⚠️/❌ | X/4 |
| Backend/Agent | ✅/⚠️/❌ | X/8 |
| Ergebnisseite & DB | ✅/⚠️/❌ | X/6 |
| E-Mail-Automatisierung | ✅/⚠️/❌ | X/4 |

**Gesamturteil:** ✅ Abnahmefähig / ⚠️ Mit Nacharbeit / ❌ Nicht abnahmefähig

## Detailbefunde

### Produktkontext & UX
- **P1 Lead-Enrichment:** …
- **P2 Intuitiv für Handwerker:** …

### Frontend – Landingpage
- **F1–F6:** …

### Ladebildschirm
- **L1–L4:** …

### Backend / Agent
- **B1–B8:** …

### Ergebnisseite & Speicherung
- **R1–R6:** …

### E-Mail-Automatisierung
- **E1–E4:** …

## Kritische Lücken (Priorität 1)
1. …

## Empfohlene Nacharbeiten (Priorität 2)
1. …

## Positiv hervorgehoben
- …
```

## Häufige Abweichungen

| Abweichung | Bewertung | Hinweis |
|------------|-----------|---------|
| Volle Marketing-Landing statt simple Form | ⚠️ F2 | Nur Formularbereich zählt für „simple Landingpage“ |
| Mock-Daten statt echter Crawl | ❌ B1–B7 | Harte Anforderung: echte Website-Analyse |
| In-Memory-Liste statt DB | ❌ R4 | `candidates = []` o. ä. reicht nicht |
| Logo nur als Text „CF“ | ⚠️ L3 | Logo sollte erkennbar Candidate Flow sein |
| CSS weicht stark ab (Arial, generisches Blau) | ⚠️ F1 | Design-Orientierung an candidate-flow.de fehlt |
| Analyse erst nach Loading (sequentiell) | ⚠️ B8 | UX ok, aber Loading soll während Analyse laufen |
| E-Mail nur geloggt, nicht gesendet | ⚠️ E1 | Console-Log akzeptabel nur wenn SMTP/Mail-Service fehlt und dokumentiert |
| Falscher Empfänger | ❌ E2 | Muss `artur.b@candidate-flow.de` sein |
| E-Mail vor DB-Save | ❌ E4 | Reihenfolge laut Aufgabe: erst speichern, dann mailen |
| Settings/API-Key-Setup für Enduser nötig | ⚠️ P2 | Handwerker soll ohne technisches Setup starten können |

## Zusätzliche Referenz

Design-Details, Datenmodell und E-Mail-Flow: [reference-design.md](reference-design.md)
