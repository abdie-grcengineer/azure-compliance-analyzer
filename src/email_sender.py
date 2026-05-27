"""
Email delivery for the weekly CMMC compliance report.

Uses Azure Communication Services Email. Sender is an Azure-managed
donotreply address (no DNS verification needed); recipient is set via
the REPORT_RECIPIENT_EMAIL app setting.

v1 uses connection-string auth. v2 will move the connection string to
Key Vault and switch to managed-identity auth.
"""

import logging
import os

import markdown
from azure.communication.email import EmailClient

logger = logging.getLogger(__name__)


def send_report_email(subject: str, report_md: str, blob_url: str | None = None) -> None:
    """Render the Markdown report as HTML and email it via ACS."""
    conn_str = os.environ["ACS_CONNECTION_STRING"]
    sender = os.environ["ACS_SENDER"]
    recipient = os.environ["REPORT_RECIPIENT_EMAIL"]

    html_body = _wrap_html(markdown.markdown(report_md, extensions=["tables", "fenced_code"]), blob_url)
    plain_body = report_md if not blob_url else f"{report_md}\n\nReport blob: {blob_url}\n"

    client = EmailClient.from_connection_string(conn_str)

    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": recipient}]},
        "content": {
            "subject": subject,
            "plainText": plain_body,
            "html": html_body,
        },
    }

    poller = client.begin_send(message)
    result = poller.result()
    status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "unknown")
    logger.info("ACS email send status: %s (to=%s)", status, recipient)


def _wrap_html(body_html: str, blob_url: str | None) -> str:
    """Wrap the rendered Markdown in a minimal HTML shell with brand styling."""
    blob_footer = (
        f'<p style="margin-top:2rem;font-size:0.9rem;color:#666;">'
        f'Source report blob: <a href="{blob_url}">{blob_url}</a></p>'
        if blob_url
        else ""
    )
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
             max-width: 760px; margin: 2rem auto; padding: 0 1rem; color: #222; line-height: 1.55; }}
    h1 {{ color: #002366; border-bottom: 3px solid #002366; padding-bottom: 0.5rem; }}
    h2 {{ color: #002366; margin-top: 2rem; }}
    code {{ background: #f4f4f4; padding: 0.1em 0.4em; border-radius: 3px; font-size: 0.9em; }}
    table {{ border-collapse: collapse; margin: 1rem 0; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem 0.8rem; text-align: left; }}
    th {{ background: #002366; color: #fff; }}
  </style>
</head>
<body>
{body_html}
{blob_footer}
</body>
</html>
"""
