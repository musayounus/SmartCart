# The connection string, kept out of the task definition.
#
# ECS injects this at container start via the `secrets` field rather than
# `environment`, so the password is not visible in the task definition, in
# `describe-task-definition` output, or to anyone with read access to the ECS
# console.
#
# Knowingly not done, and disproportionate for a demo: a dedicated customer
# managed KMS key with a `kms:ViaService` scoped key policy, and a rotation
# Lambda. Both are in the AWS guidance for production secrets.
#
# Also worth naming plainly: the password still passes through Terraform
# state, which is inherent to `password` on `aws_db_instance`. The way out is
# `manage_master_user_password`, which has RDS create and rotate the secret
# itself so the value never reaches Terraform -- it needs the application to
# assemble its URL from parts rather than take one string, which is the next
# step rather than one taken here.
resource "aws_secretsmanager_secret" "database_url" {
  name = "${local.name}-database-url"

  # No recovery window, so tearing the stack down and rebuilding it does not
  # collide with a scheduled-for-deletion secret of the same name.
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = join("", [
    "postgresql+asyncpg://",
    var.db_username, ":", var.db_password,
    "@", aws_db_instance.main.endpoint, "/smartcart",
  ])
}
