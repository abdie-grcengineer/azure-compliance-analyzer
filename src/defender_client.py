"""
Defender for Cloud client.

Defender's regulatory compliance data is structured as a three-level tree:

  Defender:    regulatoryComplianceStandards
                 -> regulatoryComplianceControls
                   -> regulatoryComplianceAssessments

We flatten that tree into a list of finding dicts so the mapper and report
code can iterate a simple list.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.security import SecurityCenter

logger = logging.getLogger(__name__)


def _credential() -> DefaultAzureCredential:
    # AZURE_CLIENT_ID is set in app settings to the UAMI's clientId so that
    # DefaultAzureCredential picks the right identity at runtime when the
    # Function App has multiple identities attached.
    return DefaultAzureCredential()


def get_findings(
    subscription_id: str,
    standard_name: str,
    hours: int = 168,
) -> list[dict[str, Any]]:
    """
    Return a list of finding dicts for the given Defender regulatory
    compliance standard, scoped to assessments updated within `hours`.
    """
    client = SecurityCenter(credential=_credential(), subscription_id=subscription_id)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    findings: list[dict[str, Any]] = []

    try:
        controls = client.regulatory_compliance_controls.list(
            regulatory_compliance_standard_name=standard_name,
        )
    except Exception as e:
        logger.error("Failed to list controls for standard %s: %s", standard_name, e)
        return []

    for control in controls:
        try:
            assessments = client.regulatory_compliance_assessments.list(
                regulatory_compliance_standard_name=standard_name,
                regulatory_compliance_control_name=control.name,
            )
        except Exception as e:
            logger.warning("Failed to list assessments for control %s: %s", control.name, e)
            continue

        for a in assessments:
            updated = getattr(a, "system_data", None)
            updated_ts = getattr(updated, "last_modified_at", None) if updated else None
            if updated_ts and updated_ts < cutoff:
                continue

            findings.append({
                "Id": a.id,
                "Title": a.description or a.name,
                "State": a.state,  # Passed | Failed | Skipped | Unsupported
                "Severity": _severity_from_state(a.state),
                "ControlId": control.name,
                "ControlDescription": control.description,
                "StandardName": standard_name,
                "PassedResources": a.passed_resources,
                "FailedResources": a.failed_resources,
                "SkippedResources": a.skipped_resources,
                "UpdatedAt": updated_ts.isoformat() if updated_ts else None,
            })

    return findings


def _severity_from_state(state: str | None) -> str:
    """
    Defender assessments don't carry a native severity. We synthesize one
    from the state so the downstream report can group by severity.
    """
    return {
        "Failed": "HIGH",
        "Skipped": "MEDIUM",
        "Unsupported": "LOW",
        "Passed": "INFORMATIONAL",
    }.get(state or "", "INFORMATIONAL")
