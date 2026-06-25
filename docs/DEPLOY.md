# Deployment (Probeaufgabe)

Die App ist eine **Flask-Python-Anwendung** mit Hintergrund-Jobs (Website-Crawl, LLM-Extraktion).  
Sie lässt sich **nicht** auf GitHub Pages hosten — dafür brauchst du einen kleinen Cloud-Server.

**Empfehlung:** [Render](https://render.com) (kostenloser Tier, einfach, kein Docker nötig).  
Alternative: [Railway](https://railway.app) (gleicher `Procfile`, ähnlicher Ablauf).

---

## Warum kein `.exe`?

Deine Sorge ist berechtigt: Selbst gebundelte Python-Apps (PyInstaller, cx_Freeze) werden von Antivirus-Software oft als verdächtig eingestuft, weil sie Code packen und entpacken. Für eine **Web-Probeaufgabe** ist ein **öffentlicher Link** außerdem deutlich professioneller:

- Reviewer klicken einfach auf die URL — kein Download, kein Windows-Warnhinweis
- Funktioniert auf Mac, Tablet, Handy
- Entspricht dem Produkt (Web-App)

---

## Voraussetzungen

1. **GitHub-Account** und Repo mit diesem Code
2. **Render-Account** (kostenlos, Login mit GitHub)
3. Optional aber empfohlen: **Supabase** (kostenloser Tier) für persistente Datenbank
4. Optional: **OpenAI-/Anthropic-/Gemini-API-Key** für bessere Extraktion (sonst Heuristik-Fallback)

---

## Schritt 1: Supabase einrichten (empfohlen)

Ohne Supabase nutzt die App SQLite auf dem Server — auf Render ist der Speicher **flüchtig** (Daten gehen bei Neustart/Deploy verloren). Für die Probeaufgabe mit DB-Anforderung ist Supabase die saubere Lösung.

1. [supabase.com](https://supabase.com) → neues Projekt anlegen
2. Im SQL-Editor den Inhalt von `supabase/schema.sql` ausführen
3. Unter **Project Settings → API** notieren:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` Key → `SUPABASE_SERVICE_ROLE_KEY`  
     (Nur serverseitig verwenden, nie im Frontend oder Git committen.)

---

## Schritt 2: Code auf GitHub pushen

```bash
git init
git add .
git commit -m "Candidate Flow Lead-Enrichment Tool"
git branch -M main
git remote add origin https://github.com/tecnickallp/candidate-flow-probeaufgabe.git
git push -u origin main
```

Stelle sicher, dass `.env` **nicht** committed wird (steht bereits in `.gitignore`).

---

## Schritt 3: Auf Render deployen

### Variante A — Blueprint (schnellste)

1. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint**
2. GitHub-Repo verbinden und `render.yaml` bestätigen
3. Unter **Environment** die Secrets setzen (siehe unten)
4. **Deploy** abwarten (~2–5 Minuten)
5. URL lautet z. B. `https://candidate-flow-analyzer.onrender.com`

### Variante B — Manuell

1. **New → Web Service**
2. Repo auswählen
3. Einstellungen:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:**  
     `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120`
   - **Health Check Path:** `/health`
4. Environment-Variablen setzen → Deploy

---

## Schritt 4: Environment-Variablen

| Variable | Pflicht | Beschreibung |
|----------|---------|--------------|
| `SUPABASE_URL` | Empfohlen | Supabase Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Empfohlen | Service-Role-Key (serverseitig) |
| `OPENAI_API_KEY` | Optional | Für LLM-Extraktion (Provider `openai`) |
| `ANTHROPIC_API_KEY` | Optional | Wenn `LLM_PROVIDER=anthropic` |
| `GEMINI_API_KEY` | Optional | Wenn `LLM_PROVIDER=gemini` |
| `LLM_PROVIDER` | Optional | Default: `openai` |
| `USE_HEURISTIC_FALLBACK` | Optional | Default: `true` — funktioniert ohne API-Key |
| `MASTER_ENCRYPTION_KEY` | Optional | Nur nötig, wenn Reviewer Keys über `/settings` speichern sollen |

Encryption-Key erzeugen:

```bash
python scripts/generate_encryption_key.py
```

Ausgabe in Render als `MASTER_ENCRYPTION_KEY` eintragen.

**Minimal-Setup zum Testen:** Nur `USE_HEURISTIC_FALLBACK=true` — die App läuft ohne API-Key und ohne Supabase (SQLite, flüchtig).

**Setup für Abgabe:** Supabase + mindestens ein LLM-Key.

---

## Schritt 5: Testen

1. Öffne die Render-URL im Browser
2. Firmenname + Website-URL eingeben → **Analyse starten**
3. Ergebnisseite prüfen
4. In Supabase: Tabelle `analyses` sollte einen neuen Eintrag haben

**Hinweis Free Tier:** Render schläft nach ~15 Min Inaktivität ein. Der erste Request danach dauert 30–60 Sekunden (Cold Start).

---

## Railway (Alternative)

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Render erkennt Python automatisch; `Procfile` wird genutzt
3. Gleiche Environment-Variablen wie oben setzen
4. Unter **Settings → Networking** öffentliche Domain generieren

---

## Was du an Candidate Flow schickst

In der E-Mail zur Probeaufgabe reicht z. B.:

```
Live-Demo: https://candidate-flow-analyzer.onrender.com
GitHub:    https://github.com/tecnickallp/candidate-flow-probeaufgabe

Lokal starten:
  python -m venv .venv
  .venv\Scripts\activate        # Windows
  pip install -r requirements.txt
  copy .env.example .env        # Keys eintragen
  python app.py                 # http://localhost:8000
```

---

## Troubleshooting

| Problem | Lösung |
|---------|--------|
| Deploy schlägt fehl | Render-Logs prüfen; Python-Version in `runtime.txt` |
| Analyse hängt / Timeout | Free Tier Cold Start abwarten; `timeout 120` in Gunicorn ist gesetzt |
| „LLM-API-Key nicht konfiguriert“ | `OPENAI_API_KEY` setzen oder `USE_HEURISTIC_FALLBACK=true` |
| Daten verschwinden | Supabase konfigurieren (SQLite auf Render ist nicht persistent) |
| Jobs doppelt / verloren | `--workers 1` beibehalten (mehrere Worker = getrennte Job-Queues) |

---

## Lokale Entwicklung vs. Produktion

| | Lokal | Render |
|---|-------|--------|
| Start | `python app.py` | Gunicorn via `Procfile` |
| Port | 8000 | `$PORT` (von Render gesetzt) |
| Debug | an | aus |
| DB | SQLite in `data/` oder Supabase | Supabase empfohlen |
