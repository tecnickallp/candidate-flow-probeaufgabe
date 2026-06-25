# Referenz: candidate-flow.de Design & Datenmodell

## Design-Referenz (candidate-flow.de)

Orientierungspunkte für F1 (Design-Abgleich):

| Element | Erwartung |
|---------|-----------|
| **Schrift** | Outfit oder Inter (wie auf candidate-flow.de), Gewichte 400–800 |
| **Hintergrund** | Dunkle Hero-Bereiche (#0f0f0f / #161616), helle Content-Sektionen |
| **Akzentfarbe** | Orange (#ff320a) / Gold (#eadeaa) für Highlights und CTAs |
| **Primär-Button** | Abgerundet, Orange-Gradient, Hover-State |
| **Logo** | Offizielles Candidate-Flow-Logo (SVG von CDN oder lokal) |
| **Look & Feel** | Modern, premium Recruiting, subtile Glows/Gradienten |

Abweichungen dokumentieren, nicht automatisch als Fehler werten – es geht um **Orientierung**, nicht Pixel-Perfektion.

## Erwartetes Analyse-Datenmodell

Mindeststruktur für Response, Ergebnisseite und DB:

```json
{
  "company_name": "string",
  "website_url": "string",
  "industry": "string",
  "benefits": ["string"],
  "vibe": "string",
  "jobs": [
    {
      "title": "string",
      "tasks": ["string"],
      "employer_benefits": ["string"]
    }
  ],
  "analyzed_at": "ISO-8601 timestamp"
}
```

## Akzeptierte DB-Lösungen

| Service | Typische Indikatoren im Code |
|---------|------------------------------|
| Supabase | `@supabase/supabase-js`, `create_client`, `SUPABASE_URL` |
| Firebase | `firebase-admin`, `firestore`, `FIREBASE_` |
| Airtable | `airtable`, `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID` |
| PostgreSQL | `psycopg2`, `sqlalchemy`, `DATABASE_URL` |
| SQLite | Akzeptabel wenn persistente Datei + Schema für Analysen |

**Nicht akzeptabel:** Nur Python-Listen/Dicts im RAM ohne Persistenz nach Server-Neustart.

## API-Flow (Soll)

```
[Landing] --POST /api/analyze--> [Backend/Agent]
                                      |
                    +-----------------+------------------+
                    |                 |                  |
              Fetch Website    Find Career Page    LLM/Parser Extract
                    |                 |                  |
                    +-----------------+------------------+
                                      |
                              Save to Database
                                      |
                              Send E-Mail to
                         artur.b@candidate-flow.de
                                      |
[Ladebildschirm] <---- polling/SSE ----+
                                      |
                              [Ergebnisseite]
```

Frontend kann alternativ: Loading anzeigen → await fetch/poll → Redirect zu `/results/:id`.

## E-Mail-Anforderungen

| Feld | Wert |
|------|------|
| **Empfänger** | `artur.b@candidate-flow.de` (exakt) |
| **Trigger** | Nach abgeschlossener Analyse **und** erfolgreicher DB-Speicherung |
| **Inhalt** | Zusammenfassung: neuer Lead erfolgreich erfasst (Firmenname, ggf. Branche/URL) |
| **Zweck** | Nur Probeaufgabe – kein produktives Feature |

Typische Implementierungen: SMTP (`smtplib`), Resend, Mailgun, SendGrid, AWS SES.
Akzeptabel für lokale Entwicklung: Mailtrap oder Log-only mit `.env.example`-Hinweis (→ ⚠️ E1).

## Karriere-Seiten-Heuristiken

Backend sollte typische Pfade/Links prüfen:

- `/karriere`, `/jobs`, `/careers`, `/stellen`, `/offene-stellen`
- Footer-Links mit „Karriere“, „Jobs“, „Work with us“
- Subdomains: `jobs.example.com`, `careers.example.com`
