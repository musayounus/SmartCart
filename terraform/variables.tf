variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "me-south-1" # Bahrain: closest region to Jeddah.
}

variable "environment" {
  description = "Environment name, used as a suffix on resource names."
  type        = string
  default     = "demo"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_username" {
  description = "Master username for the RDS instance."
  type        = string
  default     = "smartcart"
}

variable "db_password" {
  description = <<-EOT
    Master password for the RDS instance. Deliberately has no default so it
    cannot be committed. Supply it at plan time via TF_VAR_db_password.
    In production this would come from Secrets Manager rather than a variable.
  EOT
  type        = string
  sensitive   = true
}

variable "container_image" {
  description = "Image the ECS task runs. Defaults to the ECR repository this stack creates."
  type        = string
  default     = ""
}

variable "desired_count" {
  description = "Number of Fargate tasks to run."
  type        = number
  default     = 1
}
