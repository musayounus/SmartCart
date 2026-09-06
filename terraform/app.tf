resource "aws_ecr_repository" "api" {
  name                 = "${local.name}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "web" {
  name                 = "${local.name}-web"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

resource "aws_ecs_cluster" "main" {
  name = local.name
}

# One task, two containers. They share a network namespace, so nginx reaches
# the API on 127.0.0.1 exactly as it reaches it by service name under compose
# -- no service discovery, and no path rewriting at the load balancer, which
# ALB cannot do anyway.
#
# The trade is that the frontend and API scale together. They would anyway:
# adding tasks does not relieve checkout contention, since that queues on a
# Postgres row lock rather than on application CPU.
resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn

  # Stated rather than left to default. ARM64 would be roughly 20% cheaper on
  # Fargate, but the images are built on an x86 machine; switching means
  # building multi-arch first.
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:latest"
      essential = true

      portMappings = [{ containerPort = 8000, protocol = "tcp" }]

      # Serverless ElastiCache requires TLS, hence rediss rather than redis.
      environment = [{
        name  = "REDIS_URL"
        value = "rediss://${aws_elasticache_serverless_cache.main.endpoint[0].address}:${aws_elasticache_serverless_cache.main.endpoint[0].port}/0"
      }]

      # Injected at container start rather than sitting in the task
      # definition, so the password is not readable from the ECS console or
      # describe-task-definition.
      secrets = [{
        name      = "DATABASE_URL"
        valueFrom = aws_secretsmanager_secret.database_url.arn
      }]

      # Gives nginx something to wait on. /health runs SELECT 1, so healthy
      # here means the database link is up, not merely that the process
      # started.
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"]
        interval    = 10
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      # Time to finish in-flight checkouts before SIGKILL.
      stopTimeout = 30

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "api"
        }
      }
    },
    {
      name      = "web"
      image     = "${aws_ecr_repository.web.repository_url}:latest"
      essential = true

      portMappings = [{ containerPort = 80, protocol = "tcp" }]

      environment = [
        { name = "API_UPSTREAM", value = "127.0.0.1:8000" },
        { name = "NGINX_ENVSUBST_FILTER", value = "API_UPSTREAM" },
      ]

      # HEALTHY, not START: nginx starting before the API can answer would
      # fail load balancer health checks and cycle the task.
      dependsOn = [{ containerName = "api", condition = "HEALTHY" }]

      stopTimeout = 30

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "web"
        }
      }
    },
  ])
}

resource "aws_lb" "main" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

# The load balancer is here for ingress, not for distributing load: Fargate
# tasks get a new private IP on every deploy, so this is what provides a
# stable address, health-based removal, and somewhere to terminate TLS.
resource "aws_lb_target_group" "app" {
  name        = local.name
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  # Checks the API through nginx, and /health executes SELECT 1, so a task
  # with a broken database link leaves rotation instead of serving errors.
  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 15
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_ecs_service" "app" {
  name             = local.name
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.app.arn
  desired_count    = var.desired_count
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  # Public subnets with a public IP, because there is no NAT gateway. Inbound
  # is still restricted to the load balancer by the task security group.
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "web"
    container_port   = 80
  }

  depends_on = [aws_lb_listener.http]
}
