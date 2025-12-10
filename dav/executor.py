"""Command execution utilities for Dav."""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plumbum import local
from plumbum.commands import ProcessExecutionError, ProcessTimedOut

from dav.command_plan import CommandPlan
from dav.terminal import (
    confirm_action,
    render_command,
    render_error,
    render_info,
    render_warning,
)


COMMAND_TIMEOUT_SECONDS = 300

# Global sudo handler cache (created once per process)
_sudo_handler_cache: Optional[Any] = None


@dataclass
class ExecutionResult:
    """Result of a command execution."""
    command: str
    success: bool
    stdout: str
    stderr: str
    return_code: int

DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\s+/',  # rm -rf / (dangerous - always block)
    r'\brm\s+-rf\s+/etc',  # rm -rf /etc (always block)
    r'\brm\s+-rf\s+/usr',  # rm -rf /usr (always block)
    r'\brm\s+-rf\s+/var',  # rm -rf /var (always block)
    r'\brm\s+-rf\s+/boot',  # rm -rf /boot (always block)
    r'\brm\s+-rf\s+/sys',  # rm -rf /sys (always block)
    r'\brm\s+-rf\s+/proc',  # rm -rf /proc (always block)
    r'\bdd\s+if=/dev/zero',  # dd if=/dev/zero (disk wipe - always block)
    r'\bmkfs\s+.*\s+/dev/',  # mkfs on device (format disk - always block)
    r'\bwipefs\s+.*\s+/dev/',  # wipefs on device (always block)
    r'\bpasswd\s+root',  # Change root password (always block)
    r'\bdd\s+if=',  # dd if= (can overwrite disk - always block)
    r'(?<!&)>\s*/dev/(?!null|zero)',  # > /dev/ (but allow &> /dev/null and > /dev/null/zero)
    r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};',  # Fork bomb
    r'\bmkfs\.',  # mkfs. (format filesystem - always block)
    r'\bfdisk\s+/dev/',  # fdisk /dev/ (partition manipulation - always block)
    r'\bformat\s+/',  # format / (format disk - always block)
]

# Patterns that are dangerous in automation mode but may be acceptable if explicitly requested
AUTOMATION_DANGEROUS_PATTERNS = [
    r'\breboot\b',  # reboot (dangerous in automation unless explicitly requested)
    r'\bshutdown\b',  # shutdown (dangerous in automation unless explicitly requested)
    r'\bpoweroff\b',  # poweroff (dangerous in automation unless explicitly requested)
    r'\bhalt\b',  # halt (dangerous in automation unless explicitly requested)
    r'\binit\s+[06]',  # init 0 or init 6 (shutdown/reboot)
    r'\bsystemctl\s+(reboot|poweroff|halt)',  # systemctl reboot/poweroff/halt
]


def is_dangerous_command(command: str, automation_mode: bool = False) -> bool:
    """
    Check if a command contains dangerous patterns.
    
    Args:
        command: Command to check
        automation_mode: If True, also check automation-specific dangerous patterns
    
    Returns:
        True if command is dangerous, False otherwise
    """
    command_lower = command.lower().strip()
    
    # Skip dangerous check for conditional statements (if, while, for, etc.)
    # These are valid bash constructs, not dangerous operations
    if re.match(r'^\s*(if|while|for|case|until)\s+', command_lower):
        return False
    
    # Always check standard dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command_lower):
            return True
    
    # In automation mode, also check automation-specific dangerous patterns
    if automation_mode:
        for pattern in AUTOMATION_DANGEROUS_PATTERNS:
            if re.search(pattern, command_lower):
                return True
    
    return False


COMMAND_EXECUTION_MARKER = ">>>EXEC<<<"

