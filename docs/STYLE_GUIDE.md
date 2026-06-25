# Candidate Flow – UI/UX Style Guide

Dieser Style Guide dokumentiert das aktuelle Design-System der Landingpage und dient als verbindliche Referenz für alle zukünftigen UI-Entwicklungen im Projekt.

**Visuelle Vorschau:** `/styleguide` (lokal: `http://localhost:8000/styleguide`)

**Quelle der Wahrheit:** `static/css/style.css` · Orientierung an [candidate-flow.de](https://candidate-flow.de)

---

## 1. Design-Prinzipien

| Prinzip | Umsetzung |
|---------|-----------|
| **Premium & vertrauenswürdig** | Dunkle Flächen, klare Typografie, TÜV-/Trust-Elemente |
| **Conversion-fokussiert** | Orange CTAs, subtile Hover-Animationen, klare Subline unter Buttons |
| **Markenkonsistenz** | Outfit-Schrift, Orange-Gradient, kein Blau als Primärfarbe |
| **Duale Oberflächen** | Dunkle Sektionen (Hero, Methode) + helle Sektionen (Formulare, Demo) |
| **Mobile first** | Responsive Breakpoints, volle Button-Breite auf Mobile |

---

## 2. Design Tokens

Alle Tokens sind als CSS Custom Properties in `:root` definiert. **Neue Styles immer über diese Variablen bauen**, nicht mit Hardcoded-Farben.

### 2.1 Farben

| Token | Hex | Verwendung |
|-------|-----|------------|
| `--black` | `#0f0f0f` | Primärer Seitenhintergrund, Body |
| `--grey-950` | `#161616` | Karten, Footer, erhöhte Flächen |
| `--grey-900` | `#181818` | Stats-Bar, CTA-Sektion |
| `--grey-500` | `#666666` | Borders, dezenter Text auf hellem Grund |
| `--grey-300` | `#d0d0d0` | Sekundärtext auf dunklem Grund |
| `--white` | `#ffffff` | Text auf dunkel, helle Sektionen |
| `--brand-orange` | `#ff320a` | Primär-Akzent, Fokus-Ringe, Badges |
| `--light-orange` | `#ff684d` | Gradient-Start, Hover-Akzente |
| `--gold` | `#eadeaa` | Labels, Premium-Hinweise (z. B. Garantie-Eyebrow) |

#### Gradienten

```css
/* Primär-Button & Akzent-Text */
linear-gradient(180deg, var(--light-orange), var(--brand-orange))

/* Hero-Hintergrund */
radial-gradient(circle farthest-corner at 140% -125%, var(--brand-orange), transparent 67%)

/* Garantie-Sektion */
radial-gradient(circle farthest-corner at 100% 100%, rgba(255, 50, 10, 0.15), transparent 60%)
```

#### Semantische Zuordnung

| Kontext | Hintergrund | Text primär | Text sekundär |
|---------|-------------|-------------|---------------|
| Dark Section | `--black` | `--white` | `--grey-300` |
| Light Section | `--white` | `--black` | `--grey-500` |
| Elevated Card (dark) | `--grey-950` | `--white` | `--grey-300` |
| Elevated Card (light) | `--white` | `--black` | `--grey-500` |

### 2.2 Typografie

**Schriftfamilie:** `Outfit` (Regular 400, Medium 500, SemiBold 600, Bold 700)

**Fallback-Stack:** `Outfit, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`

| Klasse | Größe | Gewicht | Letter-Spacing | Line-Height | Einsatz |
|--------|-------|---------|----------------|-------------|---------|
| `.heading-h1` | `clamp(2.25rem, 5vw, 4rem)` | 600 | -0.05em | 1.1 | Hero-Headline |
| `.heading-h2` | `clamp(1.75rem, 3.5vw, 2.75rem)` | 600 | -0.03em | 1.2 | Sektionsüberschriften |
| `.heading-h3` | `2.5rem` | 600 | -0.03em | 1.3 | Große Zwischenüberschriften |
| `.heading-h3--eyebrow` | `clamp(1.25rem, 2.5vw, 1.75rem)` | 600 | -0.03em | 1.3 | Eyebrow über H1 |
| `.heading-h3--quote` | `clamp(1.375rem, 2.5vw, 2rem)` | 600 | -0.03em | 1.35 | Testimonials |
| `.heading-h4` | `1.5rem` | 600 | — | 1.3 | Karten-Titel |
| Body (default) | `1rem` | 400 | -0.02em | 1.5 | Fließtext |
| `.text-medium` | `1.125rem` | 400 | -0.02em | 1.5 | Lead-Text |
| `.text-small-medium` | `1rem` | 400 | -0.02em | 1.5 | CTA-Subline, Trust-Text |
| `.text-small` | `0.875rem` | 400 | -0.02em | 1.5 | Footer, Meta |

#### Text-Varianten

| Klasse | Beschreibung |
|--------|--------------|
| `.text-secondary` | Sekundärfarbe (`--grey-300` auf dark, kontextabhängig) |
| `.text-muted` | Gedämpft (`--grey-500`), für helle Sektionen |
| `.text-accent` | Orange Gradient als Text (nur für kurze Highlights, z. B. „Garantiert:“) |
| `.text-accent-solid` | Orange, uppercase, für Section-Labels |
| `.text-gold` | Goldene Eyebrows / Premium-Labels |

**Du-Ansprache:** Inhalte adressieren den Nutzer mit „Du/Dein“ (Markensprache).

### 2.3 Abstände & Layout

| Token / Klasse | Wert | Verwendung |
|----------------|------|------------|
| `--container` | `84.5rem` (1352px) | Max. Content-Breite |
| `.container-large` | max-width + zentriert | Haupt-Wrapper |
| `.padding-global` | `3rem` horizontal (Mobile: `1.25rem`) | Seiten-Padding |
| `.padding-section-medium` | `4rem` vertikal | Sektions-Abstand |
| `--radius` | `0.5rem` (8px) | Buttons, Karten, Inputs |
| Nav border-radius | `1rem` | Glas-Navigation |

### 2.4 Breakpoints

| Name | Min-Width | Verhalten |
|------|-----------|-----------|
| Mobile | `< 480px` | Formulare gestapelt |
| Tablet | `768px` | Nav-Links sichtbar, 3-Spalten-Grid |
| Desktop | `992px` | Hero 2-spaltig, Karten-Media sichtbar |

### 2.5 Animation & Interaktion

```css
/* Standard-Transition für Buttons & Links */
transition: transform 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94);

/* Hover: leichtes Anheben */
transform: translateY(-2px);
```

- Keine abrupten Farbwechsel ohne Transition
- Hover auf Karten: Border → Orange-Tönung + `translateY(-2px)`
- Fokus auf Inputs: Orange Border + `box-shadow: 0 0 0 3px rgba(255, 50, 10, 0.12)`

---

## 3. Komponenten

### 3.1 Navigation (`.nav`)

```html
<div class="nav-wrapper">
  <nav class="nav">
    <a href="/" class="nav__brand">
      <img src="{{ logo_dark }}" alt="Candidate Flow Logo" class="nav__logo">
    </a>
    <div class="nav__links">…</div>
    <div class="nav__actions">…</div>
  </nav>
</div>
```

- Sticky, `top: 10px`
- Glas-Effekt: `backdrop-filter: blur(10px)`, halbtransparenter Hintergrund
- Border: `0.5px solid rgba(102, 102, 102, 0.48)`
- Logo-Höhe: `1.25rem`

### 3.2 Buttons (`.button`)

| Variante | Klassen | Einsatz |
|----------|---------|---------|
| Primary | `.button .button--primary` | Haupt-CTA, Orange-Gradient |
| Secondary | `.button .button--secondary` | Nebenaktionen (Jobs, Abbrechen) |
| Small | `+ .button--sm` | Navigation, Formulare |
| Large | `+ .button--lg` | Abschluss-CTA |

**Primary Button mit Pfeil:**

```html
<a href="#" class="button button--primary">
  <span>Jetzt Fachkräfte einstellen</span>
  <img src="…/horizontal arrow.svg" alt="" class="button__arrow" width="23" height="13">
</a>
```

**CTA-Subline (immer unter Primary CTAs):**

```html
<div class="cta-subline">
  <p class="text-secondary text-small-medium">100&nbsp;% unverbindlich · 60 Sek.</p>
  <img src="…/check (3).svg" alt="" class="cta-subline__icon">
</div>
```

### 3.3 Sektionen

| Klasse | Hintergrund | Text |
|--------|-------------|------|
| `.section--dark` | `--black` | Weiß |
| `.section--dark.section--gradient` | Schwarz + Orange-Radial | Weiß |
| `.section--light` | `--white` | Schwarz |
| `.stats` | `--grey-900` | Weiß |
| `.cta` | `--grey-900` | Weiß |
| `.footer` | `--grey-950` | `--grey-300` |

**Standard-Sektionsstruktur:**

```html
<section class="section section--dark" id="…">
  <div class="padding-global padding-section-medium">
    <div class="container-large">
      <!-- Inhalt -->
    </div>
  </div>
</section>
```

### 3.4 Hero (`.hero`)

- Volle Viewport-Höhe (`min-height: 100vh`)
- Negativer Top-Margin für Überlappung mit Nav
- 2-spaltiges Grid ab 992px (Content + Karte/Media)
- Eyebrow (H3) → H1 mit `.text-accent` → Lead-Text → CTA → Trust

### 3.5 Step Cards (`.step-card`)

```html
<article class="step-card">
  <span class="step-card__num">01</span>
  <h3 class="heading-h4">Titel</h3>
  <p class="text-secondary">Beschreibung</p>
</article>
```

- Hintergrund: `--grey-950`
- Border: `1px solid rgba(102, 102, 102, 0.35)`
- Nummer in `--brand-orange`

### 3.6 Cards (`.card`) – helle Oberfläche

Für Formulare, Listen, interaktive Demo-Bereiche auf `.section--light`.

### 3.7 Status Badge (`.status`)

```html
<span class="status">Neu</span>
```

- Pill-Form (`border-radius: 999px`)
- Hintergrund: `rgba(255, 50, 10, 0.1)`
- Text: `--brand-orange`

### 3.8 Stats (`.stat`)

- Zahl: Orange-Gradient-Text, Bold 700
- Label: `.text-secondary`, `0.8125rem`

### 3.9 Formulare

```html
<input type="text" placeholder="Name eingeben">
<button type="submit" class="button button--primary button--sm">Hinzufügen</button>
```

- Border: `#ccc` → Fokus: `--brand-orange`
- Immer `.button--primary` für Submit-Aktionen

### 3.10 Testimonial (`.testimonial`)

- Zentriert, max-width `48rem`
- Zitat als `.heading-h3--quote`
- Autor: `<strong>` + `.text-secondary` für Firma

---

## 4. Assets

| Asset | URL |
|-------|-----|
| Logo dunkel | `static/img/logo-dark.svg` — Nav, Hero, Loader, Footer |
| Logo hell | `static/img/logo-light.svg` — helle Sektionen (optional) |
| Button-Pfeil | `https://cdn.prod.website-files.com/6800d44f708683707fc0c14e/6800d44f708683707fc0c215_horizontal%20arrow.svg` |
| Check-Icon | `https://cdn.prod.website-files.com/6800d44f708683707fc0c14e/684ee7dd34b85e14f37ae3f9_check%20(3).svg` |
| Hero-Karte | `https://cdn.prod.website-files.com/6800d44f708683707fc0c14e/694db0e3558deec2be8e9fb4_RC_map.avif` |

**Outfit Font (WOFF2):** Gehostet auf dem Candidate-Flow CDN – siehe `@font-face` in `style.css`.

---

## 5. Namenskonventionen (CSS)

BEM-ähnliche Struktur, konsistent mit der Landingpage:

```
.block                    → .hero, .nav, .button, .step-card
.block__element           → .hero__layout, .nav__links, .button__arrow
.block--modifier          → .button--primary, .section--dark, .heading-h2--dark
```

**Regeln:**
- Neue Komponenten als Block mit `__element` und `--modifier`
- Utility-Klassen für Typografie: `.text-*`, `.heading-*`
- Layout-Utilities: `.padding-global`, `.container-large`
- Keine Inline-Styles für Farben oder Abstände

---

## 6. Do's & Don'ts

### Do

- Orange-Gradient für alle primären CTAs
- `.text-accent` nur für kurze, betonte Wörter (1–2 Wörter)
- CTA-Subline mit Check-Icon unter Hauptbuttons
- Helle Sektionen für Formulare und datenintensive UI
- `clamp()` für responsive Überschriften
- Du-Ansprache in UI-Texten

### Don't

- Blau oder Grün als Primärfarbe (nur Orange/Gold)
- Inter, Arial oder andere Schriften statt Outfit
- Pill-Buttons (volle Border-Radius) – Radius ist `--radius` (8px)
- Neon-Glows oder starke Schatten (Design ist flach + Gradient)
- Lange Texte in `.text-accent` (Gradient-Text schlecht lesbar)
- Neue Farben ohne CSS-Variable

---

## 7. Checkliste für neue UI-Elemente

- [ ] Verwendet CSS-Variablen aus `:root`
- [ ] Typografie-Klassen statt ad-hoc `font-size`
- [ ] Korrekte Sektions-Klasse (`--dark` / `--light`)
- [ ] Primary CTA mit Subline-Pattern
- [ ] Hover/Focus-States definiert
- [ ] Mobile getestet (< 768px)
- [ ] Kontrast auf dunklem und hellem Grund geprüft
- [ ] In `/styleguide` ergänzt (bei neuen Komponenten)

---

## 8. Dateistruktur

```
static/css/style.css      ← Design Tokens + alle Komponenten
templates/index.html      ← Referenz-Implementierung Landingpage
templates/styleguide.html ← Visuelle Komponentenbibliothek
docs/STYLE_GUIDE.md       ← Diese Dokumentation
```

Bei wachsendem Projekt empfiehlt sich später eine Aufteilung in `_tokens.css`, `_typography.css`, `_components.css` – vorerst bleibt alles in `style.css` als Single Source of Truth.
