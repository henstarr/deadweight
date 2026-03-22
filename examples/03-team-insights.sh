#!/usr/bin/env bash
# Demo 3: Engineering team queries aggregate insights for their repo
#
# Scenario: A team wants to understand where their AI agents waste the
# most time. They query the insights endpoint for their repo.

echo "=== Team queries dead end insights for django/django ==="
echo ""

curl -s "http://localhost:8340/insights/django/django" | python3 -m json.tool

# Expected output:
# {
#     "repo": "django/django",
#     "total_dead_ends": 147,
#     "total_turns_wasted": 1842,
#     "avg_turns_per_dead_end": 12.5,
#     "top_dead_ends": [
#         {
#             "approach": "monkeypatching Query._execute to inject custom SQL",
#             "reason": "breaks transaction isolation in nested atomic blocks",
#             "occurrences": 23,
#             "total_turns_wasted": 312,
#             "paths": ["django/db/models/sql/compiler.py", "django/db/models/sql/query.py"]
#         },
#         {
#             "approach": "overriding ModelAdmin.get_queryset for row-level permissions",
#             "reason": "get_queryset is not called during bulk update/delete operations",
#             "occurrences": 18,
#             "total_turns_wasted": 198,
#             "paths": ["django/contrib/admin/options.py"]
#         },
#         {
#             "approach": "using raw() with string interpolation for dynamic table names",
#             "reason": "raw() does not support parameterized identifiers, only values",
#             "occurrences": 15,
#             "total_turns_wasted": 165,
#             "paths": ["django/db/models/sql/query.py", "django/db/models/manager.py"]
#         },
#         {
#             "approach": "patching django.db.connection.cursor for query logging",
#             "reason": "connection.cursor() is recreated per-thread — patches only apply to the current thread's connection",
#             "occurrences": 12,
#             "total_turns_wasted": 156,
#             "paths": ["django/db/backends/base/base.py"]
#         },
#         {
#             "approach": "adding custom Manager to abstract base model for inherited filtering",
#             "reason": "abstract model managers are not inherited by concrete children when Meta.manager_inheritance_from_future is not set",
#             "occurrences": 9,
#             "total_turns_wasted": 108,
#             "paths": ["django/db/models/manager.py", "django/db/models/base.py"]
#         }
#     ],
#     "most_common_paths": [
#         {"path": "django/db/models/sql/compiler.py", "dead_end_count": 34, "total_turns_wasted": 425},
#         {"path": "django/db/models/sql/query.py", "dead_end_count": 28, "total_turns_wasted": 336},
#         {"path": "django/contrib/admin/options.py", "dead_end_count": 22, "total_turns_wasted": 264}
#     ],
#     "agent_breakdown": {
#         "claude-code": 68,
#         "openclaw": 42,
#         "cursor": 25,
#         "copilot": 8,
#         "aider": 4
#     }
# }
#
# INSIGHT: 23 different agents independently discovered the same Query._execute
# dead end, wasting a combined 312 turns. A single CLAUDE.md note would have
# prevented all of them:
#
#   "Do NOT monkeypatch Query._execute — it breaks transaction isolation in
#    nested atomic blocks. Use QuerySet.extra() or a custom database backend."
#
# This is the enterprise product: turning aggregate dead ends into actionable
# CLAUDE.md recommendations that prevent the most expensive agent mistakes.
