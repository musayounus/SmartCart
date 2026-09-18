#!/usr/bin/env bash
# Put the shelf back to its seeded levels.
#
#   AWS_PROFILE=smartcart ./scripts/reset-demo-stock.sh     # the deployed stack
#   ./scripts/reset-demo-stock.sh --local                   # docker compose
#
# Restarting the stack does NOT restock: seed_products uses ON CONFLICT DO
# NOTHING, so it fills an empty catalog and leaves existing rows alone. Without
# this script the only way back was `docker compose down -v`, which also wipes
# the seeded order history.
#
# Order history is deliberately left alone either way -- it feeds the
# recommendations endpoint, and clearing it would quietly remove a working part
# of the demo.
#
# Remotely there is no admin endpoint by design and RDS sits in a private
# subnet, so the reset runs from inside the VPC: a one-off ECS task reusing the
# existing task definition with its uvicorn command overridden. The container
# already has Python, the app package, and DATABASE_URL from Secrets Manager.
set -euo pipefail

CLUSTER=${CLUSTER:-smartcart-demo}
REGION=${AWS_REGION:-ap-south-1}
LOCAL=""
[ "${1:-}" = "--local" ] && LOCAL=1

# Defined once and used by both paths, so the two can never drift apart.
RESET_PY='
import asyncio
from sqlalchemy import update
from app.db import SessionLocal, engine
from app.models import Product
from app.seed import SEED_PRODUCTS

async def main():
    async with SessionLocal() as session:
        for row in SEED_PRODUCTS:
            await session.execute(
                update(Product)
                .where(Product.name == row["name"])
                .values(stock_quantity=row["stock_quantity"])
            )
        await session.commit()
    await engine.dispose()
    print("stock reset to seeded levels")

asyncio.run(main())
'

show_stock() {
  echo "Done. Current stock:"
  curl -s --max-time 20 "$1/products" | python -c "
import sys, json
for p in json.load(sys.stdin):
    print(f\"  {p['name']:<22} {p['stock_quantity']:>3}\")"
}

if [ -n "$LOCAL" ]; then
  # The venv, because the app package and its dependencies live there. app.db
  # reads settings.database_url, which picks up .env -- so this follows
  # whatever host port docker-compose publishes.
  if [ -x venv/Scripts/python.exe ]; then
    PY=venv/Scripts/python.exe
  elif [ -x venv/bin/python ]; then
    PY=venv/bin/python
  else
    echo "No project venv found. Create one and 'pip install -e \".[dev]\"'." >&2
    exit 1
  fi

  echo "Resetting the local database..."
  "$PY" -c "$RESET_PY"
  show_stock "http://localhost:8000"
  exit 0
fi

echo "Finding the deployed network by tag rather than hardcoding ids..."

SUBNETS=$(aws ec2 describe-subnets --region "$REGION" \
  --filters "Name=tag:Name,Values=${CLUSTER}-public-*" \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')

SG=$(aws ec2 describe-security-groups --region "$REGION" \
  --filters "Name=group-name,Values=${CLUSTER}-task" \
  --query 'SecurityGroups[0].GroupId' --output text)

if [ -z "$SUBNETS" ] || [ "$SG" = "None" ]; then
  echo "Could not find the network for cluster '$CLUSTER' in $REGION." >&2
  exit 1
fi

echo "Launching the reset task..."

TASK_ARN=$(aws ecs run-task --region "$REGION" \
  --cluster "$CLUSTER" \
  --task-definition "$CLUSTER" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides "$(python -c "
import json, sys
print(json.dumps({'containerOverrides': [{'name': 'api', 'command': ['python', '-c', sys.argv[1]]}]}))
" "$RESET_PY")" \
  --query 'tasks[0].taskArn' --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
  echo "run-task did not return a task ARN." >&2
  exit 1
fi

echo "Waiting for it to finish..."
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN"

# The task runs two containers; only the api one did the work. The web
# container exits on its own and its code is not interesting.
EXIT_CODE=$(aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].containers[?name==`api`].exitCode' --output text)
REASON=$(aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].stoppedReason' --output text)

if [ "$EXIT_CODE" != "0" ]; then
  echo "Reset failed. api container exit code: $EXIT_CODE ($REASON)" >&2
  echo "Logs: aws logs tail /ecs/$CLUSTER --since 5m --region $REGION" >&2
  exit 1
fi

DNS=$(aws elbv2 describe-load-balancers --region "$REGION" --names "$CLUSTER" \
  --query 'LoadBalancers[0].DNSName' --output text)

show_stock "http://${DNS}/api"
