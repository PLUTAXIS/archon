FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
COPY archon ./archon
RUN uv sync --locked --python 3.12
ENV PATH="/app/.venv/bin:$PATH"

COPY samples ./samples
COPY tests ./tests

# The build fails if any test fails.
RUN uv run python -m unittest

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 10000

CMD ["sh", "-c", "uv run uvicorn archon.api.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
