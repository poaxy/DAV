"""Command execution utilities for Dav."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dav.command_plan import CommandPlan
from dav.terminal import (
    confirm_action,
    render_command,
    render_error,
    render_info,
    render_warning,
)


COMMAND_TIMEOUT_SECONDS = 300
THREAD_JOIN_TIMEOUT_SECONDS = 2

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

        if stream_output:
            success, stdout, stderr, return_code = _execute_command_streaming(
                command_list, cwd, env, script_path
            )
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
        else:
            result = subprocess.run(
                command_list,
                shell=False,  # CRITICAL: Use shell=False for security
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                cwd=cwd,
                env=env,
            )
            
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
                    success=result.returncode == 0,
                    return_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr
                )
            
            return result.returncode == 0, result.stdout, result.stderr, result.returncode
    
    except subprocess.TimeoutExpired:
        error_msg = "Command execution timed out"
        render_error(error_msg)
        if automation_logger:
            automation_logger.log_error(f"{error_msg}: {original_command if 'original_command' in locals() else command}")
        return False, "", "Command timed out", 124
    except Exception as e:
        error_msg = f"Error executing command: {str(e)}"
        render_error(error_msg)
        if automation_logger:
            automation_logger.log_error(f"{error_msg}: {command}")
        return False, "", str(e), 1


def _execute_command_streaming(
    command_list: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    script_path: Optional[Path] = None
) -> Tuple[bool, str, str, int]:
    """
    Execute a command with real-time output streaming.
    
    Args:
        command_list: List of command arguments (for shell=False)
        cwd: Working directory
        env: Environment variables (merged with os.environ)
        script_path: Path to temporary script if created (for cleanup)
    
    Returns:
        (success, stdout, stderr, return_code)
    """
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    
    try:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process_env['PYTHONUNBUFFERED'] = '1'
        
        process = subprocess.Popen(
            command_list,
            shell=False,  # CRITICAL: Use shell=False for security
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            cwd=cwd,
            env=process_env,
        )
        
        def read_stdout():
            try:
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n\r')
                    if line:
                        stdout_lines.append(line)
                        print(line)
                        sys.stdout.flush()
            except Exception:
                pass
        
        def read_stderr():
            try:
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
        
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        process_finished = threading.Event()
        returncode_container = [None]
        
        def wait_for_process():
            returncode_container[0] = process.wait()
            process_finished.set()
        
        wait_thread = threading.Thread(target=wait_for_process, daemon=True)
        wait_thread.start()
        
        if not process_finished.wait(timeout=COMMAND_TIMEOUT_SECONDS):
            process.kill()
            render_error("Command execution timed out")
            stdout_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            return False, '\n'.join(stdout_lines), '\n'.join(stderr_lines), 124
        
        wait_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
        
        returncode = returncode_container[0]
        if returncode is None:
            try:
                returncode = process.poll()
                if returncode is None:
                    time.sleep(0.1)
                    returncode = process.poll()
                    if returncode is None:
                        returncode = 1
            except Exception:
                returncode = 1
        
        process.stdout.close()
        process.stderr.close()
        stdout_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS * 5)
        stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS * 5)
        
        # Clean up temporary script if created
        if script_path and script_path.exists():
            try:
                script_path.unlink()
            except Exception:
                pass
        
        success = returncode == 0
        stdout = '\n'.join(stdout_lines)
        stderr = '\n'.join(stderr_lines)
        
        return success, stdout, stderr, returncode
        
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
    
    # Check command execution rate limit
    from dav.rate_limiter import check_command_rate_limit
    is_allowed, rate_limit_error = check_command_rate_limit()
    if not is_allowed:
        render_warning(rate_limit_error or "Command execution rate limit exceeded")
        if automation_logger:
            automation_logger.log_warning("Command execution rate limit exceeded")
        return results
    
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

