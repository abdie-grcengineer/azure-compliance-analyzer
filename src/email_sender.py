"""
Email delivery for the weekly CMMC compliance report.

Uses Azure Communication Services Email. Sender is an Azure-managed
donotreply address (no DNS verification needed); recipient is set via
the REPORT_RECIPIENT_EMAIL app setting.

v1 uses connection-string auth. v2 will move the connection string to
Key Vault and switch to managed-identity auth.

The HTML template is intentionally executive-readable:
  - RAG status banner at the top, color-coded
  - Generous typography, large headers, plenty of whitespace
  - Brand color (royal blue, matches the static landing page)
  - Technical appendix visually distinct (muted background, smaller type)
    so it's clear what's "for the exec" vs. "for the security team"
"""

from __future__ import annotations

import logging
import os
import re

import markdown
from azure.communication.email import EmailClient

logger = logging.getLogger(__name__)


def send_report_email(
    subject: str,
    report_md: str,
    blob_url: str | None = None,
    rag_label: str | None = None,
    rag_color: str | None = None,
    rag_headline: str | None = None,
) -> None:
    """Render the Markdown report as HTML and email it via ACS."""
    conn_str = os.environ["ACS_CONNECTION_STRING"]
    sender = os.environ["ACS_SENDER"]
    recipient = os.environ["REPORT_RECIPIENT_EMAIL"]

    # If the caller didn't pass the RAG (e.g. older code path), try to
    # parse it out of the report Markdown so the banner still works.
    if not rag_label:
        rag_label, rag_color, rag_headline = _extract_rag_from_markdown(report_md)

    # Prefix the subject with the RAG status so the inbox preview shows
    # posture at a glance.
    subject_with_status = f"[{rag_label}] {subject}" if rag_label else subject

    html_body = _render_html(
        report_md=report_md,
        rag_label=rag_label or "UNKNOWN",
        rag_color=rag_color or "#666",
        rag_headline=rag_headline or "",
        blob_url=blob_url,
    )
    plain_body = report_md if not blob_url else f"{report_md}\n\nReport blob: {blob_url}\n"

    client = EmailClient.from_connection_string(conn_str)

    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": recipient}]},
        "content": {
            "subject": subject_with_status,
            "plainText": plain_body,
            "html": html_body,
        },
    }

    poller = client.begin_send(message)
    result = poller.result()
    status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "unknown")
    logger.info("ACS email send status: %s (to=%s, rag=%s)", status, recipient, rag_label)


_RAG_RE = re.compile(r"\*\*Overall posture:\s*(\w+)\*\*", re.IGNORECASE)


def _extract_rag_from_markdown(report_md: str) -> tuple[str, str, str]:
    """Fallback parser for the RAG line embedded in the report Markdown."""
    match = _RAG_RE.search(report_md)
    if not match:
        return ("UNKNOWN", "#666666", "")
    label = match.group(1).upper()
    color = {"RED": "#c0392b", "AMBER": "#d68910", "GREEN": "#1e8449"}.get(label, "#666666")
    return (label, color, "")


def _render_html(
    report_md: str,
    rag_label: str,
    rag_color: str,
    rag_headline: str,
    blob_url: str | None,
) -> str:
    """Wrap the rendered Markdown in an executive-friendly HTML shell."""
    body_html = markdown.markdown(report_md, extensions=["tables", "fenced_code"])

    blob_footer = (
        f'<p class="blob-link">Full report blob (for the security team): '
        f'<a href="{blob_url}">{blob_url}</a></p>'
        if blob_url
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   "Helvetica Neue", Arial, sans-serif;
      max-width: 780px;
      margin: 0 auto;
      padding: 0;
      color: #1a1a1a;
      line-height: 1.6;
      background: #f7f8fa;
    }}

    .rag-banner {{
      background: {rag_color};
      color: #ffffff;
      padding: 1.5rem 2rem;
      text-align: center;
    }}
    .rag-banner .label {{
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      margin-bottom: 0.25rem;
    }}
    .rag-banner .headline {{
      font-size: 1rem;
      opacity: 0.95;
    }}

    .container {{
      background: #ffffff;
      padding: 2rem 2.5rem 2.5rem 2.5rem;
    }}

    h1 {{
      color: #002366;
      border-bottom: 3px solid #002366;
      padding-bottom: 0.4rem;
      margin-top: 0;
      font-size: 1.6rem;
    }}
    h2 {{
      color: #002366;
      margin-top: 2rem;
      font-size: 1.2rem;
    }}
    h3 {{ color: #002366; font-size: 1.05rem; }}

    p, li {{ font-size: 1rem; }}
    ul, ol {{ padding-left: 1.4rem; }}
    li {{ margin-bottom: 0.5rem; }}
    strong {{ color: #002366; }}
    em {{ color: #555; }}

    code {{
      background: #eef1f7;
      padding: 0.1em 0.4em;
      border-radius: 3px;
      font-size: 0.92em;
      color: #002366;
    }}

    hr {{
      border: none;
      border-top: 1px solid #d8dce5;
      margin: 2rem 0;
    }}

    /* Technical appendix: visually de-emphasized so an exec knows it's */
    /* not for them. We use a subtle wrapper class applied via sectioning */
    /* on h1 "Technical Appendix" via CSS attribute selectors below. */
    h1 + hr + p em,
    h1:nth-of-type(2) {{
      color: #6b6b6b;
    }}

    table {{
      border-collapse: collapse;
      margin: 1rem 0;
      width: 100%;
      font-size: 0.95rem;
    }}
    th, td {{
      border: 1px solid #d8dce5;
      padding: 0.5rem 0.8rem;
      text-align: left;
    }}
    th {{ background: #002366; color: #ffffff; }}

    .blob-link {{
      margin-top: 2rem;
      font-size: 0.85rem;
      color: #6b6b6b;
      padding-top: 1rem;
      border-top: 1px solid #d8dce5;
    }}
    .blob-link a {{ color: #002366; }}

    .read-time {{
      text-align: center;
      font-size: 0.85rem;
      color: #ffffff;
      opacity: 0.85;
      margin-top: 0.5rem;
    }}

    .footer {{
      text-align: center;
      font-size: 0.8rem;
      color: #6b6b6b;
      padding: 1.5rem 2rem;
    }}
  </style>
</head>
<body>
  <div class="rag-banner">
    <div class="label">{rag_label}</div>
    <div class="headline">{rag_headline}</div>
    <div class="read-time">90-second read</div>
  </div>
  <div class="container">
    {body_html}
    {blob_footer}
  </div>
  <div class="footer">
    azure-compliance-analyzer / weekly CMMC L2 briefing<br>
    Source: Microsoft Defender for Cloud
  </div>
</body>
</html>
"""
