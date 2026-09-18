# Deployment and Database Best Practices

## Target architecture

The production target is a containerized application deployed through Coolify:

```text
Browser
  |
  | HTTPS
  v
Next.js frontend
  |
  | private or controlled HTTPS API connection
  v
FastAPI backend
  |
  | private Docker network
  v
PostgreSQL database
```

The frontend, backend and database must remain separate services. The database must not be exposed directly to the public internet.

## Database decision

Use PostgreSQL as the target database from the first persistence implementation. Do not build production persistence around SQLite and migrate later unless local development requires a temporary fallback.

The current project does not yet contain database implementation code. This document defines the target before that work begins.

## PostgreSQL standards

- Use a dedicated database and dedicated application role.
- Do not use the PostgreSQL superuser from the backend.
- Use a strong generated password stored only in Coolify secrets.
- Keep PostgreSQL on a private network whenever possible.
- Do not commit connection strings, passwords or certificates.
- Use a separate database for development, staging and production.
- Set a connection pool limit appropriate for the server size.
- Use UTC for timestamps stored by the backend.
- Use explicit numeric types for money instead of floating-point values.
- Use stable identifiers for records and events.
- Add indexes only for known query paths and verify them with real data.
- Add foreign keys and uniqueness constraints for data integrity.
- Use transactions for imports, recommendation creation and approvals.

## SQLAlchemy and migrations

Use SQLAlchemy as the database access layer and Alembic for schema migrations.

Rules:

- Models describe database structure.
- Pydantic schemas describe API input and output.
- Repository functions isolate database queries from domain logic.
- Domain services perform business rules outside route handlers.
- Alembic migrations are committed to the repository.
- The application must not silently create or modify production tables at startup.
- Run migrations as an explicit deployment step before serving traffic.
- Review every migration before applying it to production.
- Avoid destructive migrations without a backup and rollback plan.

Expected separation:

```text
API routes
  -> application services
    -> domain logic
      -> repositories
        -> SQLAlchemy models
          -> PostgreSQL
```

## Data integrity requirements

The database must preserve procurement history rather than overwrite it.

Important records include:

- Source files and file hashes
- Source versions
- Normalized source records
- Workflow events
- Recommendations
- Evidence links
- Corrections
- Approvals

Important constraints include:

- An event key or source hash must prevent duplicate processing.
- A recommendation must reference the exact source version used to create it.
- An approval must reference the exact recommendation version approved.
- A stale recommendation cannot be approved.
- Evidence must reference a source file and source row where available.
- A replacement update must preserve records outside its declared scope.
- Financial values must use `NUMERIC`, not binary floating-point types.

## Docker practices

Use separate images for the frontend and backend. PostgreSQL should use the official PostgreSQL image or a managed PostgreSQL service.

### Backend image

- Use a small Python base image.
- Pin the Python version.
- Install dependencies from the Poetry lockfile.
- Build dependencies in a separate stage when practical.
- Run as a non-root user.
- Set a working directory with an explicit owner.
- Do not copy `.env`, credentials, local databases or test artifacts into the image.
- Add a `.dockerignore` file.
- Keep the container process as the main application process.
- Use Uvicorn with a production configuration.

### Frontend image

- Use a multi-stage Node build.
- Pin the Node version to the project requirement.
- Build the Next.js application in the builder stage.
- Run only the required production output in the final stage.
- Do not include development secrets in browser bundles.
- Keep public environment variables limited to non-sensitive values.

### Compose for local development

Local Docker Compose should provide:

- `frontend`
- `backend`
- `postgres`

The PostgreSQL volume must be named and persistent. The database service should be reachable by service name, not by a public IP.

The Compose file must not contain real credentials. Use an ignored local `.env` file or safe development defaults that are never reused in production.

## Coolify deployment practices

