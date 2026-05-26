"""
Foundry CMMC Analyst agent.

Uses the Azure AI Foundry Agent Service: persistent agents with system
instructions, optional tools, and run-based conversations.

In v1 the agent has:
  - A system prompt scoped to CMMC L2 narrative generation.
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
You are a CMMC Level 2 compliance analyst. Given a list of Defender for Cloud
regulatory compliance assessments mapped to CMMC Level 2 practice IDs (e.g.
AC.L2-3.1.1, SC.L2-3.13.8), write a concise executive summary suitable for a
DoD contractor's security team and a C3PAO assessor.

Structure your response as Markdown with these sections:
  1. **Posture overview** (2-3 sentences summarizing CMMC L2 readiness).
  2. **Top risks** (bulleted, ordered by severity then by failed resource count).
  3. **Domain coverage** (which CMMC domains are most affected; reference domain
     codes like AC, SC, IA, AU).
  4. **Suggested next steps** (3-5 prioritized actions, each one sentence,
     framed as remediation for CMMC assessment).

Be specific. Cite CMMC practice IDs in full (e.g. SC.L2-3.13.8). Do not
invent findings; only use what's in the provided JSON. If a section has
nothing to report, say so explicitly. Remember the audience cares about
protecting Controlled Unclassified Information (CUI).
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
            "Generate a CMMC L2 compliance narrative from the following "
            f"structured findings:\n\n```json\n{json.dumps(user_payload, default=str, indent=2)}\n```"
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
