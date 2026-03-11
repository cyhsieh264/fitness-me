FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN mkdir -p /app/data

ENV PORT=8000
EXPOSE ${PORT}

CMD /app/.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT}
