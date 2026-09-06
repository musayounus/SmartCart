# Holds the checkout rate-limit counters. This exists for correctness rather
# than speed: the in-process limiter allowed the full limit per task, so the
# effective limit scaled with instance count. Counting here makes the limit a
# property of the deployment.
#
# Deliberately not a read cache. The catalog is a handful of rows Postgres
# already serves from its own buffer cache, and HTTP validators remove those
# requests entirely rather than making them faster.
#
# Serverless rather than a cache.t4g.micro node: compute scales to zero
# between demos, it provisions in about a minute instead of five to ten, and
# there is no node type, engine version or parameter group to pin. Valkey is
# protocol compatible, so redis-py connects unchanged.
resource "aws_elasticache_serverless_cache" "main" {
  name   = local.name
  engine = "valkey"

  # Smallest allowed footprint. Rate-limit counters are a few bytes each and
  # expire within the window.
  cache_usage_limits {
    data_storage {
      maximum = 1
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 1000
    }
  }

  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.cache.id]

  tags = { Name = local.name }
}
