---
title: Run it in a container
description: The honest-agent Docker image, for scheduled runs outside GitHub Actions.
---

:::caution[An example, not a security review]
This is one setup we tested, shown as an example. Don't copy it blindly: check each step
against your company's security policies, and adapt it before you use it with real data.
See [Your setup, your responsibility](/docs/team/#your-setup-your-responsibility).
:::

For schedulers that run containers: GitLab CI, Airflow, a Kubernetes CronJob, an ECS
scheduled task. On your own machine, the [uv install](/docs/getting-started/) is simpler.

:::note[What was tested]
CI builds the image on every change to `cli/` and checks that it starts: `--version`,
`uvx`, and `init --example` followed by `debug`, which starts the demo MCP server and
lists its tools. *Not tested yet:* a run against a real agent, and any of the schedulers
above.
:::

## The image

Each release after v0.2.0 is published to GitHub's registry, tagged with its version
without the `v` (v0.3.0 is `0.3.0`):

```bash
docker pull ghcr.io/jlcoto/honest-agent:<version>
```

Pin the version you tested, as with `uv add`. The image has Python, honest-agent and
[uv](https://docs.astral.sh/uv/), so MCP servers started with `uvx` work as they do on
your machine. Its entrypoint is `honest-agent`: anything after the image name is the
command, like `run` or `report`.

To build it yourself, from a clone of the repository:

```bash
docker build -t honest-agent cli
```

## Mount the project

honest-agent looks for `honest_agent_config.yml` and `.env` from the folder it runs in,
and in the image that's `/project`. Mount your project there:

```bash
docker run --rm -v "$PWD:/project" ghcr.io/jlcoto/honest-agent:<version> run
```

A few things about it:

- **`.env` is optional.** In a scheduler, pass the API keys and tokens as environment
  variables from its secret store (`-e ANTHROPIC_API_KEY`, a Kubernetes Secret, ...).
  Variables already set win over `.env`. Don't use Docker's `--env-file .env`: it keeps
  quotes as part of the value, where `.env` strips them.
- **A local `mcp_command` runs inside the container,** in the folder of
  `honest_agent_config.yml`, so every path in it must exist there. A project made with
  `init --example` on your machine has your machine's Python in it: run
  `init --example` in the container instead.
- **The results file is in the mounted folder** (`honest_agent_results/` by default).
  A scheduler throws the container away after each run, so keep the results somewhere
  that lasts: [MotherDuck](/docs/team/results-motherduck/), or a file you copy in and out
  as in [Store results in S3](/docs/team/results-s3/). The image has no AWS CLI: add it
  in your own image (below), or copy the file in a step before and after.
- **The container runs as root,** so on Linux the files it writes belong to root. To
  write them as yourself, add `--user "$(id -u):$(id -g)" -e HOME=/tmp` (`uvx` needs a
  home folder it can write to).

## Look at the report

`report` writes the report into the mounted folder, like on your machine:

```bash
docker run --rm -v "$PWD:/project" ghcr.io/jlcoto/honest-agent:<version> report
```

`serve` only answers on 127.0.0.1, and inside a container that's the container itself,
so publishing a port (`-p 8000:8000`) doesn't reach it. On Linux, share the machine's
network instead:

```bash
docker run --rm --network host -v "$PWD:/project" ghcr.io/jlcoto/honest-agent:<version> serve --no-open-browser
```

Then open http://127.0.0.1:8000/. Elsewhere, run `serve` outside the container, from the
project folder:

```bash
uvx --from "git+https://github.com/jlcoto/the_honest_agent@<tag>#subdirectory=cli" honest-agent serve
```

For a team, host the report behind a sign-in instead: see
[Running it for a team](/docs/team/#pick-one-of-each).

## Build on top of it

The image has what honest-agent and `uvx` need, nothing more. If your MCP server needs
Node.js, extra Python packages or another tool, build your own image from this one:

```dockerfile
FROM ghcr.io/jlcoto/honest-agent:<version>

# Node.js, for MCP servers started with npx (Debian's version: check it's new enough
# for your server).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# A server published as a Python package, installed once instead of on every run.
# mcp_command is then just its name.
ENV UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin
RUN uv tool install <server-package>

# A server script of your own, with its packages in a separate environment so they
# can't clash with honest-agent's. mcp_command: "/opt/mcp/bin/python mcp_server/server.py"
RUN uv venv /opt/mcp && uv pip install --python /opt/mcp/bin/python <packages>
```

The local server gets only `PATH`, `HOME` and a few other basics, plus the variables in
the target's `mcp_env`. An `ENV` you add for the server reaches it only once its name is
in `mcp_env`.
