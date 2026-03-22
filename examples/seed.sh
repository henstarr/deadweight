#!/usr/bin/env bash
# Seed the deadweight registry with sample dead ends for testing.
# Usage: bash examples/seed.sh [BASE_URL]

BASE="${1:-http://localhost:8340}"

post() {
  curl -s -X POST "$BASE/log" -H "Content-Type: application/json" -d "$1" > /dev/null
  echo "  logged: $(echo "$1" | python3 -c "import sys,json; print(json.load(sys.stdin)['approach'][:70])")"
}

echo "Seeding deadweight at $BASE ..."
echo ""
echo "=== django/django ==="

post '{
  "repo": "django/django",
  "path": "django/db/models/sql/compiler.py",
  "approach": "monkeypatching Query._execute to inject custom SQL before compilation",
  "reason": "breaks transaction isolation in nested atomic blocks — the patched _execute runs outside the savepoint context",
  "turns_wasted": 14,
  "agent": "claude-code",
  "version": "5.0.1",
  "task_id": "django__django-16379"
}'

post '{
  "repo": "django/django",
  "path": "django/db/models/sql/query.py",
  "approach": "using raw() with string interpolation for dynamic table names",
  "reason": "raw() does not support parameterized identifiers, only values — leads to SQL injection that Django deliberately prevents",
  "turns_wasted": 11,
  "agent": "claude-code",
  "version": "5.0.1",
  "task_id": "django__django-16379"
}'

post '{
  "repo": "django/django",
  "path": "django/contrib/admin/options.py",
  "approach": "overriding ModelAdmin.get_queryset for row-level permissions",
  "reason": "get_queryset is not called during bulk update/delete operations via the admin",
  "turns_wasted": 8,
  "agent": "cursor",
  "version": "5.0"
}'

post '{
  "repo": "django/django",
  "path": "django/db/backends/base/base.py",
  "approach": "patching django.db.connection.cursor for query logging",
  "reason": "connection.cursor() is recreated per-thread — patches only apply to the current thread connection",
  "turns_wasted": 12,
  "agent": "openclaw"
}'

post '{
  "repo": "django/django",
  "path": "django/db/models/manager.py",
  "approach": "adding custom Manager to abstract base model for inherited filtering",
  "reason": "abstract model managers are not inherited by concrete children unless Meta.manager_inheritance_from_future is set",
  "turns_wasted": 9,
  "agent": "claude-code",
  "version": "5.0.1"
}'

post '{
  "repo": "django/django",
  "path": "django/db/models/fields/__init__.py",
  "approach": "overriding Field.contribute_to_class to inject validation on model save",
  "reason": "contribute_to_class runs at class definition time, not at save time — validators added here are never called",
  "turns_wasted": 7,
  "agent": "cursor"
}'

post '{
  "repo": "django/django",
  "path": "django/template/loader.py",
  "approach": "patching template loader to add custom template directories at runtime",
  "reason": "template loaders are cached after first use — runtime changes to DIRS are ignored until server restart",
  "turns_wasted": 6,
  "agent": "aider",
  "version": "4.2"
}'

echo ""
echo "=== psf/requests ==="

post '{
  "repo": "psf/requests",
  "path": "requests/adapters.py",
  "approach": "subclassing HTTPAdapter.send to add retry logic with backoff",
  "reason": "urllib3 Retry already handles this natively — subclassing send bypasses connection pooling and causes socket leaks",
  "turns_wasted": 10,
  "agent": "claude-code",
  "version": "2.31.0"
}'

post '{
  "repo": "psf/requests",
  "path": "requests/sessions.py",
  "approach": "monkeypatching Session.request to inject custom headers globally",
  "reason": "Session.headers dict is the intended mechanism — patching request() breaks prepared requests and auth flows",
  "turns_wasted": 5,
  "agent": "openclaw"
}'

post '{
  "repo": "psf/requests",
  "path": "requests/models.py",
  "approach": "modifying Response.json() to handle non-UTF-8 encodings",
  "reason": "Response.json() delegates to response.text which already handles encoding — the real issue was response.encoding being None, fixed by setting it before calling json()",
  "turns_wasted": 8,
  "agent": "cursor"
}'

