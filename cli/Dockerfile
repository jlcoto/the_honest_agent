# honest-agent in a container, for scheduled runs outside GitHub Actions.
# Build from cli/: `docker build -t honest-agent cli`. Published as ghcr.io/jlcoto/honest-agent.
# See "Run it in a container" in the docs.
#
# Both base images are pinned to a digest; Dependabot (.github/dependabot.yml) proposes
# the updates.
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913

# uv stays in the image so MCP servers started with `uvx` work.
COPY --from=uv /uv /uvx /bin/

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

# Run as a normal user, not root: a bug in a dependency or an MCP server gets no more
# rights than it needs, files written to the mounted project belong to id 1000, and
# `uvx` has a home it can write its cache to.
RUN useradd --create-home --uid 1000 honest && mkdir -p /project && chown honest:honest /project
USER honest
ENV HOME=/home/honest

# Mount the project (honest_agent_config.yml, evals/, .env) here: honest-agent looks for
# its config and .env from the folder it runs in.
WORKDIR /project

ENTRYPOINT ["honest-agent"]
CMD ["--help"]
