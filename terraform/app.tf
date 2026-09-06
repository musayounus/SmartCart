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

# Pulls images and writes logs. The containers themselves need no AWS
# permissions, so there is deliberately no task_role_arn.
resource "aws_iam_role" "execution" {
  name = "${local.name}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
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

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:latest"
      essential = true

      portMappings = [{ containerPort = 8000, protocol = "tcp" }]

      environment = [
        {
          name = "DATABASE_URL"
          # Reachable only inside the VPC. In production this would come from
          # Secrets Manager rather than sitting in the task definition.
          value = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.endpoint}/smartcart"
        },
        {
          name  = "REDIS_URL"
          value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379/0"
        },
      ]

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

      dependsOn = [{ containerName = "api", condition = "START" }]

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
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

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
