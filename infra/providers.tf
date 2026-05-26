terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.20"
    }
    # AzAPI fills the gap for newer Azure resource types that azurerm hasn't
    # caught up with yet. We use it for the AI Foundry project resource,
    # which is a child of a Microsoft.CognitiveServices/accounts (kind=AIServices)
    # account and is currently most reliably created via the raw ARM API.
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "azapi" {}
