"""Reads `honest_agent_config.yml`: a project's non-secret settings, with one target per
agent being evaluated (like the targets in a dbt profile). It's optional -- without it, every setting comes
from flags, environment variables or built-in defaults, as before.

    results_path: ./honest_agent_results/results.duckdb   # shared by every target
    model: claude-haiku-4-5                               # can be overridden per target
    default_target: demo
    targets:
      demo:
        mcp_command: python mcp_server/server.py
        evals_dir: evals
      motherduck:
        mcp_url: https://api.motherduck.com/mcp
        bearer_token_env: MOTHERDUCK_TOKEN                # names the variable, never the secret
        evals_dir: evals_motherduck
        max_tool_steps: 10

Precedence, per setting: command-line flag > environment variable > this file > built-in
default (applied in cli.py). Relative paths are resolved from the file's own folder, so a
run from a subfolder still finds them.

Any value can read an environment variable (from `.env` or the shell) the way dbt does,
so account URLs can stay out of a committed file:

    mcp_url: "{{ env_var('SNOWFLAKE_MCP_URL') }}"
    max_tool_steps: "{{ env_var('MAX_TOOL_STEPS', '10') }}"   # with a default

Top-level values are read when the file loads; a target's only when that target is used,
so an unset variable only matters for the target that needs it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILE_NAME = "honest_agent_config.yml"
EXAMPLE_CONFIG_FILE_NAME = "honest_agent_config.example.yml"

# Settings any target can set, or the top level can set for every target.
_SHARED_KEYS = {"model", "judge_model", "max_tool_steps"}
_TOP_LEVEL_KEYS = _SHARED_KEYS | {"results_path", "default_target", "targets"}
# results_path stays top-level only: every agent's results go in one file, so the report
# can compare them side by side.
_TARGET_KEYS = _SHARED_KEYS | {
    "mcp_command",
    "mcp_url",
    "bearer_token_env",
    "evals_dir",
    "ignore_tools",
    "mcp_env",
    "agent_name",
    # The connection's database/schema, where a bare table name runs (provenance.py).
    "default_database",
    "default_schema",
}
_PATH_KEYS = {"results_path", "evals_dir"}
_INT_KEYS = {"max_tool_steps"}

# dbt's `{{ env_var('NAME') }}` / `{{ env_var('NAME', 'default') }}`, single or double quotes.
_ENV_VAR = re.compile(r"""\{\{\s*env_var\(\s*(['"])([A-Za-z_][A-Za-z0-9_]*)\1\s*(?:,\s*(['"])(.*?)\3\s*)?\)\s*\}\}""")


class ConfigError(ValueError):
    pass


@dataclass
class Target:
    name: str
    # Only the settings the file actually sets; paths already resolved to absolute.
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    path: Path
    results_path: str | None
    default_target: str | None
    # Each target's settings as written: env_var() and paths are resolved by target().
    targets: dict[str, dict[str, Any]]
    shared: dict[str, Any]

    def target(self, name: str | None) -> Target:
        """The named target, else `default_target`, else the only target if there is one."""
        if name is None:
            name = self.default_target
        if name is None and len(self.targets) == 1:
            name = next(iter(self.targets))
        if name is None:
            raise ConfigError(
                f"{self.path.name} has several targets and no default_target. "
                f"Pick one with --target ({', '.join(self.targets)})."
            )
        if name not in self.targets:
            raise ConfigError(f"No target {name!r} in {self.path.name}. Targets: {', '.join(self.targets) or 'none'}.")
        where = f"target {name!r} in {self.path.name}"
        settings = _resolve_paths(_render(self.targets[name], where), self.path.parent)
        return Target(name, {**self.shared, **settings})


def find_config_file(start: Path) -> Path | None:
    """`honest_agent_config.yml` in `start` or the nearest parent folder, like .env."""
    for folder in (start, *start.parents):
        candidate = folder / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate
    return None


def missing_config_hint(start: Path) -> str:
    """When no config file is found, points to the example one (in `start` or a parent folder) to copy."""
    for folder in (start, *start.parents):
        example = folder / EXAMPLE_CONFIG_FILE_NAME
        if example.is_file():
            return f" Copy {example} to {folder / CONFIG_FILE_NAME} and fill in your own values."
    return ""


def load_config(path: Path) -> Config:
    doc = yaml.safe_load(path.read_text()) or {}
    if not isinstance(doc, dict):
        raise ConfigError(f"{path.name} must be a mapping of settings.")
    _check_keys(doc, _TOP_LEVEL_KEYS, f"{path.name}")
    raw_targets = doc.get("targets")
    doc = {**_render({k: v for k, v in doc.items() if k != "targets"}, path.name), "targets": raw_targets}

    base = path.parent
    targets: dict[str, dict[str, Any]] = {}
    for name, settings in (doc.get("targets") or {}).items():
        settings = settings or {}
        where = f"target {name!r} in {path.name}"
        _check_keys(settings, _TARGET_KEYS, where)
        if settings.get("mcp_command") and settings.get("mcp_url"):
            raise ConfigError(f"Set either mcp_command or mcp_url in {where}, not both.")
        targets[str(name)] = settings

    default_target = doc.get("default_target")
    if default_target is not None and default_target not in targets:
        raise ConfigError(
            f"default_target {default_target!r} in {path.name} isn't one of its targets "
            f"({', '.join(targets) or 'none'})."
        )

    return Config(
        path=path,
        results_path=_resolve_paths(doc, base).get("results_path"),
        default_target=default_target,
        targets=targets,
        shared={key: doc[key] for key in _SHARED_KEYS if key in doc},
    )


def _render(settings: dict[str, Any], where: str) -> dict[str, Any]:
    """Replaces each `{{ env_var(...) }}` with the variable's value (or its default)."""
    rendered = {}
    for key, value in settings.items():
        rendered[key] = _render_value(value, f"{key} in {where}")
        if key in _INT_KEYS and isinstance(rendered[key], str):
            try:
                rendered[key] = int(rendered[key])
            except ValueError:
                raise ConfigError(f"{key} in {where} must be a whole number, got {rendered[key]!r}.") from None
    return rendered


def _render_value(value: Any, where: str) -> Any:
    if isinstance(value, list):
        return [_render_value(item, where) for item in value]
    if not isinstance(value, str):
        return value

    def substitute(match: re.Match) -> str:
        name, default = match.group(2), match.group(4)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ConfigError(
            f"{where} reads env_var('{name}'), but {name} isn't set. Add it to .env or export it, "
            f"or give a default: env_var('{name}', '...')."
        )

    rendered = _ENV_VAR.sub(substitute, value)
    if "{{" in rendered:
        raise ConfigError(
            f"{where}: only {{{{ env_var('NAME') }}}} or {{{{ env_var('NAME', 'default') }}}} is supported."
        )
    return rendered


def _check_keys(settings: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(settings) - allowed)
    if unknown:
        raise ConfigError(
            f"Unknown setting(s) in {where}: {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}."
        )


def _resolve_paths(settings: dict[str, Any], base: Path) -> dict[str, Any]:
    """Relative paths become relative to the config file's folder; a MotherDuck results
    database (md:<name>) isn't a path and stays as written."""
    return {
        key: str(base / value) if key in _PATH_KEYS and value is not None and not value.startswith("md:") else value
        for key, value in settings.items()
    }
