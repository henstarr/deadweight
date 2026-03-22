#!/usr/bin/env bash
# Demo 2: Agent logs a dead end after abandoning an approach
#
# Scenario: An agent spent 11 turns trying to use Django's raw() with
# string interpolation for dynamic table names. It failed because raw()
# does not support parameterized table names. It logs this dead end.

echo "=== Agent logs a dead end after 11 wasted turns ==="
echo ""

curl -s -X POST http://localhost:8340/log \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "django/django",
    "path": "django/db/models/sql/query.py",
    "approach": "using raw() with string interpolation for dynamic table names in multi-tenant queries",
    "reason": "raw() does not support parameterized table names — only values can be parameterized, leading to SQL injection risk that Django deliberately prevents",
    "turns_wasted": 11,
    "agent": "claude-code",
    "version": "5.0.1",
    "task_id": "django__django-16379"
  }' | python3 -m json.tool

# Expected output:
# {
#     "id": "c3d4e5f6a1b2",
#     "status": "logged",
#     "similar_patterns": [
#         {
#             "repo": "sqlalchemy/sqlalchemy",
#             "approach": "using text() with f-string interpolation for dynamic table names",
#             "reason": "SQLAlchemy text() deliberately does not parameterize identifiers — same SQL injection concern as Django raw()",
#             "turns_wasted": 7
#         },
#         {
#             "repo": "encode/databases",
#             "approach": "passing table name as query parameter in databases.execute()",
#             "reason": "asyncpg treats all parameters as values, not identifiers — table name gets quoted as a string literal",
#             "turns_wasted": 5
#         },
#         {
#             "repo": "tortoise/tortoise-orm",
#             "approach": "dynamic table name via RawSQL with format string",
#             "reason": "Tortoise ORM sanitizes all RawSQL inputs as values, table name injection blocked by design",
#             "turns_wasted": 9
#         }
#     ]
# }
#
# The agent gets back similar patterns from 3 other ORMs — confirming this
# is a cross-ecosystem dead end, not a Django-specific quirk.
