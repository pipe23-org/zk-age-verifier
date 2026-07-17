# syntax=docker/dockerfile:1
# uv multi-stage build: deps resolved in a builder, only the venv + source ship.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
# install deps first (cached on a bind mount) without the project, for layer reuse
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
RUN chmod +x /app/docker-entrypoint.sh

FROM python:3.11-slim-bookworm
RUN useradd --create-home app
# The path mirrors config.py's derived default and the compose volume mounts depend
# on it. An empty named volume seeds its ownership from this directory at first
# mount, which lets the non-root app user write the mounted circuit cache.
RUN install -d -o app -g app /home/app/.cache/zk-age-verifier/circuits
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER app
WORKDIR /app
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
