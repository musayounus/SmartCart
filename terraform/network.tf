resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = local.name }
}

# Public subnets hold the load balancer and the application tasks.
resource "aws_subnet" "public" {
  count = length(local.azs)

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${local.name}-public-${local.azs[count.index]}" }
}

# Private subnets hold the database and the cache. Neither is routable from
# the internet: there is no NAT and no internet gateway route here, so these
# subnets can only talk within the VPC.
resource "aws_subnet" "private" {
  count = length(local.azs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + length(local.azs))
  availability_zone = local.azs[count.index]

  tags = { Name = "${local.name}-private-${local.azs[count.index]}" }
}

# No NAT gateway. It was the largest line item in the bill (~$33/month) and
# existed only so tasks in private subnets could reach ECR and CloudWatch.
# Tasks now run in public subnets with a public IP for egress, while inbound
# stays restricted to the load balancer's security group -- so the reachable
# surface is unchanged and the data stores stay private.
#
# VPC interface endpoints for ECR, logs and S3 are the textbook alternative
# and keep tasks fully private, but four of them cost about as much as the NAT
# they replace. Worth the trade at production traffic, not at demo traffic.

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name}-private" }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Security groups are chained: only the load balancer may reach the tasks, and
# only the tasks may reach the database and cache. No rule below uses a CIDR
# block, so widening a subnet cannot accidentally widen access.
resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Public entry point"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-alb" }
}

resource "aws_security_group" "task" {
  name        = "${local.name}-task"
  description = "Application tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Frontend port, load balancer only"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-task" }
}

resource "aws_security_group" "database" {
  name        = "${local.name}-db"
  description = "PostgreSQL, reachable only from the application tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from tasks only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.task.id]
  }

  tags = { Name = "${local.name}-db" }
}

resource "aws_security_group" "cache" {
  name        = "${local.name}-cache"
  description = "Redis, reachable only from the application tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from tasks only"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.task.id]
  }

  tags = { Name = "${local.name}-cache" }
}
