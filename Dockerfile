FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

# WORKDIR must match the final stage's (/app) -- uv bakes each venv script's
# shebang with the absolute path it was created under (e.g.
# /build/.venv/bin/python3), so copying the venv into a differently-named
# directory in the final stage leaves every entry point (uvicorn included)
# pointing at a path that doesn't exist there. Confirmed the hard way:
# "exec /app/.venv/bin/uvicorn: no such file or directory" at container
# start, with the venv otherwise copied over intact.
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./backend/app
RUN uv sync --frozen --no-dev


FROM python:3.12-slim

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY backend/app ./backend/app
# Sprint 5: static/ (CSS/JS/vendored marked+DOMPurify) sits alongside app/,
# not inside it -- main.py mounts it via StaticFiles, which fails at
# startup if the directory doesn't exist in the image.
COPY backend/static ./backend/static

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
