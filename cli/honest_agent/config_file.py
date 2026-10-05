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
        max_tool_turns: 10

Precedence, per setting: command-line flag > environment variable > this file > built-in
default (applied in cli.py). Relative paths are resolved from the file's own folder, so a
run from a subfolder still finds them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILE_NAME = "honest_agent_config.yml"
EXAMPLE_CONFIG_FILE_NAME = "honest_agent_config.example.yml"

# Settings any target can set, or the top level can set for every target.
_SHARED_KEYS = {"model", "judge_model", "max_tool_turns"}
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
}
_PATH_KEYS = {"results_path", "evals_dir"}


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
        return Target(name, {**self.shared, **self.targets[name]})


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

    base = path.parent
    targets: dict[str, dict[str, Any]] = {}
    for name, settings in (doc.get("targets") or {}).items():
        settings = settings or {}
        where = f"target {name!r} in {path.name}"
        _check_keys(settings, _TARGET_KEYS, where)
        if settings.get("mcp_command") and settings.get("mcp_url"):
            raise ConfigError(f"Set either mcp_command or mcp_url in {where}, not both.")
        targets[str(name)] = _resolve_paths(settings, base)

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


def _check_keys(settings: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(settings) - allowed)
    if unknown:
        raise ConfigError(
            f"Unknown setting(s) in {where}: {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}."
        )


def _resolve_paths(settings: dict[str, Any], base: Path) -> dict[str, Any]:
    return {
        key: str(base / value) if key in _PATH_KEYS and value is not None else value for key, value in settings.items()
    }
