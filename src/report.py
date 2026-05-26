"""Markdown report builder for the weekly CMMC compliance report."""

from collections import Counter
from datetime import datetime
from typing import Any


def render_report(
    framework: str,
    standard: str,
    mapped_findings: list[dict[str, Any]],
    narrative: str,
    generated_at: datetime,
) -> str:
    total = len(mapped_findings)
    by_state = Counter(f.get("State") or "Unknown" for f in mapped_findings)
    by_severity = Counter(f.get("Severity") or "INFORMATIONAL" for f in mapped_findings)
    by_practice: Counter = Counter()
    by_domain: Counter = Counter()
    for f in mapped_findings:
        for p in f.get("CMMCPractices", []):
            by_practice[p] += 1
        for d in f.get("CMMCDomains", []):
            by_domain[d] += 1

    lines = [
        f"# {framework} Compliance Report",
        f"_Underlying Defender standard: {standard}_  ",
        f"_Generated: {generated_at.isoformat()}_",
        "",
        "## Summary",
        f"- Total assessments analyzed: **{total}**",
        f"- By state: {dict(by_state)}",
        f"- By derived severity: {dict(by_severity)}",
        "",
        "## Analyst narrative",
        "",
        narrative,
        "",
        "## Domain coverage",
    ]
    for domain, count in by_domain.most_common():
        lines.append(f"- `{domain}`: {count} finding(s)")

    lines.extend(["", "## Practice coverage", ""])
    for practice, count in by_practice.most_common(25):
        lines.append(f"- `{practice}`: {count} finding(s)")

    lines.extend(["", "## Top failing assessments", ""])
    failing = [f for f in mapped_findings if f.get("State") == "Failed"]
    for f in failing[:25]:
        lines.append(
            f"- **{f.get('Title')}**  \n"
            f"  Defender control: `{f.get('ControlId')}`  \n"
            f"  Failed resources: {f.get('FailedResources') or 0}  \n"
            f"  CMMC practices: {', '.join(f.get('CMMCPractices') or [])}"
        )

    return "\n".join(lines)
