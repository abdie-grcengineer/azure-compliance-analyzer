# azure-compliance-analyzer

> Continuous CMMC Level 2 evidence pipeline for Azure. Defender for Cloud findings + Azure AI Foundry analyst agent, deployed with Terraform.

A GRC Engineering project: instead of producing a CMMC report by having a human read a Defender dashboard once a quarter, this tool runs every week, pulls the regulatory compliance assessments straight from the API, maps them to CMMC Level 2 practice IDs, and asks an Azure AI Foundry agent to write the executive summary. The output lands in Blob Storage as a Markdown report.

For a longer explanation of the problem, the approach, and why this counts as GRC Engineering rather than "automation," see [docs/what-this-tool-does.md](docs/what-this-tool-does.md).

## Architecture at a glance


<img width="1079" height="606" alt="image" src="https://github.com/user-attachments/assets/10770a1f-c3af-465d-baf8-67a4c37792e9" />


## What's in v1

- **IaC**: Terraform (azurerm 4.x + azapi 2.x). Resource group is a precondition; everything else is provisioned by `terraform apply`.
- **Standard**: CMMC Level 2 (110 practices, mapped through NIST SP 800-171 Rev. 2).
- **Compute**: Linux Consumption Function App (Python 3.11) with a weekly NCRONTAB timer.
- **AI**: Azure AI Foundry project hosting a `cmmc-compliance-analyst` agent backed by a **Phi-4** deployment (Microsoft IP, in Azure's compliance boundary). Picked over GPT-4o deliberately so the system has zero third-party model vendors in its supply chain, which matters when a CMMC assessor asks for a component inventory. Agent is created on first invocation if it doesn't exist.
- **Identity**: User-assigned managed identity, RBAC-scoped (`Storage Blob Data Contributor` on the storage account, `Azure AI Developer` on the Foundry project, `Security Reader` at subscription scope via a post-deploy `az role assignment`).
- **Output**: Markdown report per run, dropped in `reports/` container in Blob Storage AND emailed to the recipient set in `var.recipient_email` (default: `abdiemohamed.tech@gmail.com`).
- **Email**: Azure Communication Services Email with an Azure-managed sender domain (`donotreply@<random>.azurecomm.net`). No DNS verification required, no third-party email vendor (no SendGrid). Matches the same in-boundary supply-chain story as the Phi-4 model choice.
- **Static landing page**: Royal blue + white "GRC Engineering" page served from a dedicated storage account at `https://grcengineering<suffix>.z13.web.core.windows.net/`. Source in [web/index.html](web/index.html); served via Blob Storage's native static-website hosting (no separate web server or App Service).

## What's not in v1 (roadmap)

| Version | Adds |
|---|---|
| v2 | Customer-managed-key encryption via Key Vault. Move ACS connection string into Key Vault and switch ACS auth from connection string to managed identity. Per-run evidence bundle (JSON + Markdown + raw Defender response) with content hash for chain-of-custody. |
| v3 | Foundry agent tools (`get_findings`, `lookup_practice`, `write_report`) so the agent orchestrates instead of being called once. |
| v4 | Vector-store grounding on prior reports + CMMC Assessment Guide. Foundry Evaluations against a golden-set of past reports for groundedness and practice-mapping accuracy. |
| v5 | Multi-framework: add HIPAA (`HIPAA HITRUST`) and FedRAMP Moderate alongside CMMC L2. |

## Deploy

Prereqs: Azure CLI logged in (`az login`), Terraform 1.6+, an empty resource group, Defender for Cloud enabled with at least the NIST SP 800-171 Rev. 2 standard assigned to the subscription.

```bash
# 1. Create the resource group (one-time, manual so this module stays import-friendly)
az group create -n rg-aca -l eastus

# 2. Provision infra
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in the values
terraform init
terraform apply
```

After apply, grant the Function's MI **Security Reader at subscription scope** — Terraform deployed at RG scope can't grant this without elevated permissions, so run it once by hand:

```bash
SUB=$(az account show --query id -o tsv)
UAMI_OBJECT_ID=$(terraform -chdir=infra output -raw uami_principal_id)

az role assignment create \
  --assignee-object-id "$UAMI_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Security Reader" \
  --scope "/subscriptions/$SUB"
```

Publish the Function code:

```bash
cd src
func azure functionapp publish "$(terraform -chdir=../infra output -raw function_app_name)"
```

## Local development

```bash
cd src
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp local.settings.json.example local.settings.json
# Fill in the values from `terraform output`, then:
func start
```

The timer runs once a week in production. To force a manual run during development, hit the Functions admin endpoint or temporarily change the schedule in [function_app.py](src/function_app.py).

## Repo layout

```
.
├── infra/                      Terraform IaC
│   ├── providers.tf
│   ├── variables.tf
│   ├── main.tf                 All resources (flat layout, v1 doesn't need modules)
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── src/                        Python Functions v2 project root
│   ├── function_app.py         Timer-triggered entry point
│   ├── defender_client.py      Defender for Cloud regulatory compliance pull
│   ├── cmmc_mapper.py          Defender assessment -> CMMC L2 practice IDs
│   ├── analyst_agent.py        Foundry agent invocation
│   ├── report.py               Markdown report builder
│   ├── blob_writer.py          Writes the report to Blob via managed identity
│   ├── host.json
│   ├── requirements.txt
│   └── local.settings.json.example
├── config/
│   ├── frameworks.json
│   └── mappings/cmmc.json      Keyword-driven CMMC L2 practice mapping
└── docs/
    └── what-this-tool-does.md
```

## Things to know before you deploy

Gotchas surfaced during real `terraform apply` validation on Azure:

- **Phi model versions rotate.** Microsoft deprecates Phi versions periodically (the entire Phi-3 family was retired on 2025-08-30, mid-build). Run `az cognitiveservices model list --location <region> --query "[?model.format=='Microsoft'].{n:model.name, v:model.version, dep:model.deprecation.inference}"` to confirm current versions before applying.
- **Capacity unit differs by model family.** OpenAI deployments take capacity in thousands of TPM (50 = 50K TPM). Phi deployments take capacity in deployment units capped at 1. The default in this repo is 1 to match the more restrictive case.
- **AIServices needs `allowProjectManagement = true` for projects.** Microsoft added this in 2025. The `azurerm_ai_services` resource doesn't expose the flag, so we patch it via `azapi_update_resource.foundry_allow_projects`. Without it, child project creation 400s with "Project can only created under AIServices Kind account with allowProjectManagement set to true".
- **The Foundry agent RBAC role is `Azure AI Developer`, not `Azure AI User`.** Microsoft renamed it. Old name returns "could not find role" at apply.
- **Consumer / pay-as-you-go subs default `Total VMs` quota to 0.** Y1 consumption Function Apps need 1 VM unit under the hood; without quota you'll hit a 401 Unauthorized at `azurerm_service_plan` creation. Fix: Portal → Quotas → Compute → request increase for "Total Regional vCPUs" or "Standard BS Family". Takes minutes to hours depending on sub type.
- **Foundry SDK is moving fast.** The `azure-ai-projects` agent surface changed several times in 2024-2025. If `client.agents.threads.create()` errors at runtime, pin a known-good `azure-ai-projects` version.
- **Defender severity isn't native.** Assessments carry `state` (Passed / Failed / Skipped / Unsupported) but no severity. We synthesize a severity in [defender_client.py](src/defender_client.py) so the report can group by severity.
- **`default_tags` doesn't exist in azurerm.** A `common_tags` map is defined in `variables.tf` and merged into every resource.
- **`Y1` consumption cold-start.** The first invocation after a long idle period can take 10-20 seconds while the Foundry SDK loads. Premium (`EP1`) or Flex Consumption (`FC1`) eliminate this.
- **CMMC practice mapping is intentionally minimal in v1.** The mapping JSON has ~16 keyword groups. Real production use needs an org-curated mapping reviewed by someone who knows the CMMC Assessment Guide.

## License

MIT.
