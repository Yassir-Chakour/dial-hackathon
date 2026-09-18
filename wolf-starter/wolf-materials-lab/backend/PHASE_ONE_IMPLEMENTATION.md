# Phase One Implementation Plan: Backend Foundation

This document translates `GOALS.md` into an implementation plan for Phase One only.

Phase One should establish a small, testable FastAPI service boundary. It should not yet implement file ingestion, database persistence, LangGraph, recommendation logic, authentication, or procurement actions. Those belong to later phases and should be added behind the contracts defined here.

## 1. Phase-one outcome

At the end of this phase, the backend should:

- start locally with one documented command;
- expose liveness and readiness endpoints;
- load configuration safely from environment variables;
- validate configuration at startup;
- expose versioned, typed API models using Pydantic;
- return one consistent JSON error format;
- log useful operational events without logging source contents or secrets;
- pass automated tests, linting and type checking;
- produce a reproducible Poetry lockfile.

The service must be safe to run in demo mode even though the real source-file workflow is not implemented yet.

## 2. Recommended project structure

Create the following structure under `backend/`:

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application factory and routes
│   ├── config.py               # Typed settings and environment loading
│   ├── api/
│   │   ├── __init__.py
│   │   ├── errors.py           # Error envelope and exception handlers
│   │   └── health.py           # /health/live and /health/ready
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── common.py           # Shared response and metadata models
│   └── logging.py              # Structured logging configuration
├── tests/
│   ├── test_health.py
│   ├── test_errors.py
│   └── test_config.py
├── .env.example
├── pyproject.toml
└── poetry.lock
```

Keep business logic out of route functions. Later phases can add `domain/`, `repositories/`, `services/` and `workflows/` without changing the HTTP boundary.

## 3. Dependencies and reproducibility

Use a small dependency set in Phase One:

- `fastapi` for the HTTP API;
- `uvicorn[standard]` for local serving;
- `pydantic-settings` for typed configuration;
- `structlog` or the standard-library logging package for structured logs;
- `pytest`, `httpx` and `pytest-asyncio` for API tests;
- `ruff` for formatting and linting;
- `mypy` for static type checking.

Update the current `pyproject.toml` to use a valid Python range such as `>=3.12,<4.0`, then run Poetry to create and commit `poetry.lock`. Do not use unconstrained dependency versions in the lockfile workflow. CI and local development must install from the lockfile.

Suggested commands:

```bash
poetry install
poetry run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
poetry run pytest
poetry run ruff check .
poetry run mypy app
```

Bind to `127.0.0.1` by default. Binding to all interfaces should require an explicit deployment setting.

## 4. Configuration and environment handling

Use one typed settings object, created through a cached function. It should read environment variables and an optional local `.env` file, but never require `.env` to exist.

Recommended settings:

| Setting | Purpose | Safe default |
| --- | --- | --- |
| `APP_ENV` | `development`, `test` or `production` | `development` |
| `APP_NAME` | Service name in metadata/logs | `wolf-materials-backend` |
| `APP_VERSION` | API/service version | `0.1.0` |
| `LOG_LEVEL` | Log threshold | `INFO` |
| `CORS_ORIGINS` | Explicit browser origins | empty in production |
| `API_HOST` | Bind address | `127.0.0.1` |
| `API_PORT` | Bind port | `8000` |
| `MODEL_BASE_URL` | Optional server-side model endpoint for later phases | unset |
| `MODEL_NAME` | Optional model name | unset |
| `MODEL_TOKEN` | Optional provider token | unset and never returned |

Rules:

1. Fail fast when production settings are unsafe or contradictory.
2. Never commit `.env`, tokens, private source files or generated local data.
3. Do not expose settings through an endpoint. If configuration must be shown, expose only non-secret capabilities such as environment and version.
4. Treat all environment values as untrusted input and validate URLs, enum values, lengths and allowed origins.
5. Keep model credentials server-side. The browser must never receive `MODEL_TOKEN`.

`.env.example` should contain names and fake placeholders only, for example:

```dotenv
APP_ENV=development
APP_VERSION=0.1.0
LOG_LEVEL=INFO
CORS_ORIGINS=http://127.0.0.1:8084
# MODEL_BASE_URL=http://127.0.0.1:8001/v1
# MODEL_NAME=example-model
# MODEL_TOKEN=replace-locally
```

## 5. API foundation

Use an explicit API prefix and version from the start:

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

### Liveness

`/health/live` answers whether the process is running. It must not call a model provider, database, filesystem or external network. Expected response:

```json
{
  "status": "ok",
  "service": "wolf-materials-backend",
  "version": "0.1.0"
}
```

Return HTTP 200 when the process can serve requests.

### Readiness

`/health/ready` answers whether the application is configured to accept work. In Phase One, check only configuration and application startup state. Database, object storage and external model checks should be added in their respective phases, with short timeouts and explicit dependency statuses.

Return HTTP 200 when ready and HTTP 503 when not ready. Do not include secrets, connection strings or raw exception messages.

Example not-ready shape:

```json
{
  "status": "not_ready",
  "service": "wolf-materials-backend",
  "version": "0.1.0",
  "checks": {"configuration": "failed"}
}
```

### Versioning rule

Do not silently change a response field once exposed. Add fields compatibly or introduce `/api/v2`. Keep internal Python names separate from display labels so frontend wording can evolve without breaking clients.

## 6. Pydantic contracts

Define shared models before implementing feature endpoints. At minimum:

```python
class ServiceStatus(BaseModel):
    status: Literal["ok", "ready", "not_ready"]
    service: str
    version: str
    checks: dict[str, Literal["ok", "failed"]] | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ErrorDetail] = []
