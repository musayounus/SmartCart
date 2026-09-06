resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

# Holds the checkout rate-limit counters. This exists for correctness rather
# than speed: the in-process limiter allowed the full limit per task, so the
# effective limit scaled with instance count. Counting here makes the limit a
# property of the deployment.
#
# Deliberately not a read cache. The catalog is a handful of rows Postgres
# already serves from its own buffer cache, and HTTP validators remove those
# requests entirely rather than making them faster.
resource "aws_elasticache_cluster" "main" {
  cluster_id           = local.name
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.cache.id]

  tags = { Name = local.name }
}
