from __future__ import annotations

import html
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

import config

log = logging.getLogger(__name__)


def _build_subject(data: dict[str, Any]) -> str:
    company = (data.get("company_name") or "Unbekannt").strip()
    return f"Neuer Lead erfasst: {company}"


def _build_html(analysis_id: str, data: dict[str, Any]) -> str:
    company = html.escape((data.get("company_name") or "").strip())
    website = html.escape((data.get("website_url") or "").strip())
    industry = html.escape((data.get("industry") or "—").strip())
    vibe = html.escape((data.get("vibe") or "—").strip())
    benefits = data.get("benefits") or []
    jobs = data.get("jobs") or []
    analyzed_at = html.escape((data.get("analyzed_at") or "").strip())

    benefits_html = "".join(f"<li>{html.escape(str(b))}</li>" for b in benefits[:12])
    if not benefits_html:
        benefits_html = "<li>—</li>"

    jobs_html = ""
    for job in jobs[:8]:
        title = html.escape(str(job.get("title") or "Stelle"))
        tasks = job.get("tasks") or []
        task_items = "".join(f"<li>{html.escape(str(t))}</li>" for t in tasks[:4])
        jobs_html += f"<li><strong>{title}</strong>"
        if task_items:
            jobs_html += f"<ul>{task_items}</ul>"
        jobs_html += "</li>"
    if not jobs_html:
        jobs_html = "<li>Keine Stellen gefunden</li>"

    return f"""<!DOCTYPE html>
<html lang="de">
<body style="font-family: system-ui, sans-serif; line-height: 1.5; color: #161616;">
  <h1 style="color: #ff320a; font-size: 1.25rem;">Neuer Lead erfolgreich erfasst</h1>
  <p>Die Arbeitgeber-Analyse wurde abgeschlossen und in der Datenbank gespeichert.</p>
  <table style="border-collapse: collapse; width: 100%; max-width: 36rem;">
    <tr><td style="padding: 0.25rem 0.5rem 0.25rem 0;"><strong>Firma</strong></td><td>{company}</td></tr>
    <tr><td style="padding: 0.25rem 0.5rem 0.25rem 0;"><strong>Website</strong></td><td><a href="{website}">{website}</a></td></tr>
    <tr><td style="padding: 0.25rem 0.5rem 0.25rem 0;"><strong>Branche</strong></td><td>{industry}</td></tr>
    <tr><td style="padding: 0.25rem 0.5rem 0.25rem 0;"><strong>Stellen</strong></td><td>{len(jobs)}</td></tr>
    <tr><td style="padding: 0.25rem 0.5rem 0.25rem 0;"><strong>Analyse-ID</strong></td><td>{html.escape(analysis_id)}</td></tr>
    <tr><td style="padding: 0.25rem 0.5rem 0.25rem 0;"><strong>Zeitpunkt</strong></td><td>{analyzed_at}</td></tr>
  </table>
  <h2 style="font-size: 1rem; margin-top: 1.5rem;">Benefits</h2>
  <ul>{benefits_html}</ul>
  <h2 style="font-size: 1rem; margin-top: 1rem;">Vibe &amp; Tonalität</h2>
  <p>{vibe}</p>
  <h2 style="font-size: 1rem; margin-top: 1rem;">Offene Stellen</h2>
  <ul>{jobs_html}</ul>
  <p style="margin-top: 1.5rem; color: #666; font-size: 0.875rem;">
    Candidate Flow · Lead-Enrichment Probeaufgabe
  </p>
</body>
</html>"""


def _build_text(analysis_id: str, data: dict[str, Any]) -> str:
    company = (data.get("company_name") or "").strip()
    website = (data.get("website_url") or "").strip()
    industry = (data.get("industry") or "—").strip()
    jobs = data.get("jobs") or []
    return (
        "Neuer Lead erfolgreich erfasst\n\n"
        f"Firma: {company}\n"
        f"Website: {website}\n"
        f"Branche: {industry}\n"
        f"Stellen: {len(jobs)}\n"
        f"Analyse-ID: {analysis_id}\n"
        f"Zeitpunkt: {data.get('analyzed_at') or '—'}\n"
    )


def _parse_email_from(value: str) -> tuple[str, str]:
    """Return (display_name, email) from 'Name <email@example.com>' or plain email."""
    value = value.strip()
    match = re.match(r"^(.*?)<([^>]+)>$", value)
    if match:
        name = match.group(1).strip().strip('"')
        return name or "Candidate Flow Analyzer", match.group(2).strip()
    return "Candidate Flow Analyzer", value


def _send_via_brevo(
    recipient: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> str | None:
    sender_name, sender_email = _parse_email_from(config.EMAIL_FROM)
    response = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": config.BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": recipient}],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": text_body,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("messageId") or "")


def _send_via_smtp(
    recipient: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    sender_name, sender_email = _parse_email_from(config.EMAIL_FROM)
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.EMAIL_FROM
    message["To"] = recipient
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
        if config.SMTP_USE_TLS:
            server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(sender_email, [recipient], message.as_string())


def _send_via_resend(
    recipient: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> str | None:
    import resend

    resend.api_key = config.RESEND_API_KEY
    params: resend.Emails.SendParams = {
        "from": config.EMAIL_FROM,
        "to": [recipient],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    response = resend.Emails.send(params)
    if isinstance(response, dict):
        return str(response.get("id") or "")
    return str(getattr(response, "id", "") or "")


def notify_lead_captured(analysis_id: str, data: dict[str, Any]) -> None:
    """Send lead summary to artur.b@candidate-flow.de after DB save."""
    subject = _build_subject(data)
    recipient = config.LEAD_NOTIFICATION_TO
    html_body = _build_html(analysis_id, data)
    text_body = _build_text(analysis_id, data)
    provider = config.resolve_email_provider()

    if config.EMAIL_DRY_RUN or not provider:
        log.info(
            "Lead notification skipped (dry_run=%s, provider=%s): to=%s subject=%r analysis_id=%s",
            config.EMAIL_DRY_RUN,
            provider,
            recipient,
            subject,
            analysis_id,
        )
        return

    if provider == "brevo":
        message_id = _send_via_brevo(recipient, subject, html_body, text_body)
        log.info(
            "Lead notification sent via Brevo to %s (message_id=%s, analysis_id=%s)",
            recipient,
            message_id,
            analysis_id,
        )
        return

    if provider == "smtp":
        _send_via_smtp(recipient, subject, html_body, text_body)
        log.info("Lead notification sent via SMTP to %s (analysis_id=%s)", recipient, analysis_id)
        return

    if provider == "resend":
        email_id = _send_via_resend(recipient, subject, html_body, text_body)
        log.info(
            "Lead notification sent via Resend to %s (email_id=%s, analysis_id=%s)",
            recipient,
            email_id,
            analysis_id,
        )
        return

    raise RuntimeError(f"Unbekannter E-Mail-Provider: {provider}")
