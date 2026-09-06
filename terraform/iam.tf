data "aws_caller_identity" "current" {}

# Assumed by the Fargate runtime to pull images, write logs, and fetch the
# connection string. The containers themselves call no AWS APIs, so there is
# deliberately no task role.
resource "aws_iam_role" "execution" {
  name = "${local.name}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs-tasks.amazonaws.com" }

      # Confused deputy protection. Without these, any ECS task in any account
      # that somehow referenced this role ARN could assume it; these pin the
      # caller to tasks in this account and region.
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:*"
        }
      }
    }]
  })
}

# Written out rather than attaching AmazonECSTaskExecutionRolePolicy, which
# grants its ECR and logs actions on Resource "*". Everything here is scoped
# to the two repositories, the one log group, and the one secret this stack
# actually uses.
resource "aws_iam_role_policy" "execution" {
  name = "${local.name}-execution"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "EcrAuthToken"
        # GetAuthorizationToken is account-wide by definition: it takes no
        # resource, so "*" is the only valid value rather than a shortcut.
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "PullOurImagesOnly"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = [
          aws_ecr_repository.api.arn,
          aws_ecr_repository.web.arn,
        ]
      },
      {
        Sid      = "WriteOurLogGroupOnly"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.app.arn}:*"
      },
      {
        Sid      = "ReadTheConnectionStringOnly"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.database_url.arn
      },
    ]
  })
}
