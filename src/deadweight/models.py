"""Core data models for dead end entries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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
    """Incoming dead end from an agent — the POST body."""

    repo: str = Field(..., description="Repository identifier, e.g. 'django/django'")
    path: Optional[str] = Field(None, description="File or directory path prefix")
    approach: str = Field(
        ..., max_length=500, description="What was tried — be specific"
    )
    reason: Optional[str] = Field(
        None, max_length=1000, description="Why it failed or was abandoned"
    )
    turns_wasted: Optional[int] = Field(
        None, ge=1, description="LLM turns spent before abandoning"
    )
    agent: Optional[AgentType] = Field(None, description="Agent harness type")
    version: Optional[str] = Field(None, description="Repo version or commit SHA")
    task_id: Optional[str] = Field(None, description="External task identifier")


class DeadEnd(DeadEndCreate):
    """Stored dead end — includes server-generated fields."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    relevance_score: Optional[float] = Field(
        None, description="Search relevance score (populated on queries)"
    )


class DeadEndQuery(BaseModel):
    """Query parameters for searching dead ends."""

    repo: str
    path: Optional[str] = None
    approach: Optional[str] = None
    agent: Optional[AgentType] = None
    limit: int = Field(default=10, ge=1, le=100)


class RepoInsight(BaseModel):
    """Aggregate insight for a repository."""

    repo: str
    total_dead_ends: int
    total_turns_wasted: int
    avg_turns_per_dead_end: float
    top_dead_ends: list[DeadEndSummary]
    most_common_paths: list[PathSummary]
    agent_breakdown: dict[str, int]


class DeadEndSummary(BaseModel):
    """Condensed dead end for insight reports."""

    approach: str
    reason: Optional[str]
    occurrences: int
    total_turns_wasted: int
    paths: list[str]


class PathSummary(BaseModel):
    """Path-level aggregation."""

    path: str
    dead_end_count: int
    total_turns_wasted: int


class SimilarPattern(BaseModel):
    """A dead end from another repo that matches a similar pattern."""

    repo: str
    approach: str
    reason: Optional[str]
    turns_wasted: Optional[int]


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")


class UserRegisterResponse(BaseModel):
    username: str
    api_key: str
    message: str
