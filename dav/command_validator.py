"""Command parsing and validation for secure execution."""

import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict


class CommandParseError(Exception):
    """Raised when command cannot be parsed safely."""
    pass


def parse_command(command: str) -> Tuple[List[str], bool]:
    """
    Parse command string into list of arguments for subprocess.
    
    Args:
        command: Command string to parse
        
    Returns:
        Tuple of (command_list, needs_shell) where needs_shell is True if shell features are needed
    """
    if not command or not command.strip():
        raise CommandParseError("Empty command")
    
    command = command.strip()
    
    # Check for shell features that require shell=True
    has_pipes = '|' in command
    has_redirects = '>' in command or '<' in command or '>>' in command
    has_background = command.rstrip().endswith('&')
    has_subshell = '(' in command and ')' in command
    has_variables = '$' in command and re.search(r'\$\w+', command)
    has_conditionals = '&&' in command or '||' in command or ';' in command
    
    needs_shell = has_pipes or has_redirects or has_background or has_subshell or has_conditionals
    
    if needs_shell:
        # For complex commands, we'll create a temporary script
        return [], True
    
    # For simple commands, parse with shlex
    try:
        # Use posix=True for proper shell-like parsing
        parts = shlex.split(command, posix=True)
        if not parts:
            raise CommandParseError("No command found after parsing")
        return parts, False
    except ValueError as e:
        raise CommandParseError(f"Failed to parse command: {e}")


def create_safe_script(commands: List[str], cwd: Optional[str] = None) -> Tuple[Path, bool]:
    """
    Create a temporary script file for complex shell commands.
    
    Args:
        commands: List of command strings to execute
        cwd: Working directory
        
    Returns:
        Tuple of (script_path, success)
    """
    try:
        # Create temporary script file
        script_fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='dav_script_')
        script_file = Path(script_path)
        
        # Write script with shebang
        with os.fdopen(script_fd, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write('set -euo pipefail\n')  # Exit on error, undefined vars, pipe failures
            f.write('\n')
            
            for cmd in commands:
                f.write(f'{cmd}\n')
        
        # Set execute permissions
        os.chmod(script_path, 0o700)  # Owner read/write/execute only
        
        return script_file, True
    except Exception as e:
        return Path(), False


def validate_command_for_execution(command: str) -> Tuple[bool, Optional[str], List[str], bool]:
    """
    Validate and parse command for safe execution.
    
    Args:
        command: Command string to validate
        
    Returns:
        Tuple of (is_valid, error_message, command_list, needs_shell)
    """
    # Parse command
    try:
        command_list, needs_shell = parse_command(command)
    except CommandParseError as e:
        return False, str(e), [], False
    
    # If needs shell, we'll handle it differently
    if needs_shell:
        # For complex commands, create a script
        # Return empty list to indicate we need to create a script
        return True, None, [], True
    
    # For simple commands, return the parsed command list
    # No allowlist restriction - AI can execute any command (dangerous commands are still blocked separately)
    return True, None, command_list, False


def expand_command_variables(command: str, env: Optional[Dict[str, str]] = None) -> str:
    """
    Safely expand environment variables in command string.
    
    Args:
        command: Command string with variables
        env: Environment variables to use (defaults to os.environ)
        
    Returns:
        Command with variables expanded
    """
    if env is None:
        env = os.environ.copy()
    
    # Only expand variables that are in the environment
    def expand_var(match):
        var_name = match.group(1)
        if var_name in env:
            return env[var_name]
        return match.group(0)  # Keep original if not found
    
    # Expand $VAR and ${VAR} patterns
    command = re.sub(r'\$(\w+)', expand_var, command)
    command = re.sub(r'\$\{(\w+)\}', expand_var, command)
    
    return command


def prepare_command_for_execution(
    command: str,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> Tuple[List[str], bool, Optional[Path]]:
    """
    Prepare command for safe execution with shell=False.
    
    Args:
        command: Command string
        cwd: Working directory
        env: Environment variables
        
    Returns:
        Tuple of (command_list, use_shell, script_path)
        - command_list: List of arguments for subprocess
        - use_shell: Whether shell is needed (should be False for security)
        - script_path: Path to temporary script if created
    """
    # Expand variables first
    if env:
        command = expand_command_variables(command, env)
    else:
        command = expand_command_variables(command)
    
    # Validate and parse
    is_valid, error_msg, command_list, needs_shell = validate_command_for_execution(command)
    
    if not is_valid:
        raise CommandParseError(error_msg or "Command validation failed")
    
    # If needs shell features, create a script
    if needs_shell:
        script_path, success = create_safe_script([command], cwd)
        if success:
            # Return command to execute the script
            return [str(script_path)], False, script_path
        else:
            raise CommandParseError("Failed to create safe script for complex command")
    
    # For simple commands, return the parsed list
    return command_list, False, None

