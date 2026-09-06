variable "region" {
  description = "AWS region to deploy into."
  type        = string
  # Bahrain (me-south-1) is closest to Jeddah and is enabled on this account,
  # but its endpoints are unreachable from the network this was deployed from.
  # Mumbai is the nearest reachable alternative at roughly 3,000km.
  default = "ap-south-1"
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

variable "desired_count" {
  description = <<-EOT
    Number of Fargate tasks. Two is safe only because the rate limiter counts
    in Redis; with the in-process limiter each task allowed the full limit.
  EOT
  type        = number
  default     = 2
}
