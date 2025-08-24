FROM astral/uv:0.8-python3.12-trixie-slim AS builder
# 0.8 refers to the UV version
# 3.12 refers to the Python version
# trixie refers to the Debian version
# slim refers to the image variant

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-default-groups

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups

FROM python:3.12-slim-trixie

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

CMD ["python", "-m", "app"]
