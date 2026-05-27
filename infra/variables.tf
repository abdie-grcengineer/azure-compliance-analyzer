variable "resource_group_name" {
  type        = string
  description = "Resource group that hosts every resource this module creates."
}

variable "location" {
  type        = string
  description = "Azure region for all resources."
  default     = "eastus"
}

variable "project_name" {
  type        = string
  description = "Short prefix used for Azure resource names (lowercase, 3-12 chars, no dashes). Defaults to 'aca' (azure-compliance-analyzer). Changing this after deploy forces destroy/recreate of every resource."
  default     = "aca"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.project_name))
    error_message = "project_name must be 3-12 lowercase alphanumeric characters."
  }
}

variable "environment" {
  type        = string
  description = "Environment tag value (demo, dev, prod, etc)."
  default     = "demo"
}

variable "foundry_model_name" {
  type        = string
  description = "Model to deploy in Azure AI Foundry for the CMMC Analyst agent. Default is Phi-4 (Microsoft IP, in-boundary, 14B params, no third-party vendor added to the CMMC supply chain). The Phi-3 family was deprecated on 2025-08-30 so don't fall back there. Swap to gpt-4o (with foundry_model_format='OpenAI') for stronger narrative quality at the cost of OpenAI showing up in your component inventory."
  default     = "Phi-4"
}

variable "foundry_model_version" {
  type        = string
  description = "Model version for the Foundry deployment. Verify the latest non-deprecated version: az cognitiveservices model list --location <region> --query \"[?model.name=='Phi-4'].{v:model.version, dep:model.deprecation.inference}\""
  default     = "3"
}

variable "foundry_model_format" {
  type        = string
  description = "Model publisher format for the cognitive deployment. 'Microsoft' for Phi family, 'OpenAI' for GPT family."
  default     = "Microsoft"
}

variable "foundry_model_capacity" {
  type        = number
  description = "Capacity for the Foundry model deployment. Units differ by model family: OpenAI uses thousands of tokens per minute (50 = 50K TPM, typical), Phi-3 family uses deployment units capped at 1. Default is 1 to match the more restrictive case (Phi-3); bump to 50 if switching to gpt-4o."
  default     = 1
}

variable "defender_standard_name" {
  type        = string
  description = "Defender for Cloud regulatory compliance standard to pull. NIST SP 800-171 Rev. 2 is the underlying control set for CMMC L2."
  default     = "NIST SP 800-171 Rev. 2"
}

variable "common_tags" {
  type = map(string)
  description = "Tags applied to every resource. azurerm has no default_tags provider feature, so we pass this map to each resource explicitly."
  default = {
    Project         = "azure-compliance-analyzer"
    ManagedBy       = "terraform"
    ComplianceScope = "cmmc-l2"
  }
}
