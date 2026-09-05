output "api_url" {
  description = "Public entry point for the API."
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "Push the application image here before scaling the service up."
  value       = aws_ecr_repository.app.repository_url
}

output "database_endpoint" {
  description = "RDS endpoint. Private: reachable only from inside the VPC."
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}
