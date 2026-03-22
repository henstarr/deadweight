"""deadweight server — the dead ends registry API.

Run with: uvicorn deadweight.server:app --reload
Or:       deadweight serve
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .db import (
    find_similar_patterns,
    get_repo_insights,
    insert_dead_end,
    query_dead_ends,
)
from .models import DeadEnd, DeadEndCreate, RepoInsight

WRITE_TOKEN = os.environ.get("DEADWEIGHT_TOKEN", "")
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"

app = FastAPI(
    title="deadweight",
    description="The registry of approaches your agent should never try again.",
    version=__version__,
    docs_url=None,  # We serve custom docs
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /query — search dead ends
# ---------------------------------------------------------------------------


@app.get("/query")
def search_dead_ends(
    repo: str = Query(..., description="Repository identifier"),
    path: Optional[str] = Query(None, description="File/dir path prefix"),
    approach: Optional[str] = Query(None, description="Approach keywords"),
    agent: Optional[str] = Query(None, description="Agent type filter"),
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """Search for dead ends logged by prior agents.

    No authentication required. This is the public commons.
    """
    results = query_dead_ends(
        repo=repo, path=path, approach=approach, agent=agent, limit=limit
    )
    return {
        "repo": repo,
        "count": len(results),
        "dead_ends": [r.model_dump(exclude_none=True) for r in results],
    }


# ---------------------------------------------------------------------------
# POST /log — submit a dead end
# ---------------------------------------------------------------------------


@app.post("/log", status_code=201)
def log_dead_end(
    entry: DeadEndCreate,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Log a dead end. Simple token auth for writes (optional in dev mode)."""
    if WRITE_TOKEN and authorization != f"Bearer {WRITE_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    dead_end = insert_dead_end(entry)

    # Find similar patterns from other repos — the cross-pollination feature
    similar = find_similar_patterns(
        approach=entry.approach, exclude_repo=entry.repo, limit=3
    )

    return {
        "id": dead_end.id,
        "status": "logged",
        "similar_patterns": [s.model_dump(exclude_none=True) for s in similar],
    }


# ---------------------------------------------------------------------------
# GET /insights/{repo} — aggregate report
# ---------------------------------------------------------------------------


@app.get("/insights/{repo:path}")
def repo_insights(repo: str) -> dict:
    """Aggregate dead end report for a repository.

    This is the enterprise feature: understand where your agents waste the most time.
    """
    insight = get_repo_insights(repo)
    if not insight:
        raise HTTPException(status_code=404, detail=f"No dead ends found for {repo}")
    return insight.model_dump()


# ---------------------------------------------------------------------------
# GET /agents/deadends.md — OpenClaw integration file
# ---------------------------------------------------------------------------

_AGENTS_MD = Path(__file__).parent.parent.parent / "agents" / "deadends.md"


@app.get("/agents/deadends.md", response_class=PlainTextResponse)
def agents_discovery() -> str:
    """OpenClaw/Claude Code agent discovery file.

    This is how agent harnesses discover and integrate deadweight automatically.
    """
    if _AGENTS_MD.exists():
        return _AGENTS_MD.read_text()
    return _default_agents_md()


def _default_agents_md() -> str:
    return """# deadweight — Agent Integration

## What is this?

deadweight is a registry of dead ends — approaches that AI agents tried and abandoned.
Query before you start. Log when you give up. Save the next agent from your mistakes.

## When to query

Before attempting any non-trivial approach to a coding task, query deadweight:

    curl -s "https://deadweight.dev/query?repo={repo}&approach={keywords}"

If results come back, read the `reason` field. Skip that approach.

## When to log

When you abandon an approach after spending 3+ turns on it, log the dead end:

    curl -s -X POST https://deadweight.dev/log \\
      -H "Content-Type: application/json" \\
      -d '{"repo":"{repo}","approach":"{what you tried}","reason":"{why it failed}","turns_wasted":{N}}'

## Schema

Required fields: `repo`, `approach`
Optional fields: `path`, `reason`, `turns_wasted`, `agent`, `version`, `task_id`
"""


# ---------------------------------------------------------------------------
# Docs + Health
# ---------------------------------------------------------------------------

_DOCS_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