- Create PostgreSQL as a managed Coolify resource or an isolated database service.
- Attach the database and backend to a private network.
- Expose only the frontend and backend domains.
- Configure the frontend API base URL through environment configuration.
- Store secrets in Coolify's secret environment variables.
- Do not paste secrets into Dockerfiles, Git, build logs or frontend variables.
- Use separate Coolify resources or environments for staging and production.
- Configure HTTPS and redirect HTTP to HTTPS.
- Use health checks for frontend and backend services.
- Set resource limits and restart policies.
- Keep deployment logs free of request bodies and credentials.
- Verify that database backups are enabled before using production data.
- Test restore procedures instead of relying only on backup success messages.

## Environment variables

Sensitive variables belong only on the backend or database service:

```text
DATABASE_URL
POSTGRES_PASSWORD
WOLF_MODEL_TOKEN
SECRET_KEY
```

Non-sensitive frontend configuration may include:

```text
NEXT_PUBLIC_API_BASE_URL
```

Never expose these to the browser:

- Database URLs
- Database credentials
- Model provider tokens
- Signing keys
- Internal service URLs
- Administrative credentials

Use separate values for local, staging and production. Rotate credentials if they are ever exposed.

## API security

The backend must implement the following before production use:

- Strict CORS allowlists
- Trusted host validation
- Request size limits for uploaded files
- Allowed file type validation
- Timeouts on external calls
- Rate limiting on expensive endpoints
- Authentication for reviewer actions
- Authorization for approval and administrative actions
- Structured error responses without internal stack traces
- Request IDs for traceability
- Audit logs for corrections and approvals
- Input validation for every route
- Protection against path traversal and unsafe filenames
- No execution of spreadsheet formulas or macros
- Safe handling of untrusted spreadsheet text and embedded instructions

Uploaded source files are untrusted data. Text inside an invoice or spreadsheet must never be treated as an instruction to the agent or server.

## LangGraph security boundary

LangGraph may orchestrate tools, but tools must have explicit permissions.

The agent must not be able to:

- Execute arbitrary shell commands
- Read environment secrets
- Access the database without an approved repository tool
- Send external messages without a separate authorization boundary
- Approve its own recommendation
- Modify historical approved records

The language model may propose an action. Deterministic backend code must validate the action, and a human must approve consequential procurement decisions.

## Backups and recovery

- Enable automated PostgreSQL backups in Coolify or the selected database service.
- Define a retention period appropriate for the project.
- Keep backups separate from the running database volume.
- Encrypt backups at rest where supported.
- Test restoration into a separate database.
- Document the recovery procedure.
- Never treat the Docker volume alone as a backup.

## Observability

Log structured events for:

- Source upload accepted or rejected
- Workflow started and completed
- Event skipped as a duplicate
- Validation exception
- Recommendation created
- Approval rejected as stale
- Approval completed
- Database migration result

Do not log:

- Passwords
- API tokens
- Full uploaded documents by default
- Sensitive request headers
- Unnecessary personal data

Add metrics for request latency, failed imports, duplicate events, review queue size, approval failures and database errors.

## Deployment sequence

1. Build and test the backend image.
2. Build and test the frontend image.
3. Create or select the PostgreSQL resource in Coolify.
4. Configure private networking.
5. Add production secrets in Coolify.
6. Run Alembic migrations.
7. Start the backend and verify health checks.
8. Start the frontend with the backend API URL.
9. Run the France import and approval smoke test.
10. Verify duplicate replay and stale approval rejection.
11. Confirm HTTPS, backups and logs.
12. Only then share the public demo URL.

## Production readiness checklist

- [ ] No secrets committed to Git
- [ ] PostgreSQL is private
- [ ] Dedicated least-privilege database user exists
- [ ] Alembic migrations are committed and tested
- [ ] Backups are enabled
- [ ] Restore procedure is tested
- [ ] Frontend and backend run as separate services
- [ ] Containers run as non-root users
- [ ] CORS and trusted hosts are restricted
- [ ] Upload limits and file validation are active
- [ ] Authentication protects reviewer actions
- [ ] Approval actions are audited
- [ ] Duplicate event replay is idempotent
- [ ] Stale approvals are rejected
- [ ] Health checks work
- [ ] France end-to-end smoke test passes
