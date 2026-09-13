#!/usr/bin/env bash
# Build both images, push them to ECR, and roll the ECS service onto them.
#
# Terraform creates the ECR repositories but cannot fill them, and the task
# definition pins `:latest` -- so a fresh `terraform apply` leaves the service
# unable to pull and the tasks looping. This closes that gap:
#
#   terraform -chdir=terraform apply    # infrastructure
#   ./scripts/deploy.sh                 # images, then roll the service
#
# Repository URLs come from `terraform output` rather than being hardcoded,
# because destroying and re-applying produces a new load balancer DNS name and
# would otherwise silently push to the wrong place.
#
# Nothing about the environment is baked into either image: the frontend calls
# a relative `/api`, and the API reads its database URL from Secrets Manager at
# start. So the same image works against any deployment of this stack.
#
#   AWS_PROFILE=smartcart ./scripts/deploy.sh
set -euo pipefail

CLUSTER=${CLUSTER:-smartcart-demo}
REGION=${AWS_REGION:-ap-south-1}
TAG=${TAG:-latest}

command -v docker >/dev/null || {
  echo "docker is not on PATH. Start Docker Desktop and open a new terminal." >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "The Docker daemon is not responding. Is Docker Desktop running?" >&2
  exit 1
}

echo "Reading repository URLs from Terraform state..."

API_REPO=$(terraform -chdir=terraform output -raw ecr_api_repository_url 2>/dev/null || true)
WEB_REPO=$(terraform -chdir=terraform output -raw ecr_web_repository_url 2>/dev/null || true)

if [ -z "$API_REPO" ] || [ -z "$WEB_REPO" ]; then
  echo "No repository URLs in Terraform state." >&2
  echo "Run 'terraform -chdir=terraform apply' first, then this script." >&2
  exit 1
fi

# The registry host is the repo URL with the repository name stripped off.
REGISTRY=${API_REPO%%/*}

echo "Logging in to $REGISTRY..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

# --platform is explicit because the task definition pins X86_64; building on
# an arm64 machine would otherwise produce images ECS cannot run.
echo "Building the API image..."
docker build --platform linux/amd64 -t "${API_REPO}:${TAG}" .

echo "Building the web image..."
docker build --platform linux/amd64 -t "${WEB_REPO}:${TAG}" ./web

echo "Pushing both..."
docker push "${API_REPO}:${TAG}"
docker push "${WEB_REPO}:${TAG}"

# The tag is mutable, so ECS will not re-pull on its own -- the task definition
# is unchanged and it sees no reason to cycle. force-new-deployment is what
# makes it fetch the image we just pushed.
echo "Rolling the service onto the new images..."
aws ecs update-service --region "$REGION" \
  --cluster "$CLUSTER" --service "$CLUSTER" \
  --force-new-deployment >/dev/null

echo "Waiting for the service to reach a steady state (a few minutes)..."
if ! aws ecs wait services-stable --region "$REGION" \
  --cluster "$CLUSTER" --services "$CLUSTER"; then
  echo "The service did not stabilise. Check why the tasks are failing:" >&2
  echo "  aws ecs describe-services --cluster $CLUSTER --services $CLUSTER --region $REGION \\" >&2
  echo "    --query 'services[0].events[:5]'" >&2
  echo "  aws logs tail /ecs/$CLUSTER --since 10m --region $REGION" >&2
  exit 1
fi

DNS=$(aws elbv2 describe-load-balancers --region "$REGION" --names "$CLUSTER" \
  --query 'LoadBalancers[0].DNSName' --output text)

echo "Checking the deployment answers..."
HEALTH=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "http://${DNS}/api/health")
if [ "$HEALTH" != "200" ]; then
  echo "Deployed, but /api/health returned $HEALTH rather than 200." >&2
  exit 1
fi

echo
echo "Live at http://${DNS}"
echo
echo "NOTE: that DNS name changes every time the load balancer is recreated."
echo "      If it differs from the one in README.md, CLAUDE.md and"
echo "      docs/WALKTHROUGH.md, update all three."
echo
echo "Stock:"
curl -s --max-time 20 "http://${DNS}/api/products" | python -c "
import sys, json
for p in json.load(sys.stdin):
    print(f\"  {p['name']:<22} {p['stock_quantity']:>3}\")"
