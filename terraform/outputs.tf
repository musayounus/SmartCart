output "api_url" {
  description = "Public entry point for the API."
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_api_repository_url" {
  description = "Push the API image here."
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_web_repository_url" {
  description = "Push the frontend image here."
  value       = aws_ecr_repository.web.repository_url
}

output "database_endpoint" {
  description = "RDS endpoint. Private: reachable only from inside the VPC."
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}
