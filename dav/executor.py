"""Command execution utilities for Dav."""
"""Secure command execution for Dav."""

import glob
import os
import re
import shlex
import subprocess
import sys
from typing import Optional, Tuple, List, Dict

from dav.command_plan import CommandPlan
from dav.terminal import render_error, render_warning, render_info, render_command, confirm_action


# Dangerous command patterns that should be blocked
DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\s+/',  # rm -rf on root
    r'\bdd\s+if=',  # dd command
    r'>\s*/dev/',  # Output redirection to devices
    r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};',  # Fork bomb
    r'mkfs\.',  # Filesystem creation
    r'fdisk\s+/dev/',  # Disk partitioning
    r'format\s+/',  # Format command
]


def is_dangerous_command(command: str) -> bool:
    """Check if a command contains dangerous patterns."""
    command_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command_lower):
            return True
    return False


def extract_commands(text: str) -> List[str]:
    """Extract shell commands from AI response text."""
    commands = []
    
    # Only look for code blocks with bash/shell (most reliable)
    code_block_pattern = r'```(?:bash|sh|shell|zsh)?\n(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        # Split by newlines and filter
        lines = match.split('\n')
        for line in lines:
            line = line.strip()
            # Skip empty lines, comments, and lines that are just variable assignments
            if not line or line.startswith('#'):
                continue
            
            # Skip lines that are just variable assignments (VAR=value)
            if re.match(r'^[A-Z_][A-Z0-9_]*=', line):
                continue
            
            # Only include lines that look like actual commands:
            # - Have a command name followed by space and arguments, OR
            # - Are at least 3 characters (to filter out single letters), OR
            # - Contain common command operators (|, &&, ||, ;, >, <)
            if (' ' in line or len(line) >= 3) and not re.match(r'^[a-z]+$', line):
                commands.append(line)
    
    # Also capture inline code (e.g. `command`) as a fallback
    inline_pattern = r'`([^`]+)`'
    inline_matches = re.findall(inline_pattern, text)
    for match in inline_matches:
        candidate = match.strip()
        if not candidate or candidate.startswith('#'):
            continue
        commands.append(candidate)

    # Filter out false positives: single words that are just command names
    # These are likely just mentions in text, not actual commands
    filtered_commands = []
    common_command_names = {'bash', 'sh', 'zsh', 'apt', 'yum', 'dnf', 'pacman',
                            'pip', 'python', 'python3', 'git', 'curl', 'wget',
                            'sudo', 'ls', 'cd', 'pwd', 'cat', 'grep', 'find'}

    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            continue

        # Skip if it's just a single word that's a common command name
        cmd_parts = cmd.split()
        if len(cmd_parts) == 1 and cmd_parts[0].lower() in common_command_names:
            continue

        # Skip if it's just a single short word without any operators
        if len(cmd_parts) == 1 and not any(c in cmd for c in ['|', '&', ';', '>', '<', '(', ')', '[', ']']):
            if len(cmd_parts[0]) < 3:
                continue

        filtered_commands.append(cmd)

    # Remove duplicates while preserving order
    seen = set()
    unique_commands = []
    for cmd in filtered_commands:
        if cmd not in seen:
            seen.add(cmd)
            unique_commands.append(cmd)

    return unique_commands


def execute_command(command: str, confirm: bool = True, cwd: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    Execute a command securely.
    
    Returns:
        (success, stdout, stderr)
    """
    # Check for dangerous commands
    if is_dangerous_command(command):
        render_error(f"Command blocked: potentially dangerous operation detected")
        return False, "", "Command blocked for safety"
    
    # Ask for confirmation
    if confirm:
        render_command(command)
        if not confirm_action("Execute this command?"):
            return False, "", "User cancelled"
    
    try:
        # Use shlex to safely parse the command
        # This prevents shell injection by avoiding shell=True
        parts = shlex.split(command)
        if not parts:
            return False, "", "Empty command"
        
        # Expand environment variables and user (~)
        parts = [os.path.expandvars(os.path.expanduser(part)) for part in parts]

        # Expand glob patterns (e.g., *.log) since we're not using a shell
        expanded_parts: List[str] = []
        for part in parts:
            if any(ch in part for ch in ['*', '?', '[']):
                matches = glob.glob(part)
                if matches:
                    expanded_parts.extend(matches)
                else:
                    expanded_parts.append(part)
            else:
                expanded_parts.append(part)

        parts = expanded_parts

        # Execute the command
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=cwd,
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        render_error("Command execution timed out")
        return False, "", "Command timed out"
    except Exception as e:
        render_error(f"Error executing command: {str(e)}")
        return False, "", str(e)


def _platform_matches(plan: CommandPlan, context: Optional[Dict]) -> bool:
    if plan.platform is None or not context:
        return True

    os_info = context.get("os", {}) if isinstance(context, dict) else {}
    candidates = set(p.lower() for p in plan.platform)

    system_name = str(os_info.get("system", "")).lower()
    distribution_id = str(os_info.get("distribution_id", "")).lower()
    distribution = str(os_info.get("distribution", "")).lower()

    values = {system_name, distribution_id, distribution}
    values = {v for v in values if v}

    return bool(candidates & values)


def execute_plan(plan: CommandPlan, confirm: bool = True, context: Optional[Dict] = None) -> None:
    """Execute a structured command plan."""

    render_info("Command plan received:")
    for idx, command in enumerate(plan.commands, 1):
        render_command(f"{command}")

    if plan.notes:
        render_info(f"Notes: {plan.notes}")

    if context is not None and not _platform_matches(plan, context):
        render_warning("Command plan appears to target a different platform. Aborting execution.")
        return

    if confirm:
        if not confirm_action("Execute ALL commands above?"):
            render_warning("Command execution cancelled by user")
            return

    for idx, command in enumerate(plan.commands, 1):
        if len(plan.commands) > 1:
            render_info(f"Running command {idx}/{len(plan.commands)}")

        success, stdout, stderr = execute_command(command, confirm=False, cwd=plan.cwd)

        if success:
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)
        else:
            render_error(f"Command failed: {command}")
            if stderr:
                print(stderr, file=sys.stderr)
            break


def execute_commands_from_response(
    response: str,
    confirm: bool = True,
    context: Optional[Dict] = None,
    plan: Optional[CommandPlan] = None,
) -> None:
    """Execute commands extracted from response or provided via command plan."""

    if plan is not None:
        execute_plan(plan, confirm=confirm, context=context)
        return

    commands = extract_commands(response)
    
    if not commands:
        render_warning("No executable commands found in response")
        return
    
    render_info(f"Found {len(commands)} command(s) to execute")
    
    for i, command in enumerate(commands, 1):
        if len(commands) > 1:
            render_info(f"Executing command {i}/{len(commands)}")
        
        success, stdout, stderr = execute_command(command, confirm=confirm)
        
        if success:
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)
        else:
            render_error(f"Command failed: {command}")
            if stderr:
                print(stderr, file=sys.stderr)

