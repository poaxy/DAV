"""Command execution utilities for Dav."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from dav.command_plan import CommandPlan
from dav.terminal import (
    confirm_action,
    render_command,
    render_error,
    render_info,
    render_warning,
)


# Constants
COMMAND_TIMEOUT_SECONDS = 300  # 5 minutes timeout for command execution
THREAD_JOIN_TIMEOUT_SECONDS = 2  # Timeout for thread joining (increased for reliability)


@dataclass
class ExecutionResult:
    """Result of a command execution."""
    command: str
    success: bool
    stdout: str
    stderr: str
    return_code: int

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


def execute_command(command: str, confirm: bool = True, cwd: Optional[str] = None, stream_output: bool = True) -> Tuple[bool, str, str, int]:
    """
    Execute a command securely with real-time output streaming.
    
    Args:
        command: Command to execute (may include env vars like VAR=value cmd)
        confirm: Whether to ask for confirmation
        cwd: Working directory for command execution
        stream_output: If True, stream output in real-time; if False, capture and return
    
    Returns:
        (success, stdout, stderr, return_code)
    """
    # Check for dangerous commands
    if is_dangerous_command(command):
        render_error(f"Command blocked: potentially dangerous operation detected")
        return False, "", "Command blocked for safety", 1
    
    # Ask for confirmation
    if confirm:
        render_command(command)
        if not confirm_action("Execute this command?"):
            return False, "", "User cancelled", 1
    
    try:
        # Expand environment variables and user (~) in the command string
        command = os.path.expandvars(os.path.expanduser(command))
        
        if not command.strip():
            return False, "", "Empty command", 1

        if stream_output:
            # Stream output in real-time using Popen with shell
            # Force unbuffered output by setting environment variable
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            return _execute_command_streaming(command, cwd, env)
        else:
            # Capture output (for backward compatibility)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                cwd=cwd,
            )
            return result.returncode == 0, result.stdout, result.stderr, result.returncode
    
    except subprocess.TimeoutExpired:
        render_error("Command execution timed out")
        return False, "", "Command timed out", 124  # Standard timeout exit code
    except Exception as e:
        render_error(f"Error executing command: {str(e)}")
        return False, "", str(e), 1


def _execute_command_streaming(command: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Tuple[bool, str, str, int]:
    """
    Execute a command with real-time output streaming.
    
    Args:
        command: Command string to execute
        cwd: Working directory
        env: Environment variables (merged with os.environ)
    
    Returns:
        (success, stdout, stderr, return_code)
    """
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    
    try:
        # Prepare environment with unbuffered settings
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process_env['PYTHONUNBUFFERED'] = '1'
        
        # Start process with unbuffered output using shell
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,  # Unbuffered for immediate output
            cwd=cwd,
            env=process_env,
        )
        
        # Read stdout and stderr in real-time
        def read_stdout():
            """Read stdout line by line and print immediately."""
            try:
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n\r')
                    if line:  # Only append non-empty lines
                        stdout_lines.append(line)
                        print(line)  # Print immediately
                        sys.stdout.flush()
            except Exception:
                pass  # Process may have closed stdout
        
        def read_stderr():
            """Read stderr line by line and print immediately."""
            try:
                for line in iter(process.stderr.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n\r')
                    if line:  # Only append non-empty lines
                        stderr_lines.append(line)
                        print(line, file=sys.stderr)  # Print immediately
                        sys.stderr.flush()
            except Exception:
                pass  # Process may have closed stderr
        
        # Start reader threads
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        
        stdout_thread.start()
        stderr_thread.start()
        
        # Wait for process to complete (with timeout handling)
        # Use threading to implement timeout since process.wait() doesn't support timeout
        process_finished = threading.Event()
        returncode_container = [None]
        
        def wait_for_process():
            returncode_container[0] = process.wait()
            process_finished.set()
        
        wait_thread = threading.Thread(target=wait_for_process, daemon=True)
        wait_thread.start()
        
        # Wait for process to complete (with timeout)
        if not process_finished.wait(timeout=COMMAND_TIMEOUT_SECONDS):
            process.kill()
            render_error("Command execution timed out")
            # Give threads time to read remaining output
            stdout_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            return False, '\n'.join(stdout_lines), '\n'.join(stderr_lines), 124  # Timeout exit code
        
        returncode = returncode_container[0] or 1
        
        # Close pipes to signal EOF to reader threads
        process.stdout.close()
        process.stderr.close()
        
        # Wait for threads to finish reading all output
        stdout_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS * 5)  # Longer timeout for normal completion
        stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS * 5)
        
        success = returncode == 0
        stdout = '\n'.join(stdout_lines)
        stderr = '\n'.join(stderr_lines)
        
        return success, stdout, stderr, returncode
        
    except Exception as e:
        render_error(f"Error executing command: {str(e)}")
        return False, '\n'.join(stdout_lines), '\n'.join(stderr_lines), 1


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


def _print_command_output(stdout: str, stderr: str) -> None:
    """Print command output to appropriate streams."""
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)


def execute_plan(plan: CommandPlan, confirm: bool = True, context: Optional[Dict] = None) -> List[ExecutionResult]:
    """
    Execute a structured command plan.
    
    Returns:
        List of ExecutionResult objects for each command executed.
    """
    results: List[ExecutionResult] = []
    
    render_info("Command plan received:")
    for idx, command in enumerate(plan.commands, 1):
        render_command(f"{command}")

    if plan.notes:
        render_info(f"Notes: {plan.notes}")

    if context is not None and not _platform_matches(plan, context):
        render_warning("Command plan appears to target a different platform. Aborting execution.")
        return results

    if confirm:
        if not confirm_action("Execute ALL commands above?"):
            render_warning("Command execution cancelled by user")
            return results

    for idx, command in enumerate(plan.commands, 1):
        if len(plan.commands) > 1:
            render_info(f"Running command {idx}/{len(plan.commands)}")

        success, stdout, stderr, return_code = execute_command(command, confirm=False, cwd=plan.cwd)
        
        result = ExecutionResult(
            command=command,
            success=success,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code
        )
        results.append(result)

        if success:
            _print_command_output(stdout, stderr)
        else:
            render_error(f"Command failed: {command}")
            if stderr:
                print(stderr, file=sys.stderr)
            break
    
    return results


def execute_commands_from_response(
    response: str,
    confirm: bool = True,
    context: Optional[Dict] = None,
    plan: Optional[CommandPlan] = None,
) -> List[ExecutionResult]:
    """
    Execute commands extracted from response or provided via command plan.
    
    Returns:
        List of ExecutionResult objects for each command executed.
    """
    results: List[ExecutionResult] = []

    if plan is not None:
        return execute_plan(plan, confirm=confirm, context=context)

    commands = extract_commands(response)
    
    if not commands:
        render_warning("No executable commands found in response")
        return results
    
    render_info(f"Found {len(commands)} command(s) to execute")
    
    for i, command in enumerate(commands, 1):
        if len(commands) > 1:
            render_info(f"Executing command {i}/{len(commands)}")
        
        success, stdout, stderr, return_code = execute_command(command, confirm=confirm)
        
        result = ExecutionResult(
            command=command,
            success=success,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code
        )
        results.append(result)
        
        if success:
            _print_command_output(stdout, stderr)
        else:
            render_error(f"Command failed: {command}")
            if stderr:
                print(stderr, file=sys.stderr)
    
    return results