def extract_commands(text: str) -> List[str]:
    """Extract shell commands from AI response text.
    
    Only extracts commands if the special marker COMMAND_EXECUTION_MARKER is present in the text.
    Only extracts commands that appear AFTER the marker position.
    This prevents false positives when the AI is just explaining things without wanting to execute commands.
    
    Handles multi-line bash constructs (if/then/fi, while/do/done, etc.) as single commands.
    """
    marker_pos = text.find(COMMAND_EXECUTION_MARKER)
    if marker_pos == -1:
        return []
    
    text_after_marker = text[marker_pos + len(COMMAND_EXECUTION_MARKER):]
    commands = []
    
    code_block_pattern = r'```(?:bash|sh|shell|zsh)?\n(.*?)```'
    matches = re.findall(code_block_pattern, text_after_marker, re.DOTALL | re.IGNORECASE)
    for match in matches:
        code_block = match.strip()
        if not code_block:
            continue
        
        # Check if this is a multi-line bash construct (if/then/fi, while/do/done, etc.)
        # These should be kept as a single command
        bash_constructs = [
            (r'\bif\s+.*\bthen\b', r'\bfi\b'),  # if...then...fi
            (r'\bwhile\s+.*\bdo\b', r'\bdone\b'),  # while...do...done
            (r'\bfor\s+.*\bdo\b', r'\bdone\b'),  # for...do...done
            (r'\bcase\s+.*\bin\b', r'\besac\b'),  # case...in...esac
            (r'\buntil\s+.*\bdo\b', r'\bdone\b'),  # until...do...done
            (r'\bfunction\s+', r'\b}\s*$'),  # function...{...}
        ]
        
        is_multiline_construct = False
        for start_pattern, end_pattern in bash_constructs:
            if re.search(start_pattern, code_block, re.IGNORECASE):
                # Found start of construct, check if it has matching end
                if re.search(end_pattern, code_block, re.IGNORECASE):
                    is_multiline_construct = True
                    break
        
        if is_multiline_construct:
            # Keep the entire code block as a single command
            # Remove leading/trailing whitespace but preserve structure
            command = code_block.strip()
            if command:
                commands.append(command)
        else:
            # Split by lines for simple commands
            lines = code_block.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if re.match(r'^[A-Z_][A-Z0-9_]*=', line):
                    continue
                if (' ' in line or len(line) >= 3) and not re.match(r'^[a-z]+$', line):
                    commands.append(line)
    
    inline_pattern = r'`([^`]+)`'
    inline_matches = re.findall(inline_pattern, text_after_marker)
    for match in inline_matches:
        candidate = match.strip()
        if not candidate or candidate.startswith('#'):
            continue
        commands.append(candidate)

    filtered_commands = []
    common_command_names = {'bash', 'sh', 'zsh', 'apt', 'yum', 'dnf', 'pacman',
                            'pip', 'python', 'python3', 'git', 'curl', 'wget',
                            'sudo', 'ls', 'cd', 'pwd', 'cat', 'grep', 'find'}
    commands_requiring_args = {'less', 'more', 'cat', 'head', 'tail', 'grep', 'find',
                               'sed', 'awk', 'cut', 'sort', 'uniq', 'wc',
                               'chmod', 'chown', 'mv', 'cp', 'rm', 'mkdir', 'rmdir'}

    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            continue

        if re.match(r'^[/~]', cmd) and not any(cmd.startswith(f'{c} ') for c in ['cat', 'less', 'more', 'head', 'tail', 'grep', 'find', 'ls', 'cd']):
            if not re.match(r'^(cat|less|more|head|tail|grep|find|ls|cd|sudo\s+(cat|less|more|head|tail|grep|find|ls|cd))\s+', cmd):
                continue

        cmd_parts = cmd.split()
        if len(cmd_parts) == 1:
            if cmd_parts[0].lower() in common_command_names:
                continue
            if cmd_parts[0].lower() in commands_requiring_args:
                continue
            if not any(c in cmd for c in ['|', '&', ';', '>', '<', '(', ')', '[', ']']):
                if len(cmd_parts[0]) < 3:
                    continue

        if len(cmd_parts) >= 2:
            if cmd_parts[0].lower() == 'sudo' and len(cmd_parts) == 2:
                if cmd_parts[1].lower() in commands_requiring_args:
                    continue
        elif len(cmd_parts) == 1:
            if cmd_parts[0].lower() in commands_requiring_args:
                continue

        filtered_commands.append(cmd)

    seen = set()
    unique_commands = []
    for cmd in filtered_commands:
        if cmd not in seen:
            seen.add(cmd)
            unique_commands.append(cmd)

    return unique_commands


