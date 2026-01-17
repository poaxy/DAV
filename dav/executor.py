"""Command execution utilities for Dav."""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import traceback
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

_sudo_handler_cache: Optional[Any] = None


def _cleanup_script(script_path: Optional[Path]) -> None:
    """Clean up temporary script file if it exists."""
    if script_path and script_path.exists():
        try:
            script_path.unlink()
        except Exception:
            pass


def _ensure_string(value: Any) -> str:
    """
    Convert value to string, handling bytes and other types.
    
    Args:
        value: Value to convert (bytes, str, or other)
    
    Returns:
        String representation of the value
    """
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    elif isinstance(value, str):
        return value
    else:
        return str(value) if value else ""


def _get_process_return_code(process: Any) -> Optional[int]:
    """
    Get return code from plumbum process object with fallbacks.
    
    Args:
        process: Plumbum process object
    
    Returns:
        Return code or None if process is still running
    """
    try:
        return process.poll()
    except AttributeError:
        if hasattr(process, 'returncode'):
            return process.returncode
        elif hasattr(process, 'wait'):
            try:
                return process.wait()
            except Exception:
                return None
    return None


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
    r'\bfdisk\s+/dev/',
    r'\bformat\s+/',
]

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
    
    if re.match(r'^\s*(if|while|for|case|until)\s+', command_lower):
        return False
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command_lower):
            return True
    
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
    
    commands = []
    
    # First, check if marker is inside a code block
    # Find all code blocks and check if any contain the marker
    code_block_pattern = r'```(?:bash|sh|shell|zsh)?\s*\n?(.*?)```'
    all_code_blocks = re.finditer(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
    
    matches = []
    for match_obj in all_code_blocks:
        code_block_content = match_obj.group(1)
        block_start = match_obj.start()
        block_end = match_obj.end()
        
        # Check if marker is inside this code block
        if block_start <= marker_pos < block_end:
            # Marker is inside this code block, extract content after marker
            marker_in_block = marker_pos - block_start
            content_after_marker = code_block_content[marker_in_block + len(COMMAND_EXECUTION_MARKER):]
            matches.append(content_after_marker.strip())
            break
    
    # If marker is not inside a code block, look for code blocks after the marker
    text_after_marker = text[marker_pos + len(COMMAND_EXECUTION_MARKER):]
    if not matches:
        matches = re.findall(code_block_pattern, text_after_marker, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        code_block = match.strip()
        if not code_block:
            continue
        
        bash_constructs = [
            (r'\bif\s+.*\bthen\b', r'\bfi\b'),
            (r'\bwhile\s+.*\bdo\b', r'\bdone\b'),
            (r'\bfor\s+.*\bdo\b', r'\bdone\b'),
            (r'\bcase\s+.*\bin\b', r'\besac\b'),
            (r'\buntil\s+.*\bdo\b', r'\bdone\b'),
            (r'\bfunction\s+', r'\b}\s*$'),
        ]
        
        is_multiline_construct = False
        for start_pattern, end_pattern in bash_constructs:
            if re.search(start_pattern, code_block, re.IGNORECASE):
                if re.search(end_pattern, code_block, re.IGNORECASE):
                    is_multiline_construct = True
                    break
        
        if is_multiline_construct:
            command = code_block.strip()
            if command:
                commands.append(command)
        else:
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


def execute_command(command: str, confirm: bool = True, cwd: Optional[str] = None, stream_output: bool = True, automation_mode: bool = False, automation_logger: Optional[Any] = None, direct_passthrough: bool = False) -> Tuple[bool, str, str, int]:
    """
    Execute a command securely with real-time output streaming.
    
    Args:
        command: Command to execute (may include env vars like VAR=value cmd)
        confirm: Whether to ask for confirmation
        cwd: Working directory for command execution
        stream_output: If True, stream output in real-time; if False, capture and return
        direct_passthrough: If True, pass stdout/stderr directly to terminal (preserves formatting/colors)
    
        Returns:
        (success, stdout, stderr, return_code)
    """
    if is_dangerous_command(command, automation_mode=automation_mode):
        error_msg = "Command blocked: potentially dangerous operation detected"
        if automation_mode:
            error_msg += " (reboot/shutdown commands require explicit user request in automation mode)"
        render_error(error_msg)
        if automation_logger:
            automation_logger.log_error(error_msg)
            return False, "", "Command blocked for safety", 1
    
    if automation_mode:
        confirm = False
        stream_output = False
        
        needs_sudo = bool(re.search(r'\bsudo\b', command))
        if needs_sudo:
            from dav.config import get_automation_sudo_method
            from dav.sudo_handler import SudoHandler
            
            sudo_method = get_automation_sudo_method()
            if sudo_method == "sudoers":
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
    
    if confirm:
        render_command(command)
        if not confirm_action("Execute this command?"):
            return False, "", "User cancelled", 1
    
    try:
        from dav.command_validator import prepare_command_for_execution, CommandParseError
        
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            command_list, use_shell, script_path = prepare_command_for_execution(
                command,
                cwd=cwd,
                env=env
            )
            
            if use_shell:
                return False, "", "Command requires shell features that are not safely supported", 1
            
        except CommandParseError as e:
            error_msg = f"Command parsing failed: {str(e)}"
            render_error(error_msg)
            if automation_logger:
                automation_logger.log_error(error_msg)
            return False, "", error_msg, 1
        
        original_command = command

        if not command_list:
            return False, "", "Empty command list", 1
        
        cmd = local[command_list[0]]
        for arg in command_list[1:]:
            cmd = cmd[arg]
        
        cmd = cmd.with_env(**env)
        
        if cwd:
            cmd = cmd.with_cwd(cwd)

        if stream_output:
            success, stdout, stderr, return_code = _execute_command_streaming(
                cmd, original_command, script_path, automation_logger
            )
            return success, stdout, stderr, return_code
        else:
            try:
                result = cmd.run(
                    retcode=None,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                )
                
                _cleanup_script(script_path)
                
                if isinstance(result, tuple):
                    if len(result) >= 3:
                        return_code, stdout, stderr = result[0], result[1], result[2]
                    elif len(result) == 2:
                        return_code, stdout = result[0], result[1]
                        stderr = ""
                    else:
                        return_code = result[0] if len(result) > 0 else 0
                        stdout = result[1] if len(result) > 1 else ""
                        stderr = result[2] if len(result) > 2 else ""
                    
                    stdout = _ensure_string(stdout)
                    stderr = _ensure_string(stderr)
                else:
                    return_code = 0
                    stdout = _ensure_string(result)
                    stderr = ""
                
                success = return_code == 0
                
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
                _cleanup_script(script_path)
                return False, "", "Command timed out", 124
            
            except ProcessExecutionError as e:
                stdout = _ensure_string(e.stdout if hasattr(e, 'stdout') else "")
                stderr = _ensure_string(e.stderr if hasattr(e, 'stderr') else str(e))
                return_code = e.retcode if hasattr(e, 'retcode') else 1
                
                _cleanup_script(script_path)
                
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
        render_error(f"Exception type: {type(e).__name__}")
        render_error(f"Traceback: {traceback.format_exc()}")
        if automation_logger:
            automation_logger.log_error(f"{error_msg}: {command}")
        if 'script_path' in locals():
            _cleanup_script(script_path)
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
        process = cmd.popen(text=True)
        
        def read_stdout():
            try:
                if hasattr(process, 'stdout') and process.stdout:
                    for line in process.stdout:
                        line = _ensure_string(line)
                        line = line.rstrip('\n\r')
                        if line:
                            stdout_lines.append(line)
                            print(line)
                            sys.stdout.flush()
            except Exception as e:
                error_msg = f"Error reading stdout: {type(e).__name__}: {e}"
                stderr_lines.append(error_msg)
                render_error(f"{error_msg}\n{traceback.format_exc()}")
        
        def read_stderr():
            try:
                if hasattr(process, 'stderr') and process.stderr:
                    for line in process.stderr:
                        line = _ensure_string(line)
                        line = line.rstrip('\n\r')
                        if line:
                            stderr_lines.append(line)
                            print(line, file=sys.stderr)
                            sys.stderr.flush()
            except Exception as e:
                error_msg = f"Error reading stderr: {type(e).__name__}: {e}"
                stderr_lines.append(error_msg)
                render_error(f"{error_msg}\n{traceback.format_exc()}")
        
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        start_time = time.time()
        
        try:
            return_code = None
            while True:
                return_code = _get_process_return_code(process)
                
                if return_code is not None:
                    break
                
                if time.time() - start_time > COMMAND_TIMEOUT_SECONDS:
                    try:
                        process.kill()
                    except (AttributeError, OSError):
                        try:
                            process.terminate()
                        except (AttributeError, OSError):
                            pass
                    raise ProcessTimedOut("Command execution timed out")
                
                time.sleep(0.1)
            
        except ProcessTimedOut:
            render_error("Command execution timed out")
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            _cleanup_script(script_path)
            return False, '\n'.join(stdout_lines), '\n'.join(stderr_lines), 124
        
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        
        if return_code is None:
            return_code = _get_process_return_code(process)
            if return_code is None:
                return_code = 0
        
        _cleanup_script(script_path)
        
        success = return_code == 0
        stdout = '\n'.join(stdout_lines)
        stderr = '\n'.join(stderr_lines)
        
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
        stdout = _ensure_string(e.stdout if hasattr(e, 'stdout') else '\n'.join(stdout_lines))
        stderr = _ensure_string(e.stderr if hasattr(e, 'stderr') else str(e))
        return_code = e.retcode if hasattr(e, 'retcode') else 1
        
        _cleanup_script(script_path)
        
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
        _cleanup_script(script_path)
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

    values = {system_name, distribution_id, distribution}
    values = {v for v in values if v}
    
    if system_name == "darwin":
        values.add("darwin")
        values.add("macos")
        values.add("mac")
        values.add("osx")
    
    if system_name == "linux":
        values.add("linux")
        values.add("unix")
        if distribution_id:
            values.add(distribution_id)
        if distribution:
            values.add(distribution)
    
    if system_name == "windows":
        values.add("windows")
        values.add("win")
        values.add("win32")
    
    generic_unix = {"unix", "posix", "linux", "darwin", "macos", "mac", "osx", "bsd"}
    if candidates & generic_unix and system_name in {"linux", "darwin", "freebsd", "openbsd", "netbsd"}:
        return True
    
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
    
    from dav.input_validator import validate_ai_response
    is_valid, validation_error = validate_ai_response(response)
    if not is_valid:
        render_warning(f"AI response validation warning: {validation_error}")
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
    
    return results

