output "function_app_name" {
  description = "Name of the deployed Function App. Use this with `func azure functionapp publish`."
  value       = azurerm_linux_function_app.func.name
}

output "uami_name" {
  description = "Name of the user-assigned managed identity (needed for the post-deploy Security Reader role assignment)."
  value       = azurerm_user_assigned_identity.uami.name
}

output "uami_principal_id" {
  description = "Principal (object) ID of the UAMI. Pass to `az role assignment create --assignee-object-id` for Security Reader at sub scope."
  value       = azurerm_user_assigned_identity.uami.principal_id
}

output "reports_container_url" {
  description = "URL of the blob container where weekly reports land."
  value       = "${azurerm_storage_account.storage.primary_blob_endpoint}${azurerm_storage_container.reports.name}"
}

output "foundry_project_endpoint" {
  description = "Foundry project endpoint used by the AIProjectClient in the Function."
  value       = "${azurerm_ai_services.foundry.endpoint}api/projects/${azapi_resource.foundry_project.name}"
}

output "subscription_id" {
  description = "Subscription ID the Function is scoped to for Defender queries."
  value       = data.azurerm_client_config.current.subscription_id
}

output "static_website_url" {
  description = "Public URL of the GRC Engineering static landing page."
  value       = azurerm_storage_account.website.primary_web_endpoint
}

output "report_sender_address" {
  description = "Azure-managed sender address the weekly report is delivered from."
  value       = "donotreply@${azurerm_email_communication_service_domain.azuremanaged.from_sender_domain}"
}

output "report_recipient" {
  description = "Email address that receives the weekly report."
  value       = var.recipient_email
}