echo ""
echo "=== pallets/flask ==="

post '{
  "repo": "pallets/flask",
  "path": "src/flask/app.py",
  "approach": "overriding Flask.make_response to inject CORS headers on all responses",
  "reason": "make_response is not called for error handlers or static files — use after_request instead",
  "turns_wasted": 7,
  "agent": "claude-code",
  "version": "3.0"
}'

post '{
  "repo": "pallets/flask",
  "path": "src/flask/ctx.py",
  "approach": "storing request-scoped data in module-level dict keyed by thread ID",
  "reason": "Flask uses greenlets/async contexts, not threads — thread ID is not unique per request in async mode, causes data leaks between requests",
  "turns_wasted": 15,
  "agent": "claude-code",
  "version": "3.0"
}'

post '{
  "repo": "pallets/flask",
  "path": "src/flask/blueprints.py",
  "approach": "registering error handler on blueprint before registering blueprint on app",
  "reason": "blueprint error handlers are copied to the app at register time — handlers added after register() are silently ignored",
  "turns_wasted": 6,
  "agent": "windsurf"
}'

echo ""
echo "=== sqlalchemy/sqlalchemy ==="

post '{
  "repo": "sqlalchemy/sqlalchemy",
  "path": "lib/sqlalchemy/sql/expression.py",
  "approach": "using text() with f-string interpolation for dynamic table names",
  "reason": "text() deliberately does not parameterize identifiers — same SQL injection concern as Django raw()",
  "turns_wasted": 7,
  "agent": "claude-code",
  "version": "2.0"
}'

post '{
  "repo": "sqlalchemy/sqlalchemy",
  "path": "lib/sqlalchemy/orm/session.py",
  "approach": "calling session.flush() inside an event listener for after_bulk_update",
  "reason": "flush inside an event listener triggers recursive flush — raises InvalidRequestError about nested flush",
  "turns_wasted": 11,
  "agent": "openclaw",
  "version": "2.0"
}'

post '{
  "repo": "sqlalchemy/sqlalchemy",
  "path": "lib/sqlalchemy/orm/relationships.py",
  "approach": "using backref with lazy=dynamic on a many-to-many with association table",
  "reason": "lazy=dynamic is deprecated in 2.0 and does not work with association proxies — use lazy=write_only or lazy=select instead",
  "turns_wasted": 9,
  "agent": "cursor",
  "version": "2.0"
}'

echo ""
echo "=== pydantic/pydantic ==="

post '{
  "repo": "pydantic/pydantic",
  "path": "pydantic/main.py",
  "approach": "using __init_subclass__ to register model validators dynamically",
  "reason": "pydantic v2 rebuilds the model schema at class creation — __init_subclass__ runs too early, before __pydantic_complete__ is set",
  "turns_wasted": 13,
  "agent": "claude-code",
  "version": "2.6"
}'

post '{
  "repo": "pydantic/pydantic",
  "path": "pydantic/fields.py",
  "approach": "using Field(default_factory=list) with a class variable annotation",
  "reason": "class variables are excluded from pydantic models — use model_config or ClassVar annotation explicitly to avoid silent field dropping",
  "turns_wasted": 4,
  "agent": "aider",
  "version": "2.6"
}'

echo ""
echo "=== encode/starlette ==="

post '{
  "repo": "encode/starlette",
  "path": "starlette/middleware/base.py",
  "approach": "reading request.body() inside BaseHTTPMiddleware to log request payloads",
  "reason": "request.body() consumes the stream — downstream route handlers get empty body, breaks all POST/PUT endpoints",
  "turns_wasted": 9,
  "agent": "claude-code",
  "version": "0.37"
}'

post '{
  "repo": "encode/starlette",
  "path": "starlette/routing.py",
  "approach": "adding middleware to individual routes via Route(middleware=[...])",
  "reason": "Route does not accept a middleware parameter — middleware must be applied at the app or router level",
  "turns_wasted": 5,
  "agent": "cursor"
}'

echo ""
echo "=== Done! Seeded 20 dead ends across 6 repos. ==="
