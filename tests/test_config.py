"""Keeps `.env.example` honest.

The file is documentation and nothing reads it, so nothing breaks when it goes
stale -- which is exactly how it came to be missing `REDIS_URL` for several
commits. That mattered: leaving `REDIS_URL` unset silently falls back to
per-process rate limiting, which is correct for one instance and wrong for two.

This test makes the drift loud instead of silent.
"""

import re
from pathlib import Path

from app.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def documented_keys() -> set[str]:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8")
    return {key.lower() for key in re.findall(r"^([A-Z][A-Z0-9_]*)=", lines, re.MULTILINE)}


def test_env_example_documents_every_setting() -> None:
    undocumented = set(Settings.model_fields) - documented_keys()

    assert not undocumented, (
        f"settings missing from .env.example: {sorted(undocumented)}. "
        "Add them, or a reader running outside Docker will never learn they exist."
    )


def test_env_example_documents_nothing_that_does_not_exist() -> None:
    """Catches the other direction: a setting renamed or removed in code."""
    stale = documented_keys() - set(Settings.model_fields)

    assert not stale, f".env.example documents settings the app no longer reads: {sorted(stale)}"
