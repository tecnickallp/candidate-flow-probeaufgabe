const analysisForm = document.getElementById("analysis-form");
const loader = document.getElementById("loader");
const loaderStatus = document.getElementById("loader-status");
const formError = document.getElementById("form-error");

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_MS = 360000;
const ANALYZE_START_TIMEOUT_MS = 120000;
const EXTRACT_HINT_MS = 20000;

function showError(message) {
  formError.textContent = message;
  formError.hidden = !message;
}

function showLoader(show) {
  loader.hidden = !show;
  document.body.style.overflow = show ? "hidden" : "";
}

function setLoaderStatus(text) {
  if (loaderStatus) loaderStatus.textContent = text;
}

async function fetchWithTimeout(url, options, timeoutMs, timeoutMessage) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function pollJob(jobId) {
  const started = Date.now();
  while (true) {
    const elapsed = Date.now() - started;
    if (elapsed > MAX_POLL_MS) {
      throw new Error(
        "Die Analyse dauert ungewöhnlich lange. Bitte in 1–2 Minuten erneut versuchen."
      );
    }

    const response = await fetch(`/api/jobs/${jobId}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Job-Status konnte nicht geladen werden.");
    }

    let statusText = data.progress || "Analyse läuft…";
    if (
      statusText.includes("extrahiert") &&
      elapsed > EXTRACT_HINT_MS
    ) {
      statusText = "Claude Opus 4.8 extrahiert Daten — kann 1–3 Minuten dauern…";
    }
    setLoaderStatus(statusText);

    if (data.status === "completed" && data.analysis_id) {
      return data.analysis_id;
    }
    if (data.status === "failed") {
      throw new Error(data.error || "Analyse fehlgeschlagen.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

if (analysisForm) {
  analysisForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");

    const companyName = document.getElementById("company-name").value.trim();
    const websiteUrl = document.getElementById("website-url").value.trim();
    if (!companyName || !websiteUrl) {
      showError("Bitte Firmenname und Website-URL ausfüllen.");
      return;
    }

    showLoader(true);
    setLoaderStatus("Server wird kontaktiert… (Cold Start auf Render kann 30–60 Sek. dauern)");

    try {
      const response = await fetchWithTimeout(
        "/api/analyze",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_name: companyName, website_url: websiteUrl }),
        },
        ANALYZE_START_TIMEOUT_MS,
        "Server antwortet nicht (Cold Start?). Bitte Seite neu laden und erneut versuchen."
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Analyse konnte nicht gestartet werden.");
      }
      setLoaderStatus("Analyse wird vorbereitet…");
      const analysisId = await pollJob(data.job_id);
      window.location.href = `/results/${analysisId}`;
    } catch (error) {
      showLoader(false);
      showError(error.message || "Unbekannter Fehler.");
    }
  });
}
