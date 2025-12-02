"""Cron job management utilities for Dav."""

import re
import shutil
import subprocess
import tempfile
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
    Validate cron syntax (enhanced validation).
    
    Args:
        cron_string: Cron schedule string (e.g., "0 3 * * *")
    
    Returns:
        True if valid, False otherwise
    """
    from dav.schedule_parser import validate_and_normalize_cron
    
    is_valid, _, _ = validate_and_normalize_cron(cron_string)
    return is_valid


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


def extract_schedule_from_cron_entry(cron_entry: str) -> Optional[str]:
    """
    Extract the schedule (first 5 fields) from a cron entry.
    
    Args:
        cron_entry: Full cron entry string
    
    Returns:
        Schedule string (e.g., "0 3 * * *") or None if invalid format
    """
    parts = cron_entry.strip().split()
    if len(parts) >= 5:
        return " ".join(parts[:5])
    return None


def extract_task_from_cron_entry(cron_entry: str) -> Optional[str]:
    """
    Extract task description from a dav automation cron entry.
    
    Parses entries like: "0 3 * * * /path/to/dav --automation \"task description\""
    
    Args:
        cron_entry: Full cron entry string
    
    Returns:
        Task description string or None if not a dav automation cron job
    """
    # Split into parts (schedule + command)
    parts = cron_entry.strip().split(None, 5)
    if len(parts) < 6:
        return None
    
    command = parts[5]
    
    # Check if it's a dav automation command
    if "--automation" not in command:
        return None
    
    # Find the --automation flag and extract the task
    # Pattern: ... --automation "task" or ... --automation 'task' or ... --automation task
    automation_match = re.search(r'--automation\s+(?:"([^"]*)"|\'([^\']*)\'|(\S+))', command)
    if automation_match:
        # Return the task (could be in any of the three groups)
        task = automation_match.group(1) or automation_match.group(2) or automation_match.group(3)
        return task
    
    return None


def normalize_task(task: str) -> str:
    """
    Normalize task description for comparison.
    
    - Convert to lowercase
    - Strip leading/trailing whitespace
    - Normalize multiple spaces to single space
    - Remove extra quotes if present
    
    Args:
        task: Task description string
    
    Returns:
        Normalized task string
    """
    if not task:
        return ""
    
    # Convert to lowercase
    normalized = task.lower()
    
    # Strip quotes if present (both single and double)
    normalized = normalized.strip('"\'')
    
    # Strip whitespace
    normalized = normalized.strip()
    
    # Normalize multiple spaces to single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized


def check_cron_duplicate(
    cron_entry: str, 
    existing_crontab: Optional[List[str]] = None
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Check for duplicate cron jobs with different match modes.
    
    Args:
        cron_entry: New cron entry to check
        existing_crontab: Existing crontab entries (if None, fetches current)
    
    Returns:
        Tuple of (match_type, existing_entry, existing_schedule)
        - match_type: "exact", "task_and_schedule", "task_only", or "none"
        - existing_entry: The matching existing cron entry if found
        - existing_schedule: The schedule of the matching entry if found
    """
    if existing_crontab is None:
        existing_crontab = get_current_crontab()
    
    # Extract task and schedule from new cron entry
    new_task = extract_task_from_cron_entry(cron_entry)
    new_schedule = extract_schedule_from_cron_entry(cron_entry)
    
    # If not a dav automation job, can't compare
    if not new_task or not new_schedule:
        return "none", None, None
    
    new_task_normalized = normalize_task(new_task)
    
    # Check against existing entries
    for line in existing_crontab:
        if line.strip().startswith("#"):
            continue
        
        line_stripped = line.strip()
        
        # 1. Check exact match first
        if line_stripped == cron_entry.strip():
            # Extract schedule for consistency (though exact match means schedule is same)
            existing_schedule = extract_schedule_from_cron_entry(line_stripped)
            return "exact", line_stripped, existing_schedule if existing_schedule else new_schedule
        
        # 2. Extract task and schedule from existing entry
        existing_task = extract_task_from_cron_entry(line_stripped)
        existing_schedule = extract_schedule_from_cron_entry(line_stripped)
        
        # Skip if not a dav automation job
        if not existing_task or not existing_schedule:
            continue
        
        existing_task_normalized = normalize_task(existing_task)
        
        # 3. Check normalized task + schedule match
        if existing_task_normalized == new_task_normalized and existing_schedule == new_schedule:
            return "task_and_schedule", line_stripped, existing_schedule
        
        # 4. Check normalized task only (different schedule)
        if existing_task_normalized == new_task_normalized and existing_schedule != new_schedule:
            return "task_only", line_stripped, existing_schedule
    
    return "none", None, None


