# =============================================================================
# azure-compliance-analyzer - v1 infrastructure
#
# Provisions the full stack:
#   - Storage Account + Blob containers (reports, config)
#   - Log Analytics workspace + Application Insights
#   - Azure AI Foundry: AIServices account + project + model deployment
#   - Linux consumption Function App + user-assigned managed identity
#   - RBAC: Storage Blob Data Contributor (storage scope), Azure AI User
#     (Foundry project scope). Security Reader at subscription scope is
#     granted via a post-deploy `az role assignment` (see README).
# =============================================================================

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

locals {
  suffix       = random_string.suffix.result
  name_prefix  = "${var.project_name}-${local.suffix}"
  storage_name = substr("${var.project_name}${local.suffix}", 0, 24)

  tags = merge(var.common_tags, {
    Environment = var.environment
  })
}

# === Observability ===========================================================

resource "azurerm_log_analytics_workspace" "law" {
  name                = "${local.name_prefix}-law"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "ai" {
  name                = "${local.name_prefix}-ai"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
  tags                = local.tags
}

# === Storage =================================================================

resource "azurerm_storage_account" "storage" {
  name                          = local.storage_name
  resource_group_name           = data.azurerm_resource_group.rg.name
  location                      = var.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  account_kind                  = "StorageV2"
  min_tls_version               = "TLS1_2"
  allow_nested_items_to_be_public = false
  https_traffic_only_enabled    = true

  blob_properties {
    versioning_enabled = true
  }

  tags = local.tags
}

resource "azurerm_storage_container" "reports" {
  name                  = "reports"
  storage_account_id    = azurerm_storage_account.storage.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "config" {
  name                  = "config"
  storage_account_id    = azurerm_storage_account.storage.id
  container_access_type = "private"
}

# === Azure AI Foundry ========================================================

# AIServices account: the "Foundry hub" in the current (post-2024) model.
# Gives you unified access to chat completions, agents, embeddings, and
# content safety behind one endpoint.
resource "azurerm_ai_services" "foundry" {
  name                  = "${local.name_prefix}-foundry"
  resource_group_name   = data.azurerm_resource_group.rg.name
  location              = var.location
  sku_name              = "S0"
  custom_subdomain_name = "${local.name_prefix}-foundry"

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

# Foundry project. Child of the AIServices account. azurerm doesn't yet
# cover this resource shape cleanly, so we go through azapi to talk to the
# raw ARM API.
resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = "grc-analyst"
  parent_id = azurerm_ai_services.foundry.id
  location  = var.location

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = "GRC Analyst"
      description = "Foundry project hosting the CMMC Compliance Analyst agent for Defender for Cloud findings."
    }
  }

  response_export_values = ["id", "name"]
}

# Model deployment lives on the account, not the project. The agent we
# create at runtime references it by name.
#
# v1 default: Phi-4 (Microsoft IP). Picked deliberately for CMMC reasons:
# keeping every component of the system inside Microsoft's compliance
# boundary means zero additional third-party vendor review when an
# assessor asks "who built every component that processes your
# CUI-adjacent data?". GPT-4o would give better narrative polish but
# adds OpenAI to the supply chain inventory.
#
# NOTE: Microsoft has shifted Phi between standard cognitive deployments
# and serverless MaaS endpoints over time. If `terraform apply` errors
# on this resource, check the Foundry portal model catalog for the
# current name/version/format strings and update the variables.
resource "azurerm_cognitive_deployment" "model" {
  name                 = var.foundry_model_name
  cognitive_account_id = azurerm_ai_services.foundry.id

  model {
    format  = var.foundry_model_format
    name    = var.foundry_model_name
    version = var.foundry_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.foundry_model_capacity
  }
}

# === Function App + Managed Identity =========================================

# User-assigned MI (not system-assigned) so we can reference principal_id
# in role assignments before the Function App resource exists.
resource "azurerm_user_assigned_identity" "uami" {
  name                = "${local.name_prefix}-uami"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  tags                = local.tags
}

