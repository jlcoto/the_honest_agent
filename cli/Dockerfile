# honest-agent in a container, for scheduled runs outside GitHub Actions.
# Build from cli/: `docker build -t honest-agent cli`. Published as ghcr.io/jlcoto/honest-agent.
# See "Run it in a container" in the docs.
FROM python:3.13-slim

# uv stays in the image so MCP servers started with `uvx` work.
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /opt/honest-agent

# Dependencies first, from the lockfile, so changing the code doesn't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

ENV PATH="/opt/honest-agent/.venv/bin:$PATH"

# Mount the project (honest_agent_config.yml, evals/, .env) here: honest-agent looks for
# its config and .env from the folder it runs in.
WORKDIR /project

ENTRYPOINT ["honest-agent"]
CMD ["--help"]
