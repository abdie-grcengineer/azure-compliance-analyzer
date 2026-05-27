# Changelog

## [Unreleased]

### v1 — Initial release
- Terraform IaC (azurerm 4.x + azapi 2.x) for Storage, Log Analytics + App Insights, Azure AI Foundry account + project + model deployment, Linux consumption Function App + user-assigned managed identity.
- Python Function (timer trigger, weekly) that pulls Defender for Cloud regulatory compliance assessments for NIST SP 800-171 Rev. 2 (CMMC L2's underlying control set), maps each to CMMC L2 practice IDs via a JSON-driven keyword mapper, invokes an Azure AI Foundry agent for narrative generation, and writes the Markdown report to Blob Storage.
- RBAC via managed identity: Storage Blob Data Contributor (storage scope), Azure AI User (Foundry project scope), Security Reader (subscription scope, post-deploy manual step).
- Static landing page: dedicated storage account with native Blob static-website hosting serving a single-page royal blue + white "GRC Engineering" landing.
- Foundry model: **Phi-4** (Microsoft IP). Chosen deliberately for CMMC supply-chain reasons (keeps every system component inside Microsoft's compliance boundary, no third-party model vendor added). Parameterized via `foundry_model_name` / `foundry_model_format` so swapping to GPT-4o or other Foundry models is a tfvars change.
- Email delivery: Azure Communication Services Email with an Azure-managed sender domain. Same in-boundary rationale as the Phi-4 model choice (no SendGrid / no third-party email vendor). Recipient set via `var.recipient_email`. v1 auths via connection string in app settings; v2 will move that to Key Vault.
- Documentation: README with architecture diagram and roadmap, what-this-tool-does.md with the GRC Engineering framing.