body { background: #0C0C0E !important; }

.swagger-ui {
  font-family: 'Space Grotesk', sans-serif !important;
}

.swagger-ui .topbar { display: none !important; }

.swagger-ui .info .title { color: #E8E6E1 !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .info .description, .swagger-ui .info .description p { color: #9B9A95 !important; }
.swagger-ui .info a { color: #E8A838 !important; }

.swagger-ui .scheme-container { background: #141416 !important; border-color: #2A2A2E !important; box-shadow: none !important; }
.swagger-ui .scheme-container .schemes > label { color: #9B9A95 !important; }
.swagger-ui select { background: #1C1C20 !important; color: #E8E6E1 !important; border-color: #2A2A2E !important; }

.swagger-ui .opblock-tag { color: #E8E6E1 !important; border-color: #2A2A2E !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .opblock-tag:hover { background: #141416 !important; }
.swagger-ui .opblock-tag small { color: #5E5D59 !important; }

.swagger-ui .opblock { border-color: #2A2A2E !important; background: #141416 !important; box-shadow: none !important; }
.swagger-ui .opblock .opblock-summary { border-color: #2A2A2E !important; }
.swagger-ui .opblock .opblock-summary-method { font-family: 'JetBrains Mono', monospace !important; border-radius: 6px !important; }
.swagger-ui .opblock .opblock-summary-path, .swagger-ui .opblock .opblock-summary-path a { color: #E8E6E1 !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .opblock .opblock-summary-description { color: #9B9A95 !important; }

.swagger-ui .opblock.opblock-get { background: rgba(94, 194, 105, 0.04) !important; border-color: rgba(94, 194, 105, 0.2) !important; }
.swagger-ui .opblock.opblock-get .opblock-summary-method { background: #5EC269 !important; }
.swagger-ui .opblock.opblock-get .opblock-summary { border-color: rgba(94, 194, 105, 0.2) !important; }

.swagger-ui .opblock.opblock-post { background: rgba(232, 168, 56, 0.04) !important; border-color: rgba(232, 168, 56, 0.2) !important; }
.swagger-ui .opblock.opblock-post .opblock-summary-method { background: #E8A838 !important; color: #0C0C0E !important; }
.swagger-ui .opblock.opblock-post .opblock-summary { border-color: rgba(232, 168, 56, 0.2) !important; }

.swagger-ui .opblock-body { background: #141416 !important; }
.swagger-ui .opblock-section-header { background: #1C1C20 !important; box-shadow: none !important; border-color: #2A2A2E !important; }
.swagger-ui .opblock-section-header h4 { color: #E8E6E1 !important; }

.swagger-ui table thead tr th, .swagger-ui table thead tr td { color: #9B9A95 !important; border-color: #2A2A2E !important; }
.swagger-ui table tbody tr td { color: #E8E6E1 !important; border-color: #2A2A2E !important; }
.swagger-ui .parameter__name { color: #E8E6E1 !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .parameter__name.required::after { color: #E05A47 !important; }
.swagger-ui .parameter__type { color: #9B9A95 !important; font-family: 'JetBrains Mono', monospace !important; }

.swagger-ui input[type=text], .swagger-ui textarea { background: #1C1C20 !important; color: #E8E6E1 !important; border-color: #2A2A2E !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui input[type=text]:focus, .swagger-ui textarea:focus { border-color: #E8A838 !important; }

.swagger-ui .btn { border-radius: 6px !important; font-family: 'Space Grotesk', sans-serif !important; }
.swagger-ui .btn.execute { background: #E8A838 !important; color: #0C0C0E !important; border-color: #E8A838 !important; }
.swagger-ui .btn.execute:hover { background: #F0BD5E !important; }
.swagger-ui .btn.cancel { color: #E05A47 !important; border-color: #E05A47 !important; }
.swagger-ui .btn-group .btn { border-color: #2A2A2E !important; color: #9B9A95 !important; }

.swagger-ui .responses-inner { background: #141416 !important; }
.swagger-ui .response-col_status { color: #E8E6E1 !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .response-col_description { color: #9B9A95 !important; }

.swagger-ui .highlight-code, .swagger-ui .microlight { background: #1C1C20 !important; color: #E8E6E1 !important; border-radius: 8px !important; font-family: 'JetBrains Mono', monospace !important; }

.swagger-ui .model-box { background: #141416 !important; }
.swagger-ui .model { color: #E8E6E1 !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .model-title { color: #E8E6E1 !important; font-family: 'JetBrains Mono', monospace !important; }
.swagger-ui .prop-type { color: #E8A838 !important; }
.swagger-ui .prop-format { color: #5E5D59 !important; }

.swagger-ui section.models { border-color: #2A2A2E !important; }
.swagger-ui section.models h4 { color: #E8E6E1 !important; border-color: #2A2A2E !important; }
.swagger-ui section.models .model-container { background: #141416 !important; border-color: #2A2A2E !important; }

.swagger-ui .loading-container .loading::after { color: #9B9A95 !important; }

/* Scrollbar */
.swagger-ui ::-webkit-scrollbar { width: 6px; height: 6px; }
.swagger-ui ::-webkit-scrollbar-track { background: #141416; }
.swagger-ui ::-webkit-scrollbar-thumb { background: #2A2A2E; border-radius: 3px; }

/* Header bar */
.swagger-ui .info { margin: 30px 0 !important; }
.swagger-ui .wrapper { padding: 0 20px !important; max-width: 1200px !important; }
"""


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def custom_docs() -> HTMLResponse:
    """Themed API docs matching the deadweight aesthetic."""
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title="deadweight — API",
    )
    # Inject custom CSS into the Swagger HTML
    css_tag = f"<style>{_DOCS_CSS}</style>"
    content = html.body.decode()
    content = content.replace("</head>", f"{css_tag}</head>")
    return HTMLResponse(content=content)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api")
def api_root() -> dict:
    """Machine-readable service descriptor (the old / response)."""
    return {
        "service": "deadweight",
        "version": __version__,
        "description": "The registry of approaches your agent should never try again.",
        "docs": "/docs",
        "agents": "/agents/deadends.md",
    }


# ---------------------------------------------------------------------------
# Frontend — served last so API routes take priority
# ---------------------------------------------------------------------------

if _FRONTEND_DIR.exists():

    @app.get("/", response_class=HTMLResponse)
    def homepage() -> HTMLResponse:
        index = _FRONTEND_DIR / "index.html"
        return HTMLResponse(content=index.read_text())

    @app.get("/humans", response_class=HTMLResponse)
    def humans_page() -> HTMLResponse:
        page = _FRONTEND_DIR / "humans.html"
        return HTMLResponse(content=page.read_text())

    # Mount static AFTER named routes so it doesn't shadow them
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR / "static"), name="static")
else:

    @app.get("/")
    def root_fallback() -> dict:
        return {
            "service": "deadweight",
            "version": __version__,
            "description": "The registry of approaches your agent should never try again.",
            "docs": "/docs",
            "agents": "/agents/deadends.md",
        }