def execute_command(command: str, confirm: bool = True, cwd: Optional[str] = None, stream_output: bool = True, automation_mode: bool = False, automation_logger: Optional[Any] = None) -> Tuple[bool, str, str, int]:
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
    # Check for dangerous commands (but allow all other commands for AI flexibility)
    if is_dangerous_command(command, automation_mode=automation_mode):
        error_msg = "Command blocked: potentially dangerous operation detected"
        if automation_mode:
            error_msg += " (reboot/shutdown commands require explicit user request in automation mode)"
        render_error(error_msg)
        if automation_logger:
            automation_logger.log_error(error_msg)
        return False, "", "Command blocked for safety", 1
    
    # In automation mode, skip confirmations and use non-streaming output for logging
    if automation_mode:
        confirm = False
        stream_output = False
        
        # Check if command needs sudo and handle it
        # Use regex to match "sudo" as a word (not part of another word like "pseudo")
        needs_sudo = bool(re.search(r'\bsudo\b', command))
        if needs_sudo:
            from dav.config import get_automation_sudo_method
            from dav.sudo_handler import SudoHandler
            
            sudo_method = get_automation_sudo_method()
            if sudo_method == "sudoers":
                # Use cached sudo handler (create once, reuse)
                global _sudo_handler_cache
                if _sudo_handler_cache is None:
                    _sudo_handler_cache = SudoHandler()
                sudo_handler = _sudo_handler_cache
                
                if not sudo_handler.can_run_sudo():
                    error_msg = "Password-less sudo not available. Configure sudoers NOPASSWD or use --install-for-root"
                    render_error(error_msg)
                    if automation_logger:
                        automation_logger.log_error(error_msg)
                    return False, "", error_msg, 1
                # Command already has sudo prefix, so we execute it as-is
                # The sudo check above ensures password-less sudo is available
    
    if confirm:
        render_command(command)
        if not confirm_action("Execute this command?"):
            return False, "", "User cancelled", 1
    
    try:
        # Parse and validate command for safe execution
        from dav.command_validator import prepare_command_for_execution, CommandParseError
        
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            command_list, use_shell, script_path = prepare_command_for_execution(
                command,
                cwd=cwd,
                env=env
            )
            
            # use_shell should always be False for security
            if use_shell:
                return False, "", "Command requires shell features that are not safely supported", 1
            
        except CommandParseError as e:
            error_msg = f"Command parsing failed: {str(e)}"
            render_error(error_msg)
            if automation_logger:
                automation_logger.log_error(error_msg)
            return False, "", error_msg, 1
        
        # Store original command for logging
        original_command = command

        # Build plumbum command from command_list
        if not command_list:
            return False, "", "Empty command list", 1
        
        # Create plumbum command object
        # Plumbum supports building commands dynamically
        # Start with the command name
        cmd = local[command_list[0]]
        # Add arguments one by one (plumbum supports chaining)
        for arg in command_list[1:]:
            cmd = cmd[arg]
        
        # Apply environment variables and working directory
        if env:
            # Merge with current environment
            merged_env = os.environ.copy()
            merged_env.update(env)
            cmd = cmd.with_env(**merged_env)
        else:
            cmd = cmd.with_env(**os.environ)
        
        if cwd:
            cmd = cmd.with_cwd(cwd)

        if stream_output:
            success, stdout, stderr, return_code = _execute_command_streaming(
                cmd, original_command, script_path, automation_logger
            )
            return success, stdout, stderr, return_code
        else:
            # Non-streaming execution
            try:
                # Use plumbum's run with retcode=None to get (retcode, stdout, stderr) tuple
                # This doesn't raise on non-zero exit codes
                result = cmd.run(
                    retcode=None,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                )
                
                # Clean up temporary script if created
                if script_path and script_path.exists():
                    try:
                        script_path.unlink()
                    except Exception:
                        pass
                
                # Plumbum's run(retcode=None) returns (retcode, stdout, stderr) tuple
                # Handle different possible return formats
                if isinstance(result, tuple):
                    if len(result) >= 3:
                        return_code, stdout, stderr = result[0], result[1], result[2]
                    elif len(result) == 2:
                        # Some versions return (retcode, stdout)
                        return_code, stdout = result[0], result[1]
                        stderr = ""
                    else:
                        return_code = result[0] if len(result) > 0 else 0
                        stdout = result[1] if len(result) > 1 else ""
                        stderr = result[2] if len(result) > 2 else ""
                else:
                    # Fallback - treat as success with stdout
                    return_code = 0
                    stdout = str(result) if result else ""
                    stderr = ""
                
                success = return_code == 0
                
                # Record command execution for summary report
                if automation_logger:
                    automation_logger.record_command_execution(
                        command=original_command,
                        success=success,
                        return_code=return_code,
                        stdout=stdout,
                        stderr=stderr
                    )
                
                return success, stdout, stderr, return_code
            
            except ProcessTimedOut:
                error_msg = "Command execution timed out"
                render_error(error_msg)
                if automation_logger:
                    automation_logger.log_error(f"{error_msg}: {original_command}")
                # Clean up script
                if script_path and script_path.exists():
                    try:
                        script_path.unlink()
                    except Exception:
                        pass
                return False, "", "Command timed out", 124
            
            except ProcessExecutionError as e:
                # Command failed with non-zero exit code
                stdout = e.stdout if hasattr(e, 'stdout') else ""
                stderr = e.stderr if hasattr(e, 'stderr') else str(e)
                return_code = e.retcode if hasattr(e, 'retcode') else 1
                
                # Clean up temporary script if created
                if script_path and script_path.exists():
                    try:
                        script_path.unlink()
                    except Exception:
                        pass
                
                # Record command execution for summary report
                if automation_logger:
                    automation_logger.record_command_execution(
                        command=original_command,
                        success=False,
                        return_code=return_code,
                        stdout=stdout,
                        stderr=stderr
                    )
                
                return False, stdout, stderr, return_code
    
    except Exception as e:
        error_msg = f"Error executing command: {str(e)}"
        render_error(error_msg)
        if automation_logger:
            automation_logger.log_error(f"{error_msg}: {command}")
        # Clean up script on error
        if 'script_path' in locals() and script_path and script_path.exists():
            try:
                script_path.unlink()
            except Exception:
                pass
        return False, "", str(e), 1


