FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    POETRY_VERSION=2.2.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY tests/acceptance/fixtures/france/v1/spend-FR-v1.csv ./demo/france-v1.csv
COPY tests/acceptance/fixtures/france/v2-replacement/FR-v2--Sheet1.csv ./demo/france-v2.csv

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data /app/data/objects \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && if [ \"${SEED_FRANCE_BASELINE:-false}\" = \"true\" ]; then python scripts/seed_france_baseline.py; fi && exec uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT:-8000}"]
