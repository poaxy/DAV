from __future__ import annotations

"""Command plan parsing and validation helpers."""

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CommandPlan:
    """Structured command plan returned by the language model."""

    commands: List[str]
    sudo: bool = False
    platform: Optional[List[str]] = field(default=None)
    cwd: Optional[str] = None
    notes: Optional[str] = None


class CommandPlanError(ValueError):
    """Raised when the command plan is missing or malformed."""


JSON_BLOCK_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
JSON_INLINE_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _normalise_platform(value: Optional[object]) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else None
    if isinstance(value, list):
        results = []
        for item in value:
            if isinstance(item, str) and item.strip():
                results.append(item.strip())
        return results or None
    raise CommandPlanError("'platform' must be a string or list of strings")


def extract_command_plan(response_text: str) -> CommandPlan:
    """Extract and validate a command plan from the model response."""

    candidate_json: Optional[str] = None

    match = JSON_BLOCK_PATTERN.search(response_text)
    if match:
        candidate_json = match.group(1)
    else:
        match = JSON_INLINE_PATTERN.search(response_text)
        if match:
            candidate_json = match.group(0)

    if not candidate_json:
        raise CommandPlanError("No JSON command plan found in response")

    try:
        plan_data = json.loads(candidate_json)
    except json.JSONDecodeError as exc:
        raise CommandPlanError(f"Invalid JSON command plan: {exc}") from exc

    if not isinstance(plan_data, dict):
        raise CommandPlanError("Command plan must be a JSON object")

    commands = plan_data.get("commands")
    if not isinstance(commands, list) or not commands:
        raise CommandPlanError("'commands' must be a non-empty list")

    cleaned_commands: List[str] = []
    for entry in commands:
        if not isinstance(entry, str):
            raise CommandPlanError("Each command must be a string")
        command = entry.strip()
        if not command:
            continue
        cleaned_commands.append(command)

    if not cleaned_commands:
        raise CommandPlanError("No valid commands found in plan")

    sudo_flag = plan_data.get("sudo", False)
    if isinstance(sudo_flag, str):
        sudo_flag = sudo_flag.lower() in {"true", "1", "yes"}
    elif not isinstance(sudo_flag, bool):
        sudo_flag = bool(sudo_flag)

    cwd = plan_data.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise CommandPlanError("'cwd' must be a string if provided")

    notes = plan_data.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise CommandPlanError("'notes' must be a string if provided")

    platform = _normalise_platform(plan_data.get("platform"))

    return CommandPlan(
        commands=cleaned_commands,
        sudo=bool(sudo_flag),
        platform=platform,
        cwd=cwd.strip() if isinstance(cwd, str) and cwd.strip() else None,
        notes=notes.strip() if isinstance(notes, str) and notes.strip() else None,
    )

