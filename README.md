# SmartCart

A small grocery ordering API — browse products, add to a cart, check out —
built around one hard requirement: **concurrent checkouts competing for the
last units of stock must never oversell.**

> Scaffolding stage. Catalog, cart, and checkout are not implemented yet;
> the sections marked _TBD_ fill in as each slice lands.

## Running it

```bash
docker compose up --build
```

Then open <http://localhost:8000/docs> for the interactive API docs.

The API listens on port 8000 and Postgres on 5432. Nothing else is required —
no manual database creation, no migration step.

## Testing

The suite needs a Postgres instance. With the stack already up:

```bash
docker compose exec api pytest -v
```

Or against a local Postgres, outside Docker:

```bash
pip install -e ".[dev]"
cp .env.example .env
pytest -v
```

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, and proves the database link is live. |

_Catalog, cart, and checkout endpoints: TBD._

## Data model

_TBD._

## Architecture

_TBD._

## Concurrency safety

The core of the project. _TBD._

## Deployment

Terraform describing an ECS Fargate + RDS deployment lives in `terraform/`.
It is written to be correct and explainable but is not applied to a live
account. _TBD._

## Known gaps

Deliberate omissions, called out rather than hidden:

- **No migrations.** The schema is created at startup. Alembic is the right
  answer in production; here the schema is fixed for the life of the demo.
- **No authentication.** Carts are identified by an unguessable UUID with no
  ownership check — fine for a demo, not for production.
- **Stock is decremented at checkout, not reserved at cart-add.** Two carts
  can hold the last unit; one loses at checkout.
- No payments, delivery, rate limiting, or HA infrastructure.
