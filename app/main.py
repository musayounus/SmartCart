from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

app = FastAPI(title="SmartCart", version="0.1.0")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@app.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    """Liveness probe that also proves the database link is wired up."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
