FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /app/.venv /app/.venv
USER app
EXPOSE 8000
CMD ["uvicorn", "rag_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
