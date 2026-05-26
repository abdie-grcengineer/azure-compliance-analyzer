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
  description = "Short prefix used for resource names (lowercase, 3-12 chars, no dashes)."
  default     = "azmsdef"

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
  description = "Model to deploy in Azure AI Foundry for the GRC Analyst agent."
  default     = "gpt-4o"
}

variable "foundry_model_version" {
  type        = string
  description = "Model version for the Foundry deployment."
  default     = "2024-11-20"
}

variable "foundry_model_capacity" {
  type        = number
  description = "Capacity for the Foundry model deployment (thousands of tokens per minute)."
  default     = 50
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
