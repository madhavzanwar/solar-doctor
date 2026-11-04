"""Fault request schemas (status/workflow update, comments)."""
from __future__ import annotations

from pydantic import BaseModel


class FaultUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    # Repair workflow. Send null to clear assignee / due_date / priority override.
    assignee: str | None = None
    due_date: str | None = None          # ISO date "YYYY-MM-DD"
    priority: str | None = None          # urgent | high | medium | low
    resolution_note: str | None = None


class CommentCreate(BaseModel):
    body: str | None = None
    author: str | None = None
