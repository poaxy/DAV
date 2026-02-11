"""Script management utilities for Dav.

This module is responsible for:
- Managing the scripts directory under the Dav config root
- Creating bash scripts from validated command text
- Persisting and loading script metadata for listing and future extensions
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from dav.config import get_scripts_dir
from dav.executor import DANGEROUS_PATTERNS, AUTOMATION_DANGEROUS_PATTERNS
from dav.terminal import render_error, render_warning

console = Console()

SCRIPTS_REGISTRY_FILENAME = "scripts.json"


@dataclass
class ScriptMetadata:
    """Metadata describing a user script managed by Dav."""

    id: str
    name: str
    description: str
    path: str
    created_at: str
    run_as_root: bool = False
    schedule: Optional[str] = None
    created_by: Optional[str] = None


def _ensure_scripts_dir() -> Path:
    """Ensure the scripts directory exists and return its path."""
    scripts_dir = get_scripts_dir()
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


def _get_registry_path() -> Path:
    scripts_dir = _ensure_scripts_dir()
    return scripts_dir / SCRIPTS_REGISTRY_FILENAME


def _load_registry() -> List[Dict[str, Any]]:
    """Load scripts registry from disk."""
    registry_path = _get_registry_path()
    if not registry_path.exists():
        return []
    try:
        with registry_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        # If registry is corrupted, warn but don't crash; start fresh
        render_warning(f"Scripts registry at {registry_path} is unreadable; starting a new one.")
        return []


def _save_registry(entries: List[Dict[str, Any]]) -> None:
    """Persist scripts registry to disk atomically."""
    registry_path = _get_registry_path()
    tmp_path = registry_path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp_path, registry_path)
    except Exception as e:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        render_error(f"Failed to save scripts registry: {e}")


def _slugify(text: str, max_length: int = 24) -> str:
    """Create a filesystem-friendly slug from arbitrary text."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "script"
    return text[:max_length]


def _make_short_name(description: str, max_words: int = 6, max_chars: int = 40) -> str:
    """Generate a short, human-friendly name from a longer description.

    - Takes only the first few words
    - Strips surrounding quotes/punctuation
    - Truncates to a reasonable character limit
    """
    desc = (description or "").strip()
    # Strip common surrounding quotes
    if (desc.startswith('"') and desc.endswith('"')) or (desc.startswith("'") and desc.endswith("'")):
        desc = desc[1:-1].strip()

    if not desc:
        return "Script"

    words = desc.split()
    short_words = words[:max_words]
    short = " ".join(short_words)

    if len(short) > max_chars:
        short = short[: max_chars - 1].rstrip() + "…"

    # Capitalize first letter, leave rest as-is for readability
    return short[0].upper() + short[1:] if short else "Script"


def _contains_dangerous_pattern(script_body: str) -> bool:
    """Check script body for dangerous patterns using existing executor rules."""
    body_lower = script_body.lower()
    all_patterns = list(DANGEROUS_PATTERNS) + list(AUTOMATION_DANGEROUS_PATTERNS)
    for pattern in all_patterns:
        if re.search(pattern, body_lower):
            return True
    return False


def create_script_from_commands(
    description: str,
    commands_text: str,
    schedule: Optional[str] = None,
    run_as_root: bool = False,
    created_by: Optional[str] = None,
    name: Optional[str] = None,
) -> ScriptMetadata:
    """Create a bash script file from a block of commands and register it.

    This assumes commands_text has already been validated/sanitized at a higher level.
    """
    if not commands_text.strip():
        raise ValueError("Cannot create script from empty commands.")

    if _contains_dangerous_pattern(commands_text):
        raise ValueError("Script contains commands blocked by safety rules.")

    scripts_dir = _ensure_scripts_dir()

    # Derive a short, human-friendly name if not provided
    display_name = name or _make_short_name(description)
    script_id = uuid.uuid4().hex[:8]
    slug = _slugify(display_name)
    script_filename = f"script-{script_id}-{slug}.sh"
    script_path = scripts_dir / script_filename

    header_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"# Generated by Dav from request: {description}",
        f"# Created at: {datetime.utcnow().isoformat()}Z",
        "",
    ]

    body = commands_text.strip()
    script_content = "\n".join(header_lines) + body + "\n"

    script_path.write_text(script_content, encoding="utf-8")
    script_path.chmod(0o700)

    metadata = ScriptMetadata(
        id=script_id,
        name=display_name,
        description=description,
        path=str(script_path),
        created_at=datetime.utcnow().isoformat() + "Z",
        run_as_root=run_as_root,
        schedule=schedule,
        created_by=created_by,
    )

    registry = _load_registry()
    registry.append(asdict(metadata))
    _save_registry(registry)

    return metadata


def list_scripts() -> List[ScriptMetadata]:
    """Return all registered scripts as ScriptMetadata objects."""
    entries = _load_registry()
    scripts: List[ScriptMetadata] = []
    for entry in entries:
        try:
            scripts.append(ScriptMetadata(**entry))
        except TypeError:
            # Skip malformed entries
            continue
    return scripts


def update_script_metadata(script_id: str, **changes: Any) -> Optional[ScriptMetadata]:
    """Update fields on a script metadata entry and persist it.

    Returns the updated ScriptMetadata if found, otherwise None.
    """
    entries = _load_registry()
    updated_entry: Optional[Dict[str, Any]] = None

    for entry in entries:
        if entry.get("id") == script_id:
            for key, value in changes.items():
                # Only apply fields that ScriptMetadata knows about
                if hasattr(ScriptMetadata, key) and value is not None:
                    entry[key] = value
            updated_entry = entry
            break

    if updated_entry is None:
        return None

    _save_registry(entries)
    try:
        return ScriptMetadata(**updated_entry)
    except TypeError:
        return None


def render_scripts_table(scripts: List[ScriptMetadata]) -> None:
    """Render a table of scripts using rich."""
    if not scripts:
        console.print("[yellow]No Dav scripts found. Use 'dav --script \"your request\"' to create one.[/yellow]")
        return

    table = Table(title="Dav Scripts")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Created", style="dim")
    table.add_column("Root", style="magenta", no_wrap=True)
    table.add_column("Schedule", style="green")
    table.add_column("Path", style="dim")

    for s in scripts:
        root_label = "yes" if s.run_as_root else "no"
        schedule = s.schedule or "-"
        table.add_row(s.id, s.name, s.created_at, root_label, schedule, s.path)

    console.print(table)


def show_script_source(script: ScriptMetadata) -> None:
    """Print the source of a script with syntax highlighting."""
    path = Path(script.path)
    if not path.exists():
        render_error(f"Script file not found: {path}")
        return

    content = path.read_text(encoding="utf-8")
    syntax = Syntax(content, "bash", theme="monokai", line_numbers=True)
    console.print(syntax)

