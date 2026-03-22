#!/usr/bin/env bash
# Demo 1: Agent queries deadweight before attempting a Django ORM fix
#
# Scenario: An OpenClaw agent is about to patch a Django ORM bug involving
# custom SQL execution. Before trying anything, it checks deadweight.

echo "=== Agent queries dead ends before attempting fix ==="
echo ""

curl -s "http://localhost:8340/query?repo=django/django&path=django/db/models/sql&approach=monkeypatch+Query+_execute" | python3 -m json.tool

# Expected output:
# {
#     "repo": "django/django",
#     "count": 2,
#     "dead_ends": [
#         {
#             "id": "a1b2c3d4e5f6",
#             "repo": "django/django",
#             "path": "django/db/models/sql/compiler.py",
#             "approach": "monkeypatching Query._execute to inject custom SQL before compilation",
#             "reason": "breaks transaction isolation in nested atomic blocks — the patched _execute runs outside the savepoint context",
#             "turns_wasted": 14,
#             "agent": "claude-code",
#             "version": "5.0.1",
#             "relevance_score": 0.8
#         },
#         {
#             "id": "f6e5d4c3b2a1",
#             "repo": "django/django",
#             "path": "django/db/models/sql/query.py",
#             "approach": "subclassing Query and overriding _execute with custom SQL passthrough",
#             "reason": "Query subclasses are not picked up by Manager.get_queryset — the ORM always instantiates the base Query class",
#             "turns_wasted": 8,
#             "agent": "openclaw",
#             "version": "5.0.1",
#             "relevance_score": 0.6
#         }
#     ]
# }
#
# The agent reads these two dead ends and skips both approaches immediately.
# Without deadweight, it would have spent 14 + 8 = 22 turns discovering
# the same two dead ends independently.
