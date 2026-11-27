output "api_url" {
  description = "Public address of the chat API."
  value       = "https://${azurerm_container_app.main.ingress[0].fqdn}"
}

output "web_url" {
  description = "Public address of the chat page."
  value       = "https://${azurerm_static_web_app.app.default_host_name}"
}

output "swa_api_key" {
  description = "Deployment token for the chat page. Used only by the pipeline."
  value       = azurerm_static_web_app.app.api_key
  sensitive   = true
}

output "openai_base_url" {
  value = "https://${azurerm_cognitive_account.foundry.custom_subdomain_name}.openai.azure.com/openai/v1/"
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}
