# v1 Deploy Lessons

Every pain point caught while building and live-deploying v1 of this stack. Categorized so the next person doesn't have to repeat the trip. All errors and fixes are real, not theoretical.

## Terraform / azurerm provider gaps

- **`azurerm_ai_services` is feature-frozen.** Plan emits a deprecation warning steering you to `azurerm_cognitive_account`. Still works for now but won't gain new properties.
- **Static-website inline block on `azurerm_storage_account` is deprecated.** Will be removed in azurerm v5. Should migrate to the standalone `azurerm_storage_account_static_website` resource.
- **`allowProjectManagement` isn't in the `azurerm_ai_services` schema.** Without it, Foundry project creation 400s with `"Project can only created under AIServices Kind account with allowProjectManagement set to true."` Microsoft added this requirement in 2025. Fix: `azapi_update_resource` to patch the property after account creation. See `azapi_update_resource.foundry_allow_projects` in [infra/main.tf](../infra/main.tf).
- **`linkedDomains` isn't in the `azurerm_communication_service` schema.** Without it, ACS Email send returns `"DomainNotLinked: The specified sender domain has not been linked."` Fix: another `azapi_update_resource` (see `azapi_update_resource.acs_link_domain`) to link the email domain.
- **`azurerm_cognitive_deployment` capacity unit is model-family-specific.** OpenAI deployments take K-TPM (50 = 50K TPM). Phi deployments take deployment units capped at 1. Got back `"InvalidCapacity: The specified capacity '50' of account deployment should be at least 1 and no more than 1."` Single integer field, totally different semantics across families.

## Azure subscription gates

- **`Total VMs` quota defaults to 0 on consumer / PAYG subs.** Even Y1 consumption Function Apps need 1 vCPU under the hood, so deploy fails with `"401 Unauthorized: Operation cannot be completed without additional quota. Current Limit (Total VMs): 0."` Fix is a portal quota request; not in any first-steps doc I saw.
- **Defender for Cloud regulatory compliance requires Defender Standard tier.** API returns `"Bad Request: Subscription with no standard pricing bundle. Regulatory compliance is not supported."` This is the actual data source the whole tool exists to read. ~$15/server/month minimum.
- **Each `terraform apply` failure cascaded.** Service Plan stuck on quota meant Function App couldn't deploy, which meant downstream role assignments and app settings didn't land. Five replans before everything else turned green.

## Model catalog churn

- **Phi-3 entire family deprecated 2025-08-30, mid-build.** Catalog still lists the versions for migration reference but won't accept new deployments. Error: `"ServiceModelDeprecated: The model 'Publisher:Microsoft,Format:Microsoft,Name:Phi-3-medium-128k-instruct,Version:7' has been deprecated since 08/30/2025."` Always re-check `az cognitiveservices model list` before applying.
- **Phi-4 version `1` doesn't exist.** Picked it as an obvious-looking default in tfvars. Error: `"DeploymentModelNotSupported: The model 'Format:Microsoft,Name:Phi-4,Version:1' of account deployment is not supported."` Available Phi-4 versions in eastus are 2 and 3.
- **Phi-4 isn't in every region as a standard cognitive deployment.** Microsoft serves it via serverless MaaS in selected regions only. Worth confirming the region's model catalog before picking it.

## SDK surface migrations

- **`azure-ai-projects` reshaped completely in 2.x.** Old `client.agents.create_agent` / `threads.create` / `messages.create` / `runs.create_and_process` pattern is gone. First hit: `AttributeError: 'AgentsOperations' object has no attribute 'list_agents'`. New pattern is OpenAI-compatible chat completions via `client.get_openai_client()`. Actually cleaner once you adjust.
- **`get_openai_client()` doesn't take `api_version`.** Returns a vanilla `openai.OpenAI` client, not `AzureOpenAI`. Error: `"TypeError: __init__() got an unexpected keyword argument 'api_version'"`. Drop the kwarg.
- **`>=1.0.0b6` in requirements.txt was the trap.** Open-ended `>=` ate the 2.x SDK release at install time, silently moving the API surface under code that targeted 1.x. Pin to a major version range (`>=2.1.0,<3.0`).
- **Python 3.9 vs 3.11 type-hint syntax.** `str | None` requires 3.10+. Function App runs 3.11 so production is fine, but a local 3.9 venv blew up at import. Fix: `from __future__ import annotations` so annotations are lazy-evaluated strings.

## RBAC / auth complexity

- **"Azure AI User" was renamed to "Azure AI Developer".** Old name returns `"Error: listing role definitions: could not find role 'Azure AI User'"` at apply time. No deprecation warning, just silent name failure.
- **Foundry chat completions need data-plane "Azure AI Developer".** Subscription Owner inheritance does NOT cover it. Error: `"401 PermissionDenied: The principal lacks the required data action Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action."` UAMI got it via Terraform; the user account did not, even though it owned the subscription.
- **Storage Blob Data Contributor on storage isn't inherited from Owner either.** Same data-plane vs management-plane split. Have to grant explicitly.
- **Only built-in ACS Email role is `Communication and Email Service Owner`.** Too broad for least-privilege MI auth. v1 ended up using connection-string auth and deferring MI + Key Vault to v2.
- **First-send to Gmail from `*.azurecomm.net` lands in spam.** Sender domain is unrecognized. Has to be marked Not Spam manually once to train Gmail for subsequent sends.

## Process / tooling friction

- **`terraform apply` partial-failure state.** Some resources created, others errored. Knowing which is which requires `terraform state list` cross-checked against `az ... list`. Cognitive deployment didn't show in either state OR in Azure after the first capacity-mismatch error, which made me think it had been wiped when it had just never been created.
- **Saved `tfplan` files got auto-committed.** Binary state-ish files in the repo. Caught it on the second commit; added `tfplan` and `tfplan*` to `.gitignore`.
- **Azure CLI extensions need a one-time prompt.** `az communication list-key` triggered `az config set extension.use_dynamic_install=yes_without_prompt` before working.
- **`--force-with-lease` rejects after a history rewrite.** `filter-branch` updates `refs/original/*` backup refs which then make the lease check fail against the remote. Plain `--force` was correct here.

## Meta-observations

- **Five "azurerm doesn't cover this, patch via azapi" patches.** `allowProjectManagement` + `linkedDomains` so far, plus likely future ones for CMK, private endpoints, etc. `azapi` is now a hard dep, not optional, when you're touching the newest surfaces.
- **Two "Microsoft renamed the thing" gotchas in one build.** Phi-3 deprecated, Azure AI User → Azure AI Developer. Cloud platforms churn faster than the docs do.
- **Each pain point was 5-15 minutes solo. Aggregate: an afternoon.** Documenting them here so the cost is paid once.
