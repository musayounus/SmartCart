terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "smartcart"
      ManagedBy = "terraform"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "smartcart-${var.environment}"

  # RDS subnet groups require at least two availability zones, so the network
  # is built across two even though a single task would otherwise fit in one.
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}