# Y1 Linux consumption plan. Cheapest option. Cold-start on consumption
# can be slow when the Function imports the Foundry SDK on first run; if
# that becomes a problem, switch to Flex Consumption (FC1) or Premium.
resource "azurerm_service_plan" "plan" {
  name                = "${local.name_prefix}-plan"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = local.tags
}

resource "azurerm_linux_function_app" "func" {
  name                = "${local.name_prefix}-func"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = var.location
  service_plan_id     = azurerm_service_plan.plan.id

  storage_account_name       = azurerm_storage_account.storage.name
  storage_account_access_key = azurerm_storage_account.storage.primary_access_key

  https_only = true

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.uami.id]
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
    ftps_state            = "Disabled"
    minimum_tls_version   = "1.2"
    application_insights_connection_string = azurerm_application_insights.ai.connection_string
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME = "python"

    # DefaultAzureCredential reads AZURE_CLIENT_ID to pick the UAMI when
    # multiple identities are attached to the Function App.
    AZURE_CLIENT_ID = azurerm_user_assigned_identity.uami.client_id

    FOUNDRY_PROJECT_ENDPOINT = "${azurerm_ai_services.foundry.endpoint}api/projects/${azapi_resource.foundry_project.name}"
    FOUNDRY_AGENT_MODEL      = var.foundry_model_name

    REPORTS_STORAGE_ACCOUNT = azurerm_storage_account.storage.name
    REPORTS_CONTAINER       = azurerm_storage_container.reports.name

    DEFENDER_STANDARD = var.defender_standard_name
    DEFENDER_HOURS    = "168"
    SUBSCRIPTION_ID   = data.azurerm_client_config.current.subscription_id
  }

  tags = local.tags
}

# === RBAC ====================================================================

# Storage Blob Data Contributor on the storage account: lets the Function's
# MI write report Markdown to the `reports` container via Entra ID.
resource "azurerm_role_assignment" "storage_blob" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.uami.principal_id
}

# Azure AI User on the Foundry project: lets the Function's MI create and
# invoke agents, create threads, send messages, and read runs.
resource "azurerm_role_assignment" "foundry_ai_user" {
  scope                = azapi_resource.foundry_project.id
  role_definition_name = "Azure AI User"
  principal_id         = azurerm_user_assigned_identity.uami.principal_id
}

# === Static website ==========================================================
#
# Dedicated storage account for the public GRC Engineering landing page.
# Separate from the analyzer's data storage so the URL reads as
# `grcengineering<suffix>.z13.web.core.windows.net` and so destroying or
# rebuilding the site never touches the compliance evidence container.
#
# Storage account names must be 3-24 chars, lowercase alphanumeric, globally
# unique. "grcengineering" (14) + 6-char suffix = 20 chars; under the limit.

resource "azurerm_storage_account" "website" {
  name                            = "grcengineering${local.suffix}"
  resource_group_name             = data.azurerm_resource_group.rg.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  https_traffic_only_enabled      = true

  # Enabling static_website auto-creates the special `$web` container and
  # exposes the *.z13.web.core.windows.net endpoint. The endpoint serves
  # blobs in $web publicly regardless of the allow_nested_items_to_be_public
  # flag, so we can keep direct blob access locked down.
  static_website {
    index_document     = "index.html"
    error_404_document = "index.html"
  }

  tags = local.tags
}

resource "azurerm_storage_blob" "index_html" {
  name                   = "index.html"
  storage_account_name   = azurerm_storage_account.website.name
  storage_container_name = "$web"
  type                   = "Block"
  content_type           = "text/html"
  source                 = "${path.module}/../web/index.html"
  # MD5 of the source file forces re-upload whenever the HTML changes.
  content_md5            = filemd5("${path.module}/../web/index.html")
}