```

Use `extra="forbid"` for request models wherever practical. Use strict types for identifiers and bounded string lengths. Do not accept arbitrary dictionaries for future business data merely to move faster; that makes validation and privacy boundaries unclear.

Later source and recommendation schemas should include stable identifiers, a source/version reference and evidence references. The Phase One common models should make room for these concepts without pretending that ingestion already exists.

## 7. Consistent errors and request correlation

Install one application-wide exception handler for:

- Pydantic request validation errors;
- known domain/application errors added later;
- unexpected exceptions.

All errors should use the same envelope and include a generated `request_id`. Send the request ID in an `X-Request-ID` response header. Accept an incoming request ID only after validating length and characters; otherwise generate a new one.

Recommended stable error codes include:

```text
invalid_request
not_found
not_ready
conflict
dependency_unavailable
internal_error
```

Messages must be safe for users. In production, return a generic `internal_error` message and keep the traceback only in protected logs. Never return SQL, filesystem paths, environment variables, provider responses or stack traces.

## 8. Security requirements

Security is part of the foundation, even before uploads and approvals exist.

- Use HTTPS at the deployment boundary and document that local HTTP is development-only.
- Restrict CORS to configured frontend origins; never use wildcard origins with credentials.
- Do not add permissive authentication bypasses that could accidentally survive into production. Phase One can remain unauthenticated locally, but mark every write or sensitive route as requiring authentication in later phases.
- Set conservative request and response headers at the proxy/application boundary, including `X-Content-Type-Options: nosniff` and a restrictive policy for docs in production.
- Do not expose interactive API documentation publicly in production unless it is protected.
- Apply timeouts to outbound calls when model integrations are added. Never allow arbitrary user-supplied URLs for server-side fetching.
- Avoid shell execution, dynamic imports and unsafe deserialization of uploaded content.
- Keep dependencies patched and run `pip-audit` or an equivalent dependency scan in CI when available.
- Use least privilege for the service account and filesystem permissions.
- Treat model output as untrusted text. It must never directly execute actions, alter approvals or bypass deterministic validation.

## 9. Privacy and data minimization

The starter kit is synthetic, but the design must be ready for real procurement files later.

- Phase One stores no uploaded source files and sends no source data to external services.
- Logs must contain request IDs, route names, status codes, duration and safe error codes—not request bodies, file contents, supplier pricing, tokens or user prompts.
- Do not log authorization headers, cookies, model responses or full exception context if it may contain source data.
- Define a redaction helper for future structured logs: redact keys such as `authorization`, `token`, `password`, `secret`, `content`, `prompt` and `source_data`.
- Collect only the metadata needed for operations. Do not add user identity, location or analytics fields before a real requirement exists.
- Add a clear synthetic-data notice to API documentation and demo responses where relevant.
- Future persistence must define retention, deletion, access control, encryption and tenant boundaries before accepting real files.
- Future model calls must use an approved provider, minimize payloads and document whether prompts or outputs are retained.

## 10. Reusable functions and boundaries

Prefer small functions with one responsibility. The following utilities should be reusable in later phases:

- `get_settings()` — cached typed configuration;
- `configure_logging(settings)` — one logging setup path;
- `get_request_id(request)` — validate or create correlation IDs;
- `safe_error_response(...)` — map internal errors to the public envelope;
- `redact_mapping(value)` — remove sensitive keys before logging;
- `parse_allowed_origins(value)` — normalize and validate CORS origins;
- `utc_now()` — one timezone-aware clock helper for audit fields;
- `build_app(settings)` — application factory that tests can instantiate with overrides.

Keep these functions free of business rules. A future `normalization` module should contain procurement normalization; it should not be mixed into HTTP error handling or configuration.

## 11. Testing strategy

Tests should prove behavior, not implementation details.

Required Phase One tests:

- liveness returns 200 and never calls external dependencies;
- readiness returns 200 for valid configuration;
- readiness returns 503 for invalid/unavailable startup configuration;
- all error responses contain `code`, `message` and `request_id`;
- validation errors do not expose stack traces or secrets;
- a supplied valid request ID is echoed safely;
- an oversized or malformed request ID is replaced;
- secret settings never appear in responses or captured logs;
- CORS allows only configured origins;
- application factory works with test settings and does not mutate global state;
- test, lint and type-check commands are documented and repeatable.

Add a simple CI job that runs the complete quality gate:

```bash
poetry check
poetry run ruff check .
poetry run mypy app
poetry run pytest -q
```

## 12. Implementation order

1. Correct the Poetry metadata and add locked dependencies.
2. Add settings, `.env.example` and secret-safe startup validation.
3. Add structured logging, request IDs and redaction.
4. Add common Pydantic schemas and the error handler.
5. Add the application factory and versioned router.
6. Add liveness and readiness endpoints.
7. Add tests for the endpoints, configuration and security boundaries.
8. Run the quality gate and document the local start command.

## 13. Explicitly out of scope for Phase One

Do not implement these yet:

- accepting or storing CSV/XLSX uploads;
- SQLite models or repositories;
- source hashing and version lineage persistence;
- France replacement logic or reconciliation;
- recommendation calculations;
- LangGraph state and model calls;
- reviewer authentication and approval enforcement;
- external purchasing, contract or notification actions;
- production deployment or public exposure.

The right Phase One design makes these additions possible without weakening the security and privacy boundaries above.

## Definition of done

Phase One is complete when a fresh checkout can install from `poetry.lock`, start the backend locally, return healthy typed status responses, handle failures through the common error contract, and pass tests/lint/type checks. No secrets or source contents should appear in the repository, HTTP responses or logs.
