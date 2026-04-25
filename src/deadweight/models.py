"""Core data models for dead end entries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    CLAUDE_CODE = "claude-code"
    OPENCLAW = "openclaw"
    CURSOR = "cursor"
    COPILOT = "copilot"
    AIDER = "aider"
    WINDSURF = "windsurf"
    OTHER = "other"


class DeadEndCreate(BaseModel):
    """Incoming dead end — the `dw log` payload."""

    repo: str = Field(..., description="Repository identifier, e.g. 'django/django'")
    path: str | None = Field(None, description="File or directory path prefix")
    approach: str = Field(
        ..., max_length=500, description="What was tried — be specific"
    )
    reason: str | None = Field(
        None, max_length=1000, description="Why it failed or was abandoned"
    )
    turns_wasted: int | None = Field(
        None, ge=1, description="LLM turns spent before abandoning"
    )
    agent: AgentType | None = Field(None, description="Agent harness type")
    version: str | None = Field(None, description="Repo version or commit SHA")
    task_id: str | None = Field(None, description="External task identifier")


class DeadEnd(DeadEndCreate):
    """Stored dead end — includes server-generated fields."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    resolved: bool = Field(False, description="Whether this dead end has been marked resolved")
    resolved_at: datetime | None = Field(None, description="When this dead end was resolved")
    relevance_score: float | None = Field(
        None, description="Search relevance score (populated on queries)"
    )


class DeadEndSummary(BaseModel):
    """Condensed dead end for insight reports."""

    approach: str
    reason: str | None
    occurrences: int
    total_turns_wasted: int
    paths: list[str]


class PathSummary(BaseModel):
    """Path-level aggregation."""

    path: str
    dead_end_count: int
    total_turns_wasted: int


class RepoInsight(BaseModel):
    """Aggregate insight for a repository."""

    repo: str
    total_dead_ends: int
    total_turns_wasted: int
    avg_turns_per_dead_end: float
    top_dead_ends: list[DeadEndSummary]
    most_common_paths: list[PathSummary]
    agent_breakdown: dict[str, int]
