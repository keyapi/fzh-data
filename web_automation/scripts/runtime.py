"""Capability matrix runtime: pure Python, no third-party imports except yaml.

This module is imported by the root-environment dispatcher, so it must stay
light. Capabilities and routing decisions live in web_automation/capabilities.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Union

try:  # root env and child env both declare pyyaml
    import yaml
except Exception:  # pragma: no cover - only triggers on broken installs
    yaml = None

MODES = frozenset(
    {"API_ONLY", "API_FIRST_BROWSER_FALLBACK", "BROWSER_ONLY", "MANUAL_CONFIRM"}
)
RISKS = frozenset({"read", "write", "interactive"})
BLOCKING_STATES = frozenset(
    {"NEED_BROWSER", "NEED_LOGIN", "NEED_OCR", "NEED_USER_CONFIRMATION", "BLOCKED"}
)

_CURRENT_SCHEMA = 1
_FAILURE_CODE_RE = re.compile(r"^FAILURE_CODE=([A-Z][A-Z0-9_]+)\s*$", re.M)
_PROFILE_DIRS = {
    "tongtu": ("chrome-profile", "tongtu-profile-login"),
    "sellfox": ("sellfox-profile", "sellfox-profile-login"),
}


@dataclass(frozen=True)
class ProcResult:
    returncode: int
    failure_code: str | None


def parse_failure_code(output: str) -> str | None:
    matches = _FAILURE_CODE_RE.findall(output)
    return matches[-1] if matches else None


def run_result_from_output(returncode: int, output: str) -> ProcResult:
    if returncode == 0:
        return ProcResult(0, None)
    return ProcResult(returncode, parse_failure_code(output) or "UNCLASSIFIED_FAILURE")


def platform_profile_present(platform: str, web_root: Path) -> bool:
    names = _PROFILE_DIRS.get(platform)
    if not names:
        return True
    return any((web_root / name).is_dir() for name in names)


def _schema_version() -> int:
    return _CURRENT_SCHEMA


@dataclass(frozen=True)
class Capability:
    task: str
    platform: str
    mode: str
    risk: str
    primary: str
    fallback: Union[str, None]
    allowed_fallback_codes: tuple[str, ...]
    blocked_fallback_codes: tuple[str, ...]
    verify: str
    implementation: dict
    contract: str
    last_verified: str
    schema_version: int = _CURRENT_SCHEMA


def load_capabilities(path: Path) -> dict[str, Capability]:
    if yaml is None:
        raise RuntimeError("pyyaml is required to load capabilities.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != _schema_version():
        raise ValueError(
            f"invalid capability matrix {path}: expected version {_schema_version()}"
        )
    caps = raw.get("capabilities")
    if not isinstance(caps, dict):
        raise ValueError(f"invalid capability matrix {path}: missing capabilities map")

    matrix: dict[str, Capability] = {}
    for task, body in caps.items():
        if not isinstance(body, dict):
            raise ValueError(f"invalid capability {task}: body must be a mapping")
        try:
            matrix[task] = Capability(
                task=task,
                platform=body["platform"],
                mode=body["mode"],
                risk=body["risk"],
                primary=body["primary"],
                fallback=body.get("fallback"),
                allowed_fallback_codes=tuple(body.get("allowed_fallback_codes", [])),
                blocked_fallback_codes=tuple(body.get("blocked_fallback_codes", [])),
                verify=body["verify"],
                implementation=body["implementation"],
                contract=body["contract"],
                last_verified=body["last_verified"],
            )
        except KeyError as exc:
            raise ValueError(f"invalid capability {task}: missing field {exc.args[0]}")
    return matrix


def resolve_capability(matrix: dict[str, Capability], task: str) -> Capability:
    try:
        return matrix[task]
    except KeyError:
        raise KeyError(f"unknown capability: {task}")


def classify_failure(
    capability: Capability, code: str
) -> Literal["fallback", "blocked"]:
    if code in capability.allowed_fallback_codes:
        return "fallback"
    if code in capability.blocked_fallback_codes:
        return "blocked"
    return "blocked"  # unclassified failures must not silently fall back


def build_script_command(
    root: Path,
    capability: Capability,
    passthrough: list[str],
    channel: str | None = None,
) -> list[str]:
    impl = capability.implementation
    script_rel = impl.get(channel or capability.primary)
    if not script_rel:
        raise ValueError(
            f"capability {capability.task} has no implementation for channel "
            f"{channel or capability.primary}"
        )
    # Existence of the migrated script is asserted by the Task 4 entrypoint
    # test (tests/web_automation/test_migrated_entrypoints.py), not here.
    script = (root / "web_automation" / script_rel).resolve()
    configured = list(impl.get(f"{capability.primary}_args", []))
    return [
        "uv",
        "run",
        "--project",
        str((root / "web_automation").resolve()),
        "python",
        str(script),
        *configured,
        *passthrough,
    ]


__all__ = [
    "BLOCKING_STATES",
    "MODES",
    "RISKS",
    "Capability",
    "ProcResult",
    "build_script_command",
    "classify_failure",
    "load_capabilities",
    "parse_failure_code",
    "platform_profile_present",
    "resolve_capability",
    "run_result_from_output",
    "_schema_version",
]
