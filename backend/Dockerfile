FROM python:3.12-slim

WORKDIR /app

# Pin uv version for reproducible builds; update deliberately
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies before copying source so this layer is cached
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

# Copy source
COPY src/ ./src/
COPY api/ ./api/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Run as non-root
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser /app

USER appuser

EXPOSE 8000

CMD [".venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
