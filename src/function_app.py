"""
Azure Function: weekly CMMC L2 compliance analyzer.

Runs every Monday at 09:00 UTC. The pipeline:
  1. Pulls regulatory compliance assessments from Defender for Cloud for
     the configured standard (NIST SP 800-171 Rev. 2 by default, which is
     the underlying control set CMMC Level 2 enforces).
  2. Maps each assessment to one or more CMMC L2 practice IDs.
  3. Asks the Foundry CMMC Analyst agent for an executive-summary narrative
     over the structured findings.
  4. Writes the rendered Markdown report to Blob Storage.
"""

import logging
import os
from datetime import datetime, timezone

import azure.functions as func

from defender_client import get_findings
from cmmc_mapper import CMMCMapper
from analyst_agent import generate_narrative
from report import render_report
from blob_writer import write_report

app = func.FunctionApp()


# NCRONTAB format: {second} {minute} {hour} {day} {month} {day-of-week}
# "0 0 9 * * 1" = every Monday at 09:00 UTC.
@app.timer_trigger(
    schedule="0 0 9 * * 1",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def weekly_cmmc_report(timer: func.TimerRequest) -> None:
    logging.info("Weekly CMMC L2 compliance analyzer starting")

    standard = os.environ.get("DEFENDER_STANDARD", "NIST SP 800-171 Rev. 2")
    hours = int(os.environ.get("DEFENDER_HOURS", "168"))
    subscription_id = os.environ["SUBSCRIPTION_ID"]

    findings = get_findings(
        subscription_id=subscription_id,
        standard_name=standard,
        hours=hours,
    )
    logging.info("Retrieved %d findings from Defender for Cloud", len(findings))

    mapper = CMMCMapper()
    mapped = [mapper.map_finding(f) for f in findings]

    narrative = generate_narrative(framework="CMMC Level 2", mapped_findings=mapped)

    report_md = render_report(
        framework="CMMC Level 2",
        standard=standard,
        mapped_findings=mapped,
        narrative=narrative,
        generated_at=datetime.now(timezone.utc),
    )

    blob_url = write_report(report_md)
    logging.info("Report written: %s", blob_url)
