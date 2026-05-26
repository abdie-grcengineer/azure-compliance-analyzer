# What this tool does (and why it's GRC Engineering)

## The problem

CMMC Level 2 has 110 practices. A DoD contractor pursuing certification needs to show, on demand, that every one of those practices is implemented and is *staying* implemented. The traditional way to do this is one of:

1. **A spreadsheet.** Someone interviews engineers, copies screenshots into a tracker, and updates it quarterly. By the time the C3PAO arrives, the spreadsheet is months out of date and the conversation in the assessment becomes archaeology.
2. **A GRC SaaS product.** It does some of this automatically through cloud connectors, but the mapping from cloud-control to CMMC practice is opaque, the reports are templated, and the narrative summary still gets written by hand the night before the meeting.
3. **The cloud-native dashboard.** Microsoft Defender for Cloud already runs continuous compliance assessments against built-in standards including NIST SP 800-171 Rev. 2 (which CMMC L2 is built on). The data is there. The problem is that nobody is *consuming* it on a schedule the way they would a build pipeline.

This tool fixes option 3.

## What this tool does

Once a week, at 09:00 UTC on Monday, a Python Azure Function:

1. **Asks Defender for Cloud** for every regulatory compliance assessment under the NIST SP 800-171 Rev. 2 standard (the underlying control set for CMMC L2). Defender already runs these continuously, so it's a read.
2. **Maps each assessment to one or more CMMC L2 practice IDs** (e.g. `SC.L2-3.13.8`, `AC.L2-3.1.5`) using a JSON-driven keyword mapper that's checked into the repo. The mapping is auditable, version-controlled, and PR-reviewable.
3. **Sends the structured findings to an Azure AI Foundry agent** ("cmmc-compliance-analyst") with a system prompt that tells it to produce a four-section Markdown executive summary: posture overview, top risks, domain coverage, suggested next steps.
4. **Writes the rendered report to Blob Storage** with a timestamped filename. The blob container is the system of record for "what did our compliance posture look like on date X."

Everything runs as the Function's user-assigned managed identity. There are no service principal secrets to rotate.

## What this tool is NOT

- It is not a substitute for a C3PAO assessment. It produces an *internal* readiness signal.
- It does not replace the human review of mapping logic. The keyword mapper is starter content. Production use means someone who knows the CMMC Assessment Guide owns `config/mappings/cmmc.json`.
- It does not collect evidence beyond what Defender already collects. If a practice isn't covered by a Defender assessment (e.g. physical protection, personnel security), this tool will not see it.
- It is not a chatbot. The Foundry agent is invoked once per run with structured input and produces structured output. v3 adds tool use for ad-hoc queries.

## Why this is GRC Engineering

GRC Engineering treats compliance the way software engineering teams treat reliability: as something that should be observed continuously, instrumented in code, and reviewed in version control rather than reviewed in PDFs once a quarter. The cues:

| GRC Engineering principle | How this tool embodies it |
|---|---|
| **Compliance as code** | The mapping from Defender assessment to CMMC practice lives in [config/mappings/cmmc.json](../config/mappings/cmmc.json). Changes are PRs. The diff history is the audit trail of "when did we change how we interpret SC.L2-3.13.8?" |
| **Evidence as a side-effect of the work, not a separate workstream** | The weekly report is generated from the live regulatory compliance API, not from a separate evidence collection process. There is no drift between "what the system actually does" and "what the report says." |
| **Continuous, not periodic** | The timer runs weekly, but the underlying Defender assessments update continuously. The report is a render of state-at-time-X, not a manually compiled snapshot. |
| **Infrastructure as code, end to end** | Every Azure resource (storage, Function, Foundry project, model deployment, RBAC) is in [infra/main.tf](../infra/main.tf). `terraform destroy` cleanly removes the entire control plane. |
| **Least privilege, by default** | The Function runs as a user-assigned MI with three RBAC scopes: Storage Blob Data Contributor (just the report bucket), Azure AI User (just the Foundry project), Security Reader (subscription, granted manually post-deploy). No `*:*` policies. No long-lived secrets. |
| **AI where judgment is needed, not where mechanics are** | The mechanics (pull assessments, map to practices, write to Blob) are deterministic Python. The AI is asked to do *only* the part that is genuinely judgment-shaped: write a coherent executive narrative over the structured input. The mapping logic stays in version control because an auditor needs to defend it. |
| **Failure modes are observable** | App Insights and Log Analytics are wired in. The Function logs every stage. Failed agent runs are logged with status. The blob container's modification timestamps are themselves evidence the pipeline ran. |

## How it's different from a typical "AI GRC tool"

Most current AI compliance tooling falls into one of two patterns:

1. **AI as a chatbot wrapper** over the same dashboards humans were already reading. The LLM doesn't have hands; it can summarize what you paste in, but it doesn't pull, map, or persist anything.
2. **AI as the mapper** — an LLM is asked to decide which CMMC practice a finding maps to. This is fast to build, hard to defend in an assessment, and unpredictable when the underlying model changes.

This tool does neither. The mapper is code (deterministic, auditable, diffable). The persistence is code (managed identity to a versioned blob container). The AI is reserved for the narrative summary, the one task where "judgment about how to communicate to humans" is the actual product.

When v3 adds Foundry agent tools, the agent will be able to call back into the deterministic mapper and Defender client itself — but the *mapping logic* will still live in code, not in the prompt.

## v1 → v5 roadmap (and why each step exists)

- **v2 — Email + CMK + signed evidence bundles**. The current report lands in Blob. v2 makes it stakeholder-visible (ACS email) and tamper-evident (per-run JSON evidence bundle with content hash + Customer-Managed-Key encryption via Key Vault, satisfying SC.L2-3.13.11). This is the version that's actually fit for sharing externally.
- **v3 — Foundry agent tools**. Convert the deterministic Python functions (`get_findings`, `lookup_practice`, `write_report`) into agent tools so the agent can orchestrate. Same logic in the same Python files, just exposed differently. Enables conversational ad-hoc queries ("what changed in SC since last week?") on top of the weekly run.
- **v4 — Grounding + evaluations**. Index past reports and the CMMC Assessment Guide into a Foundry vector store. Set up Foundry Evaluations against a golden set so we have a metric for "did this report quality regress?" — same way a software team has a regression suite.
- **v5 — Multi-framework**. Add HIPAA HITRUST and FedRAMP Moderate as parallel pipelines sharing the same agent + infra. The mapping JSON pattern generalizes; the agent's system prompt is parameterized by framework.

Every step exists because the *previous* step would, in real production use by a real contractor, hit a specific limit. The roadmap isn't speculative — it's the next thing that would break.
