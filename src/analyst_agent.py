"""
Foundry CMMC Analyst.

Uses azure-ai-projects 2.x, which exposes the Foundry model deployments
through an OpenAI-compatible chat completions endpoint. For the v1
one-shot narrative generation we don't need persistent agent state, so
we just call chat completions with the system prompt + structured user
message in a single round trip.

When we add tools in v3 (per the README roadmap), we'll switch to the
agent + version pattern with `client.agents.create_version()` and the
openai_client.chat.completions function-calling surface for tool calls.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = """\
You are a CMMC Level 2 compliance analyst writing for a Chief Information
Security Officer or other senior executive. The reader has 90 seconds.
Translate technical compliance findings into business language a non-
technical executive can act on.

Structure your response as Markdown with exactly these four sections:

## Executive Summary
2-3 sentences. Lead with the bottom line. State the overall CMMC Level 2
readiness posture and the single most important business implication.
Avoid jargon. Numbers should be specific.

## Top Business Risks
Bulleted list of 3-5 risks. Each bullet:
- **<Risk in business terms>**: <one sentence on business impact: contract
  eligibility, audit deadline, financial exposure, customer commitment>.
  _Evidence: <count> failing assessments in <CMMC domain code(s)>._

Translate findings into business language. Example: instead of "12 storage
accounts have public network access enabled," write "Customer data is
reachable from the public internet across 12 production systems, creating
breach exposure that disqualifies us from CMMC Level 2 certification."

## Decisions for Leadership
Bulleted list of 3-5 decisions the executive needs to make this week.
Each item:
- **<The decision>**: <one sentence on rough cost / effort / timeline>.
  _Closes: <count> related findings._

Frame as something the executive can approve or reject, not a technical
action. Example: "Approve a 90-day cloud-security sprint (one engineer,
~$45K loaded cost) to close MFA and encryption gaps" rather than
"Enable MFA on all admin accounts."

## Reading the Technical Appendix
One sentence pointing the technical team at the detailed appendix below
the executive summary.

Rules:
- Cite CMMC practice IDs sparingly and only when essential. Prefer domain
  codes (AC, SC, IA, AU, CM, IR, MA, MP, PE, PS, RA, CA, SI).
- Do not invent findings. Only use what's in the provided JSON.
- Do not mention model names, AI, or the analysis process. Write as if
  you are the analyst signing the report.
- Keep the entire response under 500 words.
- If there are zero failing assessments, say so plainly and skip Top
  Business Risks and Decisions.
"""


def _project_client() -> AIProjectClient:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def generate_narrative(framework: str, mapped_findings: list[dict[str, Any]]) -> str:
    """
    One-shot chat completion against the Foundry model deployment.

    Pattern: get the OpenAI-compatible client from the AIProjectClient,
    call chat.completions.create with the deployment name as the model.
    """
    model = os.environ["FOUNDRY_AGENT_MODEL"]
    project = _project_client()
    # No api_version: get_openai_client returns a plain openai.OpenAI pointed
    # at <foundry_endpoint>/openai/v1, bearer-token auth wired from our
    # DefaultAzureCredential. The model arg below is the Foundry deployment
    # name ("Phi-4" in our default config).
    openai_client = project.get_openai_client()

    # Separate failing from non-failing so the agent doesn't conflate the total
    # count with the count that needs action. In practice Phi-4 was reading
    # "finding_count: 57" as "57 critical findings" before this split.
    failing = [f for f in mapped_findings if f.get("State") == "Failed"]
    other = [f for f in mapped_findings if f.get("State") != "Failed"]

    user_payload = {
        "framework": framework,
        "counts": {
            "total_assessments": len(mapped_findings),
            "failing": len(failing),
            "passing": sum(1 for f in other if f.get("State") == "Passed"),
            "other_states": len(other) - sum(1 for f in other if f.get("State") == "Passed"),
        },
        # Only send the failing assessments to the agent — those are the only
        # ones it can write actionable risks and decisions about. Cap at 100
        # so we don't blow out the context window on a large tenant.
        "failing_assessments": failing[:100],
    }

    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": (
                        "Generate an executive CMMC L2 compliance briefing from the "
                        "following structured findings:\n\n"
                        f"```json\n{json.dumps(user_payload, default=str, indent=2)}\n```"
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        return response.choices[0].message.content or "_(empty agent response)_"
    except Exception as e:
        logger.error("Foundry chat completion failed: %s", e)
        return f"_(Agent call failed: {e})_"
