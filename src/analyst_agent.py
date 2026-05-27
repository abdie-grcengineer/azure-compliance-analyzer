"""
Foundry CMMC Analyst agent.

Uses the Azure AI Foundry Agent Service: persistent agents with system
instructions, optional tools, and run-based conversations.

In v1 the agent has:
  - A system prompt that scopes it to executive-audience narrative generation.
  - No custom tools (the mapper and Defender client run in the Function,
    not inside the agent). Tools are a v3 task per the README roadmap.

The agent is looked up by name and created on first invocation if it
doesn't already exist in the project. In v2+ we'd move agent creation
into a deploy-time setup script and pin its ID via app setting.
"""

import json
import logging
import os
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

AGENT_NAME = "cmmc-compliance-analyst"

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


def _get_or_create_agent(client: AIProjectClient, model: str) -> str:
    """Return the agent ID, creating the agent if it doesn't exist."""
    for agent in client.agents.list_agents():
        if agent.name == AGENT_NAME:
            return agent.id

    created = client.agents.create_agent(
        model=model,
        name=AGENT_NAME,
        instructions=SYSTEM_INSTRUCTIONS,
    )
    logger.info("Created Foundry agent: %s", created.id)
    return created.id


def generate_narrative(framework: str, mapped_findings: list[dict[str, Any]]) -> str:
    """Send mapped findings to the agent and return the narrative Markdown."""
    model = os.environ["FOUNDRY_AGENT_MODEL"]
    client = _project_client()
    agent_id = _get_or_create_agent(client, model)

    user_payload = {
        "framework": framework,
        "finding_count": len(mapped_findings),
        # Cap the prompt payload so we don't blow out the context window in v1.
        # v4 will swap this for vector-store grounding.
        "findings": mapped_findings[:200],
    }

    thread = client.agents.threads.create()
    client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=(
            "Generate an executive CMMC L2 compliance briefing from the "
            f"following structured findings:\n\n```json\n{json.dumps(user_payload, default=str, indent=2)}\n```"
        ),
    )
    run = client.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent_id,
    )

    if run.status != "completed":
        logger.error("Agent run did not complete: %s", run.status)
        return f"_(Agent run failed: {run.status})_"

    messages = client.agents.messages.list(thread_id=thread.id, order="desc")
    for m in messages:
        if m.role == "assistant" and m.text_messages:
            return m.text_messages[-1].text.value
    return "_(No assistant response)_"
