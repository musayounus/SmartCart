resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = local.name }
}

# The docker-compose "db" service, in managed form. Same engine major version
# as local, so the row-locking behaviour the application depends on is
# identical in both places.
resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "16"

  # t3 rather than the cheaper Graviton t4g: db.t4g.micro is not orderable for
  # Postgres 16 in ap-south-1 at all -- describe-orderable-db-instance-options
  # returns zero offerings for it, and CreateDBInstance fails with
  # InsufficientDBInstanceCapacity rather than a clear "unsupported". Same
  # size (2 vCPU burstable, 1 GiB); check t4g availability again if the region
  # changes, since it is the cheaper option where offered.
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "smartcart"
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false

  # Single AZ and a short backup window: this is a demo stack. Production
  # would set multi_az, a longer retention, and deletion protection.
  multi_az                = false
  backup_retention_period = 1
  skip_final_snapshot     = true
  deletion_protection     = false

  tags = { Name = local.name }
}
