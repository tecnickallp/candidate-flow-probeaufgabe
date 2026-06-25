const analysisForm = document.getElementById("analysis-form");
const loader = document.getElementById("loader");
const loaderStatus = document.getElementById("loader-status");
const formError = document.getElementById("form-error");

const POLL_INTERVAL_MS = 1500;

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

async function pollJob(jobId) {
  while (true) {
    const response = await fetch(`/api/jobs/${jobId}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Job-Status konnte nicht geladen werden.");
    }
    if (data.progress) setLoaderStatus(data.progress);
    if (data.status === "completed" && data.analysis_id) {
      return data.analysis_id;
    }
    if (data.status === "failed") {
      throw new Error(data.error || "Analyse fehlgeschlagen.");
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
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
    setLoaderStatus("Analyse wird vorbereitet…");

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_name: companyName, website_url: websiteUrl }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Analyse konnte nicht gestartet werden.");
      }
      const analysisId = await pollJob(data.job_id);
      window.location.href = `/results/${analysisId}`;
    } catch (error) {
      showLoader(false);
      showError(error.message || "Unbekannter Fehler.");
    }
  });
}