def find_similar_cron_jobs(
    task: str, 
    schedule: str, 
    existing_crontab: Optional[List[str]] = None
) -> List[Tuple[str, str]]:
    """
    Find all cron jobs with the same normalized task but different schedules.
    
    Args:
        task: Task description to search for
        schedule: Schedule to exclude from results (current/new schedule)
        existing_crontab: Existing crontab entries (if None, fetches current)
    
    Returns:
        List of (existing_schedule, existing_entry) tuples
    """
    if existing_crontab is None:
        existing_crontab = get_current_crontab()
    
    task_normalized = normalize_task(task)
    similar_jobs = []
    
    for line in existing_crontab:
        if line.strip().startswith("#"):
            continue
        
        line_stripped = line.strip()
        existing_task = extract_task_from_cron_entry(line_stripped)
        existing_schedule = extract_schedule_from_cron_entry(line_stripped)
        
        # Skip if not a dav automation job
        if not existing_task or not existing_schedule:
            continue
        
        existing_task_normalized = normalize_task(existing_task)
        
        # Check if task matches but schedule is different
        if existing_task_normalized == task_normalized and existing_schedule != schedule:
            similar_jobs.append((existing_schedule, line_stripped))
    
    return similar_jobs


def _write_crontab(crontab_lines: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Write crontab entries to the system crontab.
    
    This is a helper function to avoid code duplication.
    
    Args:
        crontab_lines: List of crontab entry lines
    
    Returns:
        Tuple of (success, error_message)
        - success: True if crontab was written successfully
        - error_message: Error message if failed, None if successful
    """
    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".crontab") as tmp_file:
        tmp_file.write("\n".join(crontab_lines))
        if crontab_lines:  # Add newline if not empty
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
            return True, None
        else:
            return False, result.stderr
    
    except Exception as e:
        # Clean up temp file on error
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass
        return False, str(e)


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


def replace_cron_job(old_entry: str, new_schedule: str, new_task: str) -> Tuple[bool, str]:
    """
    Replace an existing cron job with a new schedule and/or task.
    
    Args:
        old_entry: The existing cron entry to replace
        new_schedule: New schedule for the cron job
        new_task: New task description
    
    Returns:
        Tuple of (success, message)
    """
    # Validate cron syntax
    if not validate_cron_syntax(new_schedule):
        return False, f"Invalid cron syntax: {new_schedule}"
    
    # Detect dav path
    dav_path = detect_dav_path()
    
    # Build new cron entry
    new_cron_entry = f'{new_schedule} {dav_path} --automation "{new_task}"'
    
    # Get current crontab
    current_crontab = get_current_crontab()
    
    # Remove old entry and add new one
    new_crontab = []
    old_found = False
    
    for line in current_crontab:
        if line.strip() == old_entry.strip():
            old_found = True
            # Replace with new entry
            new_crontab.append(new_cron_entry)
        else:
            new_crontab.append(line)
    
    if not old_found:
        return False, "Old cron entry not found in crontab"
    
    # Write crontab using helper function
    success, error_msg = _write_crontab(new_crontab)
    
    if success:
        return True, f"Replaced cron job: {new_task} (schedule: {new_schedule})"
    else:
        return False, f"Failed to install crontab: {error_msg}" if error_msg else "Failed to install crontab"


def add_cron_job(schedule: str, task: str, auto_confirm: bool = True) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Add cron job to user's crontab.
    
    Args:
        schedule: Cron schedule (e.g., "0 3 * * *")
        task: Task description for dav command
        auto_confirm: Whether to auto-confirm (no prompts)
    
    Returns:
        Tuple of (success, message, match_type, existing_entry)
        - success: True if job was added, False otherwise
        - message: Success or error message
        - match_type: "exact", "task_and_schedule", "task_only", or None
        - existing_entry: The matching existing cron entry if found
    """
    # Validate cron syntax
    if not validate_cron_syntax(schedule):
        return False, f"Invalid cron syntax: {schedule}", None, None
    
    # Detect dav path
    dav_path = detect_dav_path()
    
    # Build cron entry
    cron_entry = f'{schedule} {dav_path} --automation "{task}"'
    
    # Check for duplicates using enhanced detection
    match_type, existing_entry, existing_schedule = check_cron_duplicate(cron_entry)
    
    # Handle different match types
    if match_type == "exact":
        return False, "Exact duplicate cron job already exists", "exact", existing_entry
    elif match_type == "task_and_schedule":
        return False, f"Task '{task}' is already scheduled at {existing_schedule}", "task_and_schedule", existing_entry
    elif match_type == "task_only":
        # Return False but let CLI handle the prompt
        return False, f"Task '{task}' already exists with a different schedule", "task_only", existing_entry
    
    # No duplicate found, proceed with adding
    # Get current crontab
    current_crontab = get_current_crontab()
    
    # Add new entry
    new_crontab = current_crontab + [cron_entry]
    
    # Write crontab using helper function
    success, error_msg = _write_crontab(new_crontab)
    
    if success:
        return True, f"Scheduled: {task} (schedule: {schedule})", None, None
    else:
        error_message = f"Failed to install crontab: {error_msg}" if error_msg else "Failed to install crontab"
        return False, error_message, None, None


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