def _execute_command_streaming(
    cmd: Any,
    original_command: str,
    script_path: Optional[Path] = None,
    automation_logger: Optional[Any] = None
) -> Tuple[bool, str, str, int]:
    """
    Execute a command with real-time output streaming using plumbum.
    
    Args:
        cmd: Plumbum command object (already configured with env, cwd, etc.)
        original_command: Original command string for logging
        script_path: Path to temporary script if created (for cleanup)
        automation_logger: Optional automation logger
    
    Returns:
        (success, stdout, stderr, return_code)
    """
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    
    try:
        # Use plumbum's popen for streaming
        # Plumbum's popen() returns a process object similar to subprocess.Popen
        process = cmd.popen()
        
        # Stream stdout in real-time
        # Plumbum's iter_lines() gives stdout lines
        
        def read_stdout():
            try:
                for line in process.iter_lines():
                    line = line.rstrip('\n\r')
                    if line:
                        stdout_lines.append(line)
                        print(line)
                        sys.stdout.flush()
            except Exception:
                pass
        
        def read_stderr():
            try:
                # Read stderr from process.stderr if available
                if hasattr(process, 'stderr') and process.stderr:
                    for line in iter(process.stderr.readline, ''):
                        if not line:
                            break
                        line = line.rstrip('\n\r')
                        if line:
                            stderr_lines.append(line)
                            print(line, file=sys.stderr)
                            sys.stderr.flush()
            except Exception:
                pass
        
        # Start reading threads
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        # Wait for process to complete with timeout
        # Plumbum's process object from popen() should have wait() method
        # Handle timeout by polling with timeout check
        start_time = time.time()
        
        try:
            # Poll process until it completes or times out
            while True:
                return_code = process.poll()
                if return_code is not None:
                    break
                
                # Check for timeout
                if time.time() - start_time > COMMAND_TIMEOUT_SECONDS:
                    process.kill()
                    raise ProcessTimedOut("Command execution timed out")
                
                time.sleep(0.1)
            
        except ProcessTimedOut:
            render_error("Command execution timed out")
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            # Clean up script
            if script_path and script_path.exists():
                try:
                    script_path.unlink()
                except Exception:
                    pass
            return False, '\n'.join(stdout_lines), '\n'.join(stderr_lines), 124
        
        # Wait for threads to finish reading
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        
        # Clean up temporary script if created
        if script_path and script_path.exists():
            try:
                script_path.unlink()
            except Exception:
                pass
        
        success = return_code == 0
        stdout = '\n'.join(stdout_lines)
        stderr = '\n'.join(stderr_lines)
        
        # Record streaming command execution for summary
        if automation_logger:
            automation_logger.record_command_execution(
                command=original_command,
                success=success,
                return_code=return_code,
                stdout=stdout,
                stderr=stderr
            )
        
        return success, stdout, stderr, return_code
        
    except ProcessExecutionError as e:
        # Command failed
        stdout = e.stdout if hasattr(e, 'stdout') else '\n'.join(stdout_lines)
        stderr = e.stderr if hasattr(e, 'stderr') else str(e)
        return_code = e.retcode if hasattr(e, 'retcode') else 1
        
        # Clean up temporary script on error
        if script_path and script_path.exists():
            try:
                script_path.unlink()
            except Exception:
                pass
        
        # Record error
        if automation_logger:
            automation_logger.record_command_execution(
                command=original_command,
                success=False,
                return_code=return_code,
                stdout=stdout,
                stderr=stderr
            )
        
        return False, stdout, stderr, return_code
        
    except Exception as e:
        # Clean up temporary script on error
        if script_path and script_path.exists():
            try:
                script_path.unlink()
            except Exception:
                pass
        render_error(f"Error executing command: {str(e)}")
        return False, '\n'.join(stdout_lines), '\n'.join(stderr_lines), 1


