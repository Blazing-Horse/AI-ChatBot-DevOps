data "azurerm_resource_group" "app" {
  name = var.resource_group_name
}

data "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = var.shared_resource_group_name
}

data "azurerm_client_config" "current" {}

resource "random_string" "rebuild" {
  length  = 4
  upper   = false
  special = false
}

resource "azurerm_user_assigned_identity" "app" {
  name                = "id-aichat-api"
  location            = var.location
  resource_group_name = var.resource_group_name

}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "ai-workspace-${random_string.rebuild.result}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.15
}

resource "azurerm_application_insights" "main" {
  name                = "ai-appinsight-${random_string.rebuild.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "other"
}

resource "azurerm_key_vault" "main" {
  name                       = "kv-aichat${random_string.rebuild.result}"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  sku_name                   = "standard"
  purge_protection_enabled   = false

}

resource "azurerm_role_assignment" "pipeline_kv_officer" {
  scope                = azurerm_key_vault.main.id
  principal_id         = data.azurerm_client_config.current.object_id
  role_definition_name = "Key Vault Secrets Officer"
}

resource "azurerm_role_assignment" "app_kv_user" {
  scope                = azurerm_key_vault.main.id
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  role_definition_name = "Key Vault Secrets User"
  principal_type       = "ServicePrincipal"
}

resource "time_sleep" "wait_for_kv_roles" {
  create_duration = "120s"
  depends_on = [
    azurerm_role_assignment.pipeline_kv_officer,
    azurerm_role_assignment.app_kv_user,
  ]
}

resource "azurerm_key_vault_secret" "app_insight" {
  name         = "azure-app-connection-string"
  key_vault_id = azurerm_key_vault.main.id
  value        = azurerm_application_insights.main.connection_string
  depends_on   = [time_sleep.wait_for_kv_roles]
}

resource "azurerm_cognitive_account" "foundry" {
  name                       = "aif-account-${random_string.rebuild.result}"
  location                   = var.location
  kind                       = "AIServices"
  sku_name                   = "S0"
  resource_group_name        = var.resource_group_name
  custom_subdomain_name      = "aif-account-${random_string.rebuild.result}"
  project_management_enabled = true
  local_auth_enabled         = false

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_account_project" "main" {
  name                 = "chatbot"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = var.location
  display_name         = "AI Chat Bot"
  description          = "GPT Nano 5 Power"
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "app" {
  name                 = "ai-chatbot"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.model_capacity
  }

}

resource "azurerm_role_assignment" "app_usage" {
  role_definition_name = "Cognitive Services OpenAI User"
  scope                = azurerm_cognitive_account.foundry.id
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "developer_openai_user" {
  count                = var.developer_object_id == "" ? 0 : 1
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = var.developer_object_id
  principal_type       = "User"
}

resource "azurerm_cosmosdb_account" "main" {
  name                         = "cosmodb-account-${random_string.rebuild.result}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  offer_type                   = "Standard"
  kind                         = "GlobalDocumentDB"
  free_tier_enabled            = true
  local_authentication_enabled = false

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "chatbot" {
  name                = "chatbot"
  account_name        = azurerm_cosmosdb_account.main.name
  resource_group_name = var.resource_group_name
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "messages" {
  name                = "messages"
  database_name       = azurerm_cosmosdb_sql_database.chatbot.name
  account_name        = azurerm_cosmosdb_account.main.name
  partition_key_paths = ["/sessionId"]
  default_ttl         = 2592000
  resource_group_name = var.resource_group_name
}

resource "azurerm_cosmosdb_sql_role_assignment" "app" {
  scope               = azurerm_cosmosdb_account.main.id
  principal_id        = azurerm_user_assigned_identity.app.principal_id
  role_definition_id  = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  account_name        = azurerm_cosmosdb_account.main.name
  resource_group_name = var.resource_group_name
}

resource "azurerm_cosmosdb_sql_role_assignment" "developer" {
  count               = var.developer_object_id == "" ? 0 : 1
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = var.developer_object_id
  scope               = azurerm_cosmosdb_account.main.id
}

resource "azurerm_static_web_app" "app" {
  name                = "swa-aichatbot-${random_string.rebuild.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_size            = "Free"
  sku_tier            = "Free"
}

resource "azurerm_role_assignment" "acr_api_pull" {
  scope                = data.azurerm_container_registry.acr.id
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  principal_type       = "ServicePrincipal"
  role_definition_name = "AcrPull"
}

resource "time_sleep" "wait_for_app_roles" {
  create_duration = "60s"
  depends_on = [
    azurerm_role_assignment.acr_api_pull,
    azurerm_role_assignment.app_usage,
    azurerm_cosmosdb_sql_role_assignment.app,
  ]
}
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-aichat"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  logs_destination           = "log-analytics"

}

resource "azurerm_container_app" "main" {
  name                         = "aca-aichat"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = data.azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "appinsight-connection-string"
    key_vault_secret_id = azurerm_key_vault_secret.app_insight.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }
  ingress {
    target_port      = 8000
    external_enabled = true
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
    cors {
      allowed_origins = ["https://${azurerm_static_web_app.app.default_host_name}"]
      allowed_methods = ["GET", "POST", "OPTIONS"]
      allowed_headers = ["Content-Type"]
    }
  }
  template {
    min_replicas = 0
    max_replicas = 2
    container {
      name   = "api"
      image  = "${data.azurerm_container_registry.acr.login_server}/chatbot:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }
      env {
        name  = "AZURE_OPENAI_BASE_URL"
        value = "https://${azurerm_cognitive_account.foundry.custom_subdomain_name}.openai.azure.com/openai/v1/"
      }
      env {
        name  = "MODEL_DEPLOYMENT_NAME"
        value = var.model_name
      }
      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.main.endpoint
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsight-connection-string"
      }
      readiness_probe {
        port      = 8000
        path      = "/health"
        transport = "HTTP"
      }
    }
  }
  depends_on = [time_sleep.wait_for_app_roles]
}

resource "azurerm_monitor_action_group" "message" {
  name                = "aichat"
  resource_group_name = var.resource_group_name
  short_name          = "AI alert"

  email_receiver {
    email_address = var.alert_email
    name          = "owner"
  }

}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "alert" {
  name                 = "alert_rule"
  resource_group_name  = var.resource_group_name
  location             = var.location
  scopes               = [azurerm_application_insights.main.id]
  severity             = 2
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"
  description          = "More than 5% chat requests failed in 5 minutes"
  criteria {
    query = <<-QUERY
    request
    | summarize total = count(), failed = countif(success == false)
    | extend failure_rate = iff(total == 0, 0.0, 100.0 * failed / total)
    | project failure_rate
    QUERY

    time_aggregation_method = "Maximum"
    metric_measure_column   = "failure_rate"
    operator                = "GreaterThan"
    threshold               = 5

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }
  action {
    action_groups = [azurerm_monitor_action_group.message.id]
  }
}
