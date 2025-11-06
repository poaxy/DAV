"""Secure command execution for Dav."""

import re
import subprocess
import shlex
from typing import Optional, Tuple, List
from dav.terminal import render_error, render_warning, render_command, confirm_action


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
    
    # Look for code blocks with bash/shell
    code_block_pattern = r'```(?:bash|sh|shell)?\n(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        # Split by newlines and filter empty
        lines = [line.strip() for line in match.split('\n') if line.strip() and not line.strip().startswith('#')]
        commands.extend(lines)
    
    # Also look for inline code with $ prefix
    inline_pattern = r'\$?\s*`([^`]+)`'
    inline_matches = re.findall(inline_pattern, text)
    for match in inline_matches:
        if match.strip() and not match.strip().startswith('#'):
            commands.append(match.strip())
    
    # Remove duplicates while preserving order
    seen = set()
    unique_commands = []
    for cmd in commands:
        if cmd not in seen:
            seen.add(cmd)
            unique_commands.append(cmd)
    
    return unique_commands


def execute_command(command: str, confirm: bool = True) -> Tuple[bool, str, str]:
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
        
        # Execute the command
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        render_error("Command execution timed out")
        return False, "", "Command timed out"
    except Exception as e:
        render_error(f"Error executing command: {str(e)}")
        return False, "", str(e)


def execute_commands_from_response(response: str, confirm: bool = True) -> None:
    """Extract and execute commands from AI response."""
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
                print(stderr, file=__import__('sys').stderr)
        else:
            render_error(f"Command failed: {command}")
            if stderr:
                print(stderr, file=__import__('sys').stderr)