def _platform_matches(plan: CommandPlan, context: Optional[Dict]) -> bool:
    """
    Check if command plan platform matches the current system.
    
    Returns:
        True if platforms match or if platform is None (platform-agnostic commands)
        False if platforms explicitly don't match
    """
    if plan.platform is None or not context:
        return True

    os_info = context.get("os", {}) if isinstance(context, dict) else {}
    candidates = set(p.lower().strip() for p in plan.platform)

    system_name = str(os_info.get("system", "")).lower()
    distribution_id = str(os_info.get("distribution_id", "")).lower()
    distribution = str(os_info.get("distribution", "")).lower()

    # Build set of current system identifiers
    values = {system_name, distribution_id, distribution}
    values = {v for v in values if v}
    
    # Add platform aliases for better matching
    # macOS/Darwin aliases
    if system_name == "darwin":
        values.add("darwin")
        values.add("macos")
        values.add("mac")
        values.add("osx")
    
    # Linux distribution aliases
    if system_name == "linux":
        values.add("linux")
        values.add("unix")
        # Add common distribution aliases
        if distribution_id:
            values.add(distribution_id)
        if distribution:
            values.add(distribution)
    
    # Windows aliases
    if system_name == "windows":
        values.add("windows")
        values.add("win")
        values.add("win32")
    
    # Check for generic platform identifiers that match any Unix-like system
    generic_unix = {"unix", "posix", "linux", "darwin", "macos", "mac", "osx", "bsd"}
    if candidates & generic_unix and system_name in {"linux", "darwin", "freebsd", "openbsd", "netbsd"}:
        # If plan specifies generic Unix and we're on a Unix-like system, it matches
        return True
    
    # Check for exact matches
    return bool(candidates & values)


def _print_command_output(stdout: str, stderr: str) -> None:
    """Print command output to appropriate streams."""
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)


def execute_plan(plan: CommandPlan, confirm: bool = True, context: Optional[Dict] = None, automation_mode: bool = False, automation_logger: Optional[Any] = None) -> List[ExecutionResult]:
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

    # Check platform compatibility (warn but don't abort)
    if context is not None and plan.platform is not None and not _platform_matches(plan, context):
        os_info = context.get("os", {}) if isinstance(context, dict) else {}
        current_system = os_info.get("system", "unknown")
        plan_platforms = ", ".join(plan.platform)
        render_warning(
            f"Command plan targets platform(s): {plan_platforms}, but current system is: {current_system}. "
            f"Proceeding with execution, but commands may not work as expected."
        )

    if confirm:
        if not confirm_action("Execute ALL commands above?"):
            render_warning("Command execution cancelled by user")
            return results

    for idx, command in enumerate(plan.commands, 1):
        if len(plan.commands) > 1:
            render_info(f"Running command {idx}/{len(plan.commands)}")

        success, stdout, stderr, return_code = execute_command(
            command, 
            confirm=False, 
            cwd=plan.cwd,
            stream_output=not automation_mode,
            automation_mode=automation_mode,
            automation_logger=automation_logger,
        )
        
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
    automation_mode: bool = False,
    automation_logger: Optional[Any] = None,
) -> List[ExecutionResult]:
    """
    Execute commands extracted from response or provided via command plan.
    
    Returns:
        List of ExecutionResult objects for each command executed.
    """
    results: List[ExecutionResult] = []
    
    # Validate AI response before extracting commands
    from dav.input_validator import validate_ai_response
    is_valid, validation_error = validate_ai_response(response)
    if not is_valid:
        render_warning(f"AI response validation warning: {validation_error}")
        # Continue but log the warning
        if automation_logger:
            automation_logger.log_warning(f"Response validation warning: {validation_error}")
    
    if plan is not None:
        return execute_plan(plan, confirm=confirm, context=context, automation_mode=automation_mode, automation_logger=automation_logger)
    
    commands = extract_commands(response)
    
    if not commands:
        if COMMAND_EXECUTION_MARKER not in response:
            pass
        else:
            render_warning("Command execution marker found but no valid commands could be extracted")
        return results
    
    render_info(f"Found {len(commands)} command(s) to execute")
    
    for i, command in enumerate(commands, 1):
        if len(commands) > 1:
            render_info(f"Executing command {i}/{len(commands)}")
        
        success, stdout, stderr, return_code = execute_command(
            command, 
            confirm=confirm,
            stream_output=not automation_mode,  # Don't stream in automation mode
            automation_mode=automation_mode,
            automation_logger=automation_logger,
        )
        
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

