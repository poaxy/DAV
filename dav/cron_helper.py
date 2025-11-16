"""Cron job management utilities for Dav."""

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def detect_dav_path() -> str:
    """
    Detect where dav command is installed.
    
    Returns:
        Path to dav command
    """
    dav_path = shutil.which("dav")
    if dav_path:
        return dav_path
    
    # Fallback to common locations
    common_paths = [
        "/usr/local/bin/dav",
        "/usr/bin/dav",
        "~/.local/bin/dav",
    ]
    
    for path in common_paths:
        expanded = Path(path).expanduser()
        if expanded.exists():
            return str(expanded)
    
    # Default fallback
    return "/usr/local/bin/dav"


def validate_cron_syntax(cron_string: str) -> bool:
    """
    Validate cron syntax (basic validation).
    
    Args:
        cron_string: Cron schedule string (e.g., "0 3 * * *")
    
    Returns:
        True if valid, False otherwise
    """
    # Basic cron format: minute hour day month weekday
    parts = cron_string.strip().split()
    
    if len(parts) != 5:
        return False
    
    # Validate each part (basic check)
    for part in parts:
        if not re.match(r'^[\d\*\/\-,]+$', part):
            return False
    
    return True


def parse_schedule_to_cron(natural_language: str) -> Optional[str]:
    """
    Parse natural language schedule to cron format (basic patterns).
    
    This is a fallback - AI should handle most parsing.
    
    Args:
        natural_language: Natural language schedule (e.g., "every night at 3")
    
    Returns:
        Cron format string or None if cannot parse
    """
    text = natural_language.lower().strip()
    
    # Common patterns
    patterns = {
        r"every\s+night\s+at\s+(\d+)": lambda m: f"0 {m.group(1)} * * *",
        r"daily\s+at\s+(\d+)": lambda m: f"0 {m.group(1)} * * *",
        r"at\s+(\d+)\s+am": lambda m: f"0 {m.group(1)} * * *",
        r"at\s+(\d+)\s+pm": lambda m: f"0 {int(m.group(1)) + 12} * * *",
        r"every\s+day": "0 0 * * *",
        r"weekly": "0 0 * * 0",
        r"monthly": "0 0 1 * *",
    }
    
    for pattern, replacement in patterns.items():
        match = re.search(pattern, text)
        if match:
            if callable(replacement):
                return replacement(match)
            return replacement
    
    return None


def get_current_crontab() -> List[str]:
    """
    Get current crontab entries.
    
    Returns:
        List of crontab lines
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode == 0:
            return [line for line in result.stdout.split("\n") if line.strip()]
        else:
            # No crontab exists yet
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []


def is_duplicate_cron_job(cron_entry: str, existing_crontab: Optional[List[str]] = None) -> bool:
    """
    Check if cron job already exists.
    
    Args:
        cron_entry: New cron entry to check
        existing_crontab: Existing crontab entries (if None, fetches current)
    
    Returns:
        True if duplicate exists, False otherwise
    """
    if existing_crontab is None:
        existing_crontab = get_current_crontab()
    
    # Extract the command part (everything after the schedule)
    new_parts = cron_entry.strip().split(None, 5)
    if len(new_parts) < 6:
        return False
    
    new_command = " ".join(new_parts[5:])
    
    # Check against existing entries
    for line in existing_crontab:
        if line.strip().startswith("#"):
            continue
        
        parts = line.strip().split(None, 5)
        if len(parts) >= 6:
            existing_command = " ".join(parts[5:])
            # Compare commands (ignore schedule differences)
            if new_command == existing_command:
                return True
    
    return False


def add_cron_job(schedule: str, task: str, auto_confirm: bool = True) -> Tuple[bool, str]:
    """
    Add cron job to user's crontab.
    
    Args:
        schedule: Cron schedule (e.g., "0 3 * * *")
        task: Task description for dav command
        auto_confirm: Whether to auto-confirm (no prompts)
    
    Returns:
        Tuple of (success, message)
    """
    # Validate cron syntax
    if not validate_cron_syntax(schedule):
        return False, f"Invalid cron syntax: {schedule}"
    
    # Detect dav path
    dav_path = detect_dav_path()
    
    # Build cron entry
    cron_entry = f'{schedule} {dav_path} --automation "{task}"'
    
    # Check for duplicates
    if is_duplicate_cron_job(cron_entry):
        return False, "Duplicate cron job already exists"
    
    # Get current crontab
    current_crontab = get_current_crontab()
    
    # Add new entry
    new_crontab = current_crontab + [cron_entry]
    
    # Write to temporary file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".crontab") as tmp_file:
        tmp_file.write("\n".join(new_crontab))
        if new_crontab:  # Add newline if not empty
            tmp_file.write("\n")
        tmp_path = tmp_file.name
    
    try:
        # Install new crontab
        result = subprocess.run(
            ["crontab", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Clean up temp file
        Path(tmp_path).unlink()
        
        if result.returncode == 0:
            return True, f"Scheduled: {task} (schedule: {schedule})"
        else:
            return False, f"Failed to install crontab: {result.stderr}"
    
    except Exception as e:
        # Clean up temp file on error
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass
        return False, f"Error adding cron job: {str(e)}"


def show_cron_examples() -> str:
    """Show example cron configurations."""
    return """
Example Cron Jobs:

1. Daily system maintenance at 2 AM:
   0 2 * * * /usr/local/bin/dav --automation "daily system maintenance"

2. Weekly log analysis on Monday at 3 AM:
   0 3 * * 1 /usr/local/bin/dav --automation "analyze system logs and report issues"

3. System health check every 6 hours:
   0 */6 * * * /usr/local/bin/dav --automation "check system health"

4. Package updates daily at 4 AM:
   0 4 * * * /usr/local/bin/dav --automation "check for and install security updates"

Use 'dav --schedule' to set up cron jobs easily with natural language.
"""


def show_sudoers_examples() -> str:
    """Show sudoers NOPASSWD configuration examples."""
    return """
Sudoers NOPASSWD Configuration:

1. Create sudoers file:
   sudo visudo -f /etc/sudoers.d/dav-automation

2. Add specific commands (recommended for security):
   username ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/bin/systemctl, /usr/bin/journalctl

3. Or allow all commands (less secure):
   username ALL=(ALL) NOPASSWD: ALL

4. Test configuration:
   sudo -n true

Note: Replace 'username' with your actual username.
Be specific with commands for better security.
"""

