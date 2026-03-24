"""Tests for the deadweight API server."""

import os

import pytest
from fastapi.testclient import TestClient

# Use a temp database for tests
os.environ["DEADWEIGHT_DB"] = ":memory:"

from deadweight.server import app

client = TestClient(app)

# Register once for the whole test session — avoids hitting the /register rate limit.
_r = client.post("/register", json={"username": "test-session-user"})
assert _r.status_code == 201, _r.text
AUTH = {"Authorization": f"Bearer {_r.json()['api_key']}"}


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    # Root now serves HTML frontend or JSON fallback
    if "text/html" in r.headers.get("content-type", ""):
        assert "deadweight" in r.text
    else:
        assert r.json()["service"] == "deadweight"


def test_api_root():
    r = client.get("/api")
    assert r.status_code == 200
    assert r.json()["service"] == "deadweight"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register():
    r = client.post("/register", json={"username": "unique-reg-user"})
    assert r.status_code == 201
    data = r.json()
    assert "api_key" in data
    assert data["username"] == "unique-reg-user"
    assert "Save this key" in data["message"]

    # Duplicate username should 409
    r2 = client.post("/register", json={"username": "unique-reg-user"})
    assert r2.status_code == 409


def test_log_requires_auth():
    r = client.post("/log", json={"repo": "x/y", "approach": "something"})
    assert r.status_code == 401


def test_log_and_query():
    # Log a dead end
    r = client.post(
        "/log",
        headers=AUTH,
        json={
            "repo": "test/repo",
            "approach": "monkeypatching the thing",
            "reason": "it breaks everything",
            "turns_wasted": 7,
            "agent": "claude-code",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "logged"
    assert "id" in data

    # Query it back
    r = client.get("/query", params={"repo": "test/repo"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["dead_ends"][0]["approach"] == "monkeypatching the thing"


def test_query_with_approach_filter():
    client.post(
        "/log",
        headers=AUTH,
        json={"repo": "filter/repo", "approach": "using raw SQL injection"},
    )
    client.post(
        "/log",
        headers=AUTH,
        json={"repo": "filter/repo", "approach": "subclassing the manager"},
    )

    r = client.get(
        "/query", params={"repo": "filter/repo", "approach": "raw SQL"}
    )
    data = r.json()
    assert data["count"] == 1
    assert "raw SQL" in data["dead_ends"][0]["approach"]


def test_query_empty_repo():
    r = client.get("/query", params={"repo": "nonexistent/repo"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_insights_not_found():
    r = client.get("/insights/nonexistent/repo")
    assert r.status_code == 404


def test_insights():
    for i in range(3):
        client.post(
            "/log",
            headers=AUTH,
            json={
                "repo": "insights/repo",
                "approach": "bad approach",
                "reason": "it fails",
                "turns_wasted": 5 + i,
            },
        )

    r = client.get("/insights/insights/repo")
    assert r.status_code == 200
    data = r.json()
    assert data["total_dead_ends"] == 3
    assert data["total_turns_wasted"] == 18  # 5 + 6 + 7


def test_agents_md():
    r = client.get("/agents/deadends.md")
    assert r.status_code == 200
    assert "deadweight" in r.text


def test_log_minimal():
    """Only repo and approach are required."""
    r = client.post(
        "/log",
        headers=AUTH,
        json={"repo": "minimal/repo", "approach": "just the approach"},
    )
    assert r.status_code == 201


def test_log_rejects_invalid_agent():
    r = client.post(
        "/log",
        headers=AUTH,
        json={
            "repo": "test/repo",
            "approach": "something",
            "agent": "invalid-agent",
        },
    )
    assert r.status_code == 422
