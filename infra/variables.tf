variable "location" {
  type    = string
  default = "eastus2"
}

variable "resource_group_name" {
  type    = string
  default = "rg-aichat-prod"
}

variable "shared_resource_group_name" {
  type    = string
  default = "rg-tf-backend"
}

variable "acr_name" {
  type = string
}

variable "developer_object_id" {
  type = string
}

variable "image_tag" {
  type = string
}

variable "model_name" {
  type    = string
  default = "gpt-5-nano"
}

variable "model_capacity" {
  type    = number
  default = 10
}

variable "model_version" {
  type    = string
  default = "2025-08-07"
}

variable "alert_email" {
  type = string
}


