"""Main CLI interface for Dav."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import typer
from rich.console import Console

if TYPE_CHECKING:
    from dav.ai_backend import FailoverAIBackend
    from dav.executor import ExecutionResult
    from dav.session import SessionManager

app = typer.Typer(help="Dav - An intelligent, context-aware AI assistant for the Linux terminal")
console = Console()




def _check_setup_needed() -> bool:
    """Check if Dav setup is needed (no configuration file or missing API keys).
    
    Returns:
        True if setup is needed, False otherwise
    """
    from pathlib import Path
    from dav.config import get_api_key, get_default_backend
    
    env_file = Path.home() / ".dav" / ".env"
    
    if not env_file.exists():
        return True
    
    try:
        if env_file.stat().st_size == 0:
            return True
    except Exception:
        pass
    
    backend = get_default_backend()
    api_key = get_api_key(backend)
    
    if not api_key:
        for other_backend in ("openai", "anthropic", "gemini"):
            if other_backend == backend:
                continue
            api_key = get_api_key(other_backend)
            if api_key:
                break
    
    return not api_key


def _auto_setup_if_needed() -> bool:
    """Automatically run setup if configuration is missing.
    
    Returns:
        True if setup was run, False if setup was not needed
    """
    if not _check_setup_needed():
        return False
    
    console.print("\n[bold yellow]⚠ Dav is not configured yet.[/bold yellow]")
    console.print("[yellow]Running initial setup...[/yellow]\n")
    
    from dav.setup import run_setup
    run_setup()
    
    return True


@app.command()
def main(
    query: Optional[str] = typer.Argument(None, help="Natural language query"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="Interactive mode for multi-turn conversations"),
    session: Optional[str] = typer.Option(None, "--session", help="Session ID to maintain context"),
    execute: bool = typer.Option(
        False,
        "--execute",
        "--execution",
        help="Execute commands found in response (with confirmation)",
    ),
    backend: Optional[str] = typer.Option(None, "--backend", help="AI backend (openai, anthropic, or gemini)"),
    model: Optional[str] = typer.Option(None, "--model", help="AI model to use"),
    uninstall: bool = typer.Option(False, "--uninstall", help="Complete uninstall: remove all data files and uninstall the package"),
    setup: bool = typer.Option(False, "--setup", help="Set up Dav: create .dav directory and template .env file"),
    update: bool = typer.Option(False, "--update", help="Update Dav to the latest version (preserves configuration)"),
    auto_confirm: bool = typer.Option(
        False,
        "-y",
        "--yes",
        "--auto-yes",
        help="Automatically confirm command execution when using --execute",
    ),
    automation: bool = typer.Option(False, "--automation", help="Enable automation mode (no confirmations, auto-execute, logging)"),
    schedule: Optional[str] = typer.Option(None, "--schedule", help="Schedule a cron job with natural language (e.g., 'update system every night at 3')"),
    cron_setup: bool = typer.Option(False, "--cron-setup", help="Show cron setup examples and instructions"),
    install_for_root: bool = typer.Option(False, "--install-for-root", help="Install Dav for root user (alternative to sudoers)"),
    cve: Optional[str] = typer.Option(
        None,
        "--cve",
        help="Perform vulnerability scan. Use 'scan' for full system scan, or provide a query for AI analysis. Usage: 'dav --cve scan' or 'dav --cve \"your query\"'"
    ),
    log_mode: bool = typer.Option(
        False,
        "-log",
        "--log",
        help="Treat stdin as log content and analyze it. Usage: cat app.log | dav -log \"why is my app crashing\"",
    ),
):
    """Dav - An intelligent, context-aware AI assistant for the Linux terminal."""
    
    if setup:
        from dav.setup import run_setup
        run_setup()
        return
    
    if update:
        from dav.update import run_update
        run_update(confirm=True)
        return
    
    if uninstall:
        from dav.uninstall import run_uninstall
        run_uninstall(confirm=True)
        return
    
    if cron_setup:
        from dav.cron_helper import show_cron_examples
        from dav.sudo_handler import SudoHandler
        from rich.prompt import Confirm
        
        console.print("\n[bold]Cron Setup Guide[/bold]\n")
        console.print(show_cron_examples())
        
        sudo_handler = SudoHandler()
        is_configured, status_msg = sudo_handler.check_sudoers_setup()
        
        console.print("\n[bold]Sudoers Configuration Status[/bold]\n")
        if is_configured:
            console.print(f"[green]✓ {status_msg}[/green]\n")
        else:
            console.print(f"[yellow]⚠ {status_msg}[/yellow]\n")
            console.print("[bold]Would you like to configure password-less sudo automatically?[/bold]")
            console.print("[dim]This will create /etc/sudoers.d/dav-automation with appropriate permissions.[/dim]\n")
            
            if Confirm.ask("Configure sudoers NOPASSWD automatically?", default=True):
                console.print("\n[cyan]Configuring sudoers...[/cyan]")
                console.print("[dim]You may be prompted for your sudo password.[/dim]\n")
                
                use_specific = Confirm.ask(
                    "Use specific commands only (more secure)?",
                    default=True
                )
                
                success, message = sudo_handler.configure_sudoers(specific_commands=use_specific)
                
                if success:
                    console.print(f"[green]✓ {message}[/green]\n")
                    console.print("[green]Sudoers configuration complete![/green]")
                    console.print("[dim]You can now use Dav automation with sudo commands.[/dim]\n")
                else:
                    console.print(f"[red]✗ {message}[/red]\n")
                    console.print("[yellow]Manual configuration may be required.[/yellow]")
                    console.print(sudo_handler.get_sudoers_instructions())
            else:
                console.print("\n[yellow]Skipping automatic configuration.[/yellow]")
                console.print(sudo_handler.get_sudoers_instructions())
        
        return
    
    if install_for_root:
        from dav.setup import run_root_installation
        run_root_installation()
        return
    
    if schedule:
        _handle_schedule_command(schedule)
        return
    
    # Disallow incompatible mode combinations early
    if log_mode and automation:
        from dav.terminal import render_error
        
        render_error("The -log/--log option cannot be used together with --automation.")
        sys.exit(1)
    
    # Handle CVE operations early (before AI processing)
    # Check if --cve flag was provided (even if value is None)
    cve_flag_provided = "--cve" in sys.argv
    
    if cve_flag_provided:
        if log_mode:
            from dav.terminal import render_error
            
            render_error("The -log/--log option cannot be used together with --cve.")
            sys.exit(1)
        from dav.vulnerability.cli import handle_cve_command
        # If cve is None or empty string, default to "scan"
        if cve is None or (isinstance(cve, str) and not cve.strip()):
            cve_arg = "scan"
        else:
            cve_arg = cve.strip()
        handle_cve_command(cve_arg, execute, auto_confirm, automation)
        return
    
    is_automation_mode = automation
    if not is_automation_mode and not sys.stdin.isatty() and not sys.stdout.isatty():
        is_automation_mode = True
        console.print("[yellow]Auto-detected automation mode (non-TTY)[/yellow]")
    
    # Read stdin content once so it can be reused consistently
    stdin_content = None
    try:
        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read()
    except Exception:
        stdin_content = None
    
    # Handle log mode stdin behavior
    if log_mode:
        from dav.terminal import render_error, render_warning
        
        if sys.stdin.isatty() or not stdin_content:
            render_error(
                "The -log/--log option requires log content via stdin (e.g., 'cat app.log | dav -log')."
            )
            sys.exit(1)
        
        # Log mode is analysis-only: disable automation and execution
        if is_automation_mode:
            is_automation_mode = False
            render_warning("Ignoring auto-detected automation mode for -log; running analysis-only.")
        
        if execute:
            render_warning("Ignoring --execute for -log; running in analysis-only log analysis mode.")
            execute = False
        
        # If no explicit query provided, use a log-focused default
        if not query:
            query = "analyze these logs"
    else:
        # Default stdin behavior when not in log mode
        if not query and stdin_content:
            query = "analyze this"
    
    if _auto_setup_if_needed():
        import importlib
        from dav import config
        importlib.reload(config)
    
    from dav.ai_backend import FailoverAIBackend
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.context import build_context, format_context_for_prompt
    from dav.executor import COMMAND_EXECUTION_MARKER, execute_commands_from_response
    from dav.session import SessionManager
    from dav.terminal import (
        render_error,
        render_info,
        render_streaming_response_with_loading,
        render_warning,
    )
    
    session_manager = SessionManager(session_id=session)
    
    # Try to restore provider from session if available
    session_provider = session_manager.get_active_provider()
    if session_provider and not backend:
        # Use session provider if no explicit backend specified
        backend = session_provider
    
    try:
        ai_backend = FailoverAIBackend(backend=backend, model=model)
        # Store active provider in session for persistence
        session_manager.set_active_provider(ai_backend.backend)
    except ValueError as e:
        error_msg = str(e)
        render_error(error_msg)
        if "API key not found" in error_msg:
            console.print("\n[yellow]Tip:[/yellow] Run [cyan]dav --setup[/cyan] to configure your API keys.")
        sys.exit(1)
    
    automation_logger = None
    if is_automation_mode:
        from dav.automation import AutomationLogger
        automation_logger = AutomationLogger()
        if query:
            automation_logger.set_task(query)
        execute = True
        auto_confirm = True
        
        if not query:
            render_error("Automation mode requires a query. Use 'dav --automation \"your task\"'")
            if automation_logger:
                automation_logger.log_error("Automation mode requires a query")
                automation_logger.close()
            sys.exit(1)
    
    if not query and not interactive:
        interactive = True
        execute = True
    
    if interactive:
        if is_automation_mode:
            render_warning("Automation mode and interactive mode are mutually exclusive. Using automation mode.")
        else:
            run_interactive_mode(ai_backend, session_manager, execute, auto_confirm)
            return
    
    if not query:
        render_error("No query provided. Use 'dav \"your question\"' or 'dav -i' for interactive mode.")
        sys.exit(1)
    
    from dav.input_validator import (
        sanitize_user_input,
        detect_prompt_injection,
        validate_query_length,
    )
    
    is_valid, length_error = validate_query_length(query)
    if not is_valid:
        render_error(length_error or "Query validation failed")
        sys.exit(1)
    
    query = sanitize_user_input(query)
    
    is_injection, injection_reason = detect_prompt_injection(query)
    if is_injection:
        render_warning(f"Potential prompt injection detected: {injection_reason}")
        render_warning("This query may be blocked or modified for security.")
    
    context_data, full_prompt, system_prompt = _build_prompt_with_context(
        query,
        session_manager,
        stdin_content=stdin_content,
        execute_mode=execute,
        interactive_mode=False,
        automation_mode=is_automation_mode,
        log_mode=log_mode,
    )
    
    try:
        backend_name = ai_backend.backend.title()
        response = render_streaming_response_with_loading(
            ai_backend.stream_response(full_prompt, system_prompt=system_prompt),
                loading_message=f"Generating response with {backend_name}...",
        )
        
        # Update session with current provider (in case failover occurred)
        session_manager.set_active_provider(ai_backend.backend)
        
        from dav.input_validator import validate_ai_response
        is_valid_response, validation_error = validate_ai_response(response)
        if not is_valid_response:
            render_error(f"AI response validation failed: {validation_error}")
            if automation_logger:
                automation_logger.log_error(f"Response validation failed: {validation_error}")
            sys.exit(1)
        
        if automation_logger:
            automation_logger.record_ai_response(response)

        _process_response(
            response,
            query,
            ai_backend,
            session_manager,
            execute,
            auto_confirm,
            context_data,
            is_interactive=False,
            automation_mode=is_automation_mode,
            automation_logger=automation_logger,
            log_mode=log_mode,
        )
        
        if automation_logger:
            log_path = automation_logger.get_log_path()
            automation_logger.close()
            console.print(f"\n[green]Log saved to: {log_path}[/green]")

    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Interrupted by user[/bold yellow]")
        if automation_logger:
            automation_logger.log_error("Interrupted by user")
            automation_logger.close()
        sys.exit(0)
    except Exception as e:
        render_error(f"Error: {str(e)}")
        if automation_logger:
            automation_logger.log_error(f"Error: {str(e)}")
            automation_logger.close()
        sys.exit(1)


def _build_prompt_with_context(
    query: str,
    session_manager: SessionManager,
    stdin_content: Optional[str] = None,
    execute_mode: bool = False,
    interactive_mode: bool = False,
    automation_mode: bool = False,
    command_outputs: Optional[List[Dict[str, Any]]] = None,
    log_mode: bool = False,
) -> Tuple[Dict, str, str]:
    """
    Build prompt with context and session history.
    
    Args:
        query: User query
        session_manager: Session manager instance
        stdin_content: Optional stdin content
        execute_mode: Whether in execute mode (affects system prompt)
        interactive_mode: Whether in interactive mode (affects system prompt)
        automation_mode: Whether in automation mode
        command_outputs: Optional list of recent command outputs to include
    
        Returns:
        Tuple of (context_dict, context_string, system_prompt)
    """
    from dav.context import build_context, format_context_for_prompt
    from dav.ai_backend import get_system_prompt
    
    context = build_context(query=query, stdin_content=stdin_content)
    
    # Annotate context when in dedicated log analysis mode
    if log_mode:
        context["log_mode"] = True
    
    context_str = format_context_for_prompt(context, command_outputs=command_outputs)
    
    session_context = session_manager.get_conversation_context()
    if session_context:
        context_str = session_context + "\n" + context_str
    
    system_prompt = get_system_prompt(execute_mode=execute_mode, interactive_mode=interactive_mode, automation_mode=automation_mode)
    
    return context, context_str, system_prompt


def _process_response(
    response: str,
    query: str,
    ai_backend: FailoverAIBackend,
    session_manager: SessionManager,
    execute: bool,
    auto_confirm: bool,
    context_data: Optional[Dict],
    is_interactive: bool = False,
    automation_mode: bool = False,
    automation_logger: Optional[Any] = None,
    log_mode: bool = False,
) -> None:
    """
    Process and save response, optionally execute commands.
    
    Args:
        response: AI response text
        query: User query
        ai_backend: AI backend instance
        session_manager: Session manager instance
        execute: Whether to execute commands
        auto_confirm: Whether to auto-confirm execution
        context_data: Context data dictionary
        is_interactive: Whether in interactive mode (affects execution result storage)
    """
    from dav.config import get_execute_permission
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.executor import COMMAND_EXECUTION_MARKER, execute_commands_from_response
    from dav.terminal import render_warning
    
    session_manager.add_message("user", query)
    session_manager.add_message("assistant", response)
    
    # Log mode is strictly analysis-only: never execute commands
    should_execute = (execute or get_execute_permission()) and not log_mode
    if should_execute:
        has_marker = COMMAND_EXECUTION_MARKER in response
        
        if has_marker:
            confirm = not auto_confirm
            execution_results = _execute_with_feedback_loop(
                initial_response=response,
                query=query,
                ai_backend=ai_backend,
                session_manager=session_manager,
                context_data=context_data,
                confirm=confirm,
                auto_confirm=auto_confirm,
                is_interactive=is_interactive,
                automation_mode=automation_mode,
                automation_logger=automation_logger,
            )


def _format_execution_feedback(execution_results: List, original_query: str) -> str:
    """
    Format execution results into a prompt for AI to analyze and provide next steps.
    
    Args:
        execution_results: List of ExecutionResult objects
        original_query: Original user query
    
    Returns:
        Formatted prompt string for AI
    """
    from dav.input_validator import sanitize_command_output
    
    lines = []
    lines.append("## Command Execution Results")
    lines.append("")
    lines.append(f"**Original Task:** {original_query}")
    lines.append("")
    
    for idx, result in enumerate(execution_results, 1):
        status = "✓ Success" if result.success else "✗ Failed"
        lines.append(f"### Command {idx}")
        lines.append(f"**Command:** `{result.command}`")
        lines.append(f"**Status:** {status} (exit code: {result.return_code})")
        lines.append("")
        
        if result.stdout:
            stdout = sanitize_command_output(result.stdout)
            if len(stdout) > 3000:
                stdout = stdout[:2000] + "\n[... truncated ...]\n" + stdout[-500:]
            lines.append("**Output:**")
            lines.append("```")
            lines.append(stdout)
            lines.append("```")
            lines.append("")
        
        if result.stderr:
            stderr = sanitize_command_output(result.stderr)
            if len(stderr) > 1000:
                stderr = stderr[:800] + "\n[... truncated ...]\n" + stderr[-200:]
            lines.append("**Error Output:**")
            lines.append("```")
            lines.append(stderr)
            lines.append("```")
            lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("**Your Task:**")
    lines.append("Based on the command execution results above, analyze the output and determine:")
    lines.append("1. What does the output indicate?")
    lines.append("2. Is the original task complete, or are additional commands needed?")
    lines.append("3. If more commands are needed, provide them with the >>>EXEC<<< marker.")
    lines.append("4. If the task is complete, explicitly state 'Task complete' or 'No further commands needed'.")
    lines.append("5. Explain your reasoning at each step.")
    lines.append("")
    
    return "\n".join(lines)


def _is_task_complete(response: str) -> bool:
    """
    Check if AI response indicates task completion.
    
    Args:
        response: AI response text
    
    Returns:
        True if task is complete, False otherwise
    """
    from dav.executor import COMMAND_EXECUTION_MARKER
    
    if COMMAND_EXECUTION_MARKER in response:
        return False
    
    completion_phrases = [
        "task complete",
        "task is complete",
        "task completed",
        "no further commands needed",
        "no more commands needed",
        "no additional commands",
        "all done",
        "finished",
        "completed successfully",
        "task finished",
    ]
    
    response_lower = response.lower()
    for phrase in completion_phrases:
        if phrase in response_lower:
            return True
    
    return False


def _execute_with_feedback_loop(
    initial_response: str,
    query: str,
    ai_backend: FailoverAIBackend,
    session_manager: SessionManager,
    context_data: Optional[Dict],
    confirm: bool,
    auto_confirm: bool,
    is_interactive: bool,
    automation_mode: bool = False,
    automation_logger: Optional[Any] = None,
) -> List:
    """
    Execute commands with automatic feedback loop.
    
    After each command execution, feeds results back to AI for analysis
    and continues until AI indicates task is complete.
    
    Args:
        initial_response: AI's initial response with commands
        query: Original user query
        ai_backend: AI backend instance
        session_manager: Session manager instance
        context_data: System context data
        confirm: Whether to ask for confirmation
        auto_confirm: Whether to auto-confirm execution
        is_interactive: Whether in interactive mode
    """
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.executor import COMMAND_EXECUTION_MARKER, execute_commands_from_response
    from dav.terminal import render_error, render_info, render_streaming_response_with_loading, render_warning
    
    # Extract command plan if available (preferred over heuristic extraction)
    plan = None
    try:
        plan = extract_command_plan(initial_response)
    except CommandPlanError:
        pass
    
    execution_results: List = []
    
    console.print()
    render_info("[bold cyan]Step 1:[/bold cyan] Executing initial commands...")
    console.print()
    
    execution_results = execute_commands_from_response(
        initial_response,
        confirm=confirm,
        context=context_data,
        plan=plan,
        automation_mode=automation_mode,
        automation_logger=automation_logger,
    )
    
    if not execution_results:
        render_warning("No commands were executed. Task may already be complete.")
        return []
    
    session_manager.add_execution_results(execution_results)
    
    max_iterations = 10
    iteration = 1
    
    while iteration < max_iterations:
        iteration += 1
        
        feedback_prompt = _format_execution_feedback(execution_results, query)
        
        console.print()
        render_info(f"[bold cyan]Step {iteration}:[/bold cyan] Analyzing results and determining next steps...")
        console.print()
        
        from dav.ai_backend import get_system_prompt
        
        session_context = session_manager.get_conversation_context()
        
        full_feedback_prompt = ""
        if session_context:
            full_feedback_prompt = session_context + "\n\n" + feedback_prompt
        else:
            full_feedback_prompt = feedback_prompt
        
        system_prompt = get_system_prompt(execute_mode=True, interactive_mode=is_interactive)
        
        backend_name = ai_backend.backend.title()
        followup_response = render_streaming_response_with_loading(
            ai_backend.stream_response(full_feedback_prompt, system_prompt=system_prompt),
            loading_message=f"Analyzing with {backend_name}...",
        )
        console.print()
        
        # Update session with current provider (in case failover occurred)
        session_manager.set_active_provider(ai_backend.backend)
        
        session_manager.add_message("assistant", followup_response)
        
        if _is_task_complete(followup_response):
            render_info("[bold green]✓ Task complete![/bold green]")
            console.print()
            break
        
        if COMMAND_EXECUTION_MARKER not in followup_response:
            render_info("AI provided analysis but no commands. Checking if task is complete...")
            if "complete" in followup_response.lower() or "done" in followup_response.lower():
                render_info("[bold green]✓ Task complete![/bold green]")
                console.print()
                break
            else:
                render_warning("AI response unclear. Assuming task needs more steps.")
                continue
        
        render_info(f"[bold cyan]Step {iteration} (continued):[/bold cyan] Executing follow-up commands...")
        console.print()
        
        plan = None
        try:
            plan = extract_command_plan(followup_response)
        except CommandPlanError:
            pass
        
        step_results = execute_commands_from_response(
            followup_response,
            confirm=confirm,
            context=context_data,
            plan=plan,
            automation_mode=automation_mode,
            automation_logger=automation_logger,
        )
        
        execution_results.extend(step_results)
        
        if not step_results:
            render_warning("No commands found in AI response. Task may be complete.")
            break
        
        session_manager.add_execution_results(step_results)
    
    if iteration >= max_iterations:
        render_error(f"Reached maximum iteration limit ({max_iterations}). Stopping feedback loop.")
        console.print()
        render_warning("If the task is not complete, you may need to continue manually.")
        if automation_logger:
            automation_logger.log_warning(f"Reached maximum iteration limit ({max_iterations})")
    
    if automation_logger and execution_results:
        task_status = "Task (incomplete)" if iteration >= max_iterations else "Task completed"
        automation_logger.log_summary(f"{task_status}: {query}", execution_results)
    
    return execution_results


def _truncate_output(output: str, max_lines: int = 2000, keep_lines: int = 1000) -> str:
    """
    Truncate output intelligently.
    
    Args:
        output: Output string to truncate
        max_lines: Maximum lines before truncation
        keep_lines: Number of lines to keep when truncating
    
    Returns:
        Truncated output string with note if truncated
    """
    if not output:
        return output
    
    lines = output.split('\n')
    if len(lines) <= max_lines:
        return output
    
    truncated = '\n'.join(lines[-keep_lines:])
    return f"[... {len(lines) - keep_lines} lines truncated ...]\n{truncated}"


def _store_command_output(command: str, stdout: str, stderr: str, success: bool, 
                          command_outputs: List[Dict[str, Any]]) -> None:
    """
    Store command output in the command_outputs list, maintaining max 20 commands.
    
    Args:
        command: Command string that was executed
        stdout: Standard output
        stderr: Standard error
        success: Whether command succeeded
        command_outputs: List to store command outputs
    """
    import time
    
    truncated_stdout = _truncate_output(stdout)
    truncated_stderr = _truncate_output(stderr)
    
    command_outputs.append({
        "command": command,
        "stdout": truncated_stdout,
        "stderr": truncated_stderr,
        "success": success,
        "timestamp": time.time()
    })
    
    if len(command_outputs) > 20:
        command_outputs.pop(0)


def _handle_command_execution(command: str, command_outputs: List[Dict[str, Any]]) -> bool:
    """
    Execute a shell command and handle directory changes.
    
    Args:
        command: Command string (with > prefix already stripped)
        command_outputs: List to store command outputs for Dav context
    
    Returns:
        True if command executed successfully, False otherwise
    """
    import os
    from dav.executor import execute_command
    from dav.terminal import render_error
    
    command = command.strip()
    if not command:
        return False
    
    if command.startswith("cd "):
        target_dir = command[3:].strip()
        if not target_dir:
            target_dir = os.path.expanduser("~")
        else:
            target_dir = os.path.expanduser(target_dir)
            target_dir = os.path.expandvars(target_dir)
        
        try:
            os.chdir(target_dir)
            _store_command_output(command, "", "", True, command_outputs)
            return True
        except FileNotFoundError:
            error_msg = f"Directory not found: {target_dir}"
            render_error(error_msg)
            _store_command_output(command, "", error_msg, False, command_outputs)
            return False
        except PermissionError:
            error_msg = f"Permission denied: {target_dir}"
            render_error(error_msg)
            _store_command_output(command, "", error_msg, False, command_outputs)
            return False
        except Exception as e:
            error_msg = f"Error changing directory: {str(e)}"
            render_error(error_msg)
            _store_command_output(command, "", error_msg, False, command_outputs)
            return False
    
    try:
        success, stdout, stderr, return_code = execute_command(
            command,
            confirm=False,
            stream_output=True,
            automation_mode=False,
        )
        
        _store_command_output(command, stdout, stderr, success, command_outputs)
        return success
    except Exception as e:
        error_msg = f"Error executing command: {str(e)}"
        render_error(error_msg)
        _store_command_output(command, "", error_msg, False, command_outputs)
        return False


def _process_query_with_ai(query: str, ai_backend: FailoverAIBackend, session_manager, 
                           execute: bool, auto_confirm: bool, command_outputs: List[Dict[str, Any]]) -> None:
    """
    Process a query with the AI backend (validation, sanitization, and response).
    
    Args:
        query: User query string
        ai_backend: AI backend instance
        session_manager: Session manager instance
        execute: Execute mode flag
        auto_confirm: Auto confirm flag
        command_outputs: List of command outputs for Dav context
    """
    from dav.terminal import render_error, render_warning, render_streaming_response_with_loading
    from dav.input_validator import sanitize_user_input, detect_prompt_injection, validate_query_length
    
    is_valid, length_error = validate_query_length(query)
    if not is_valid:
        render_error(length_error or "Query validation failed")
        return
    
    query = sanitize_user_input(query)
    
    is_injection, injection_reason = detect_prompt_injection(query)
    if is_injection:
        render_warning(f"Potential prompt injection detected: {injection_reason}")
    
    context_data, full_prompt, system_prompt = _build_prompt_with_context(
        query, session_manager, execute_mode=execute, interactive_mode=True, command_outputs=command_outputs
    )
    
    backend_name = ai_backend.backend.title()
    console.print()
    response = render_streaming_response_with_loading(
        ai_backend.stream_response(full_prompt, system_prompt=system_prompt),
        loading_message=f"Generating response with {backend_name}...",
    )
    console.print()
    
    # Update session with current provider (in case failover occurred)
    session_manager.set_active_provider(ai_backend.backend)
    
    _process_response(
        response,
        query,
        ai_backend,
        session_manager,
        execute,
        auto_confirm,
        context_data,
        is_interactive=True,
        log_mode=False,
    )
    
    console.print()


def _handle_app_function(func_name: str, current_mode: str, command_outputs: List[Dict[str, Any]]) -> Tuple[Optional[str], bool]:
    """
    Handle app functions (commands starting with /).
    
    Args:
        func_name: Function name (without / prefix)
        current_mode: Current mode ("interactive" or "command")
        command_outputs: List of command outputs (cleared on mode switch)
    
    Returns:
        Tuple of (new_mode, should_exit)
        - new_mode: New mode to switch to, or None if no change
        - should_exit: True if should exit interactive mode
    """
    from dav.terminal import render_error, render_info, render_dav_banner
    
    func_name = func_name.lower().strip()
    
    if func_name == "exit":
        return None, True
    
    elif func_name == "cmd":
        if current_mode == "command":
            render_info("Already in command mode. Commands can be run directly without '>' prefix.")
            return None, False
        command_outputs.clear()
        console.clear()
        render_dav_banner()
        console.print("[bold green]Dav Interactive Mode[/bold green]")
        console.print("Type 'exit' or 'quit' to exit, 'clear' to clear session")
        console.print("Use '>' prefix to execute commands, '/' for functions (/exit, /cmd, /dav, /int, /clear)\n")
        render_info("Entering command mode. Commands can be run directly without '>' prefix. Use '/dav' to talk to Dav.")
        return "command", False
    
    elif func_name == "dav":
        if current_mode != "command":
            render_error("'/dav' can only be used in command mode. Use '/cmd' to enter command mode first.")
            return None, False
        return None, False
    
    elif func_name == "int":
        if current_mode == "interactive":
            render_info("Already in interactive mode.")
            return None, False
        command_outputs.clear()
        console.clear()
        render_dav_banner()
        console.print("[bold green]Dav Interactive Mode[/bold green]")
        console.print("Type 'exit' or 'quit' to exit, 'clear' to clear session")
        console.print("Use '>' prefix to execute commands, '/' for functions (/exit, /cmd, /dav, /int, /clear)\n")
        render_info("Switching to interactive mode.")
        return "interactive", False
    
    elif func_name == "clear":
        console.clear()
        render_dav_banner()
        console.print("[bold green]Dav Interactive Mode[/bold green]")
        console.print("Type 'exit' or 'quit' to exit, 'clear' to clear session")
        console.print("Use '>' prefix to execute commands, '/' for functions (/exit, /cmd, /dav, /int, /clear)\n")
        return None, False
    
    else:
        render_error(f"Unknown function: /{func_name}. Available functions: /exit, /cmd, /dav, /int, /clear")
        return None, False


def _route_input(user_input: str, current_mode: str, ai_backend, session_manager, 
                 execute: bool, auto_confirm: bool, command_outputs: List[Dict[str, Any]]) -> Tuple[Optional[str], bool]:
    """
    Route user input based on prefix and current mode.
    
    Args:
        user_input: User input string
        current_mode: Current mode ("interactive" or "command")
        ai_backend: AI backend instance
        session_manager: Session manager instance
        execute: Execute mode flag
        auto_confirm: Auto confirm flag
        command_outputs: List of command outputs for Dav context
    
    Returns:
        Tuple of (new_mode, should_exit)
        - new_mode: New mode to switch to, or None if no change
        - should_exit: True if should exit interactive mode
    """
    from dav.terminal import render_warning
    
    if not user_input:
        return None, False
    
    if user_input.startswith(">"):
        command = user_input[1:].strip()
        if command:
            _handle_command_execution(command, command_outputs)
        return None, False
    
    if user_input.startswith("/"):
        parts = user_input[1:].strip().split(None, 1)
        func_name = parts[0] if parts else ""
        remaining_text = parts[1] if len(parts) > 1 else None
        
        if remaining_text and func_name != "dav":
            render_warning(f"Extra text after /{func_name} will be ignored. Use '/dav <text>' to ask Dav a question.")
        
        new_mode, should_exit = _handle_app_function(func_name, current_mode, command_outputs)
        
        if func_name == "dav" and remaining_text and new_mode is None:
            query = remaining_text.strip()
            if query:
                _process_query_with_ai(
                    query, ai_backend, session_manager,
                    execute, auto_confirm, command_outputs
                )
            return None, False
        
        return new_mode, should_exit
    
    if current_mode == "command":
        _handle_command_execution(user_input, command_outputs)
        return None, False
    else:
        _process_query_with_ai(
            user_input, ai_backend, session_manager,
            execute, auto_confirm, command_outputs
        )
        return None, False


def run_interactive_mode(ai_backend: FailoverAIBackend,
                        session_manager: SessionManager, execute: bool, auto_confirm: bool):
    """Run interactive mode for multi-turn conversations."""
    from dav.terminal import render_error, render_streaming_response_with_loading, render_context_status, render_warning, render_dav_banner
    from dav.context_tracker import ContextTracker
    from dav.context import format_context_for_prompt, build_context
    
    console.clear()
    
    context_tracker = ContextTracker(backend=ai_backend.backend, model=ai_backend.model)
    
    render_dav_banner()
    
    console.print("[bold green]Dav Interactive Mode[/bold green]")
    console.print("Type 'exit' or 'quit' to exit, 'clear' to clear session")
    console.print("Use '>' prefix to execute commands, '/' for functions (/exit, /cmd, /dav, /int, /clear)\n")
    
    current_mode = "interactive"
    
    command_outputs: List[Dict[str, Any]] = []
    
    def display_prompt_with_context():
        """Display context status panel and prompt."""
        context_data = build_context(query=None)
        system_context_str = format_context_for_prompt(context_data)
        session_history_str = session_manager.get_conversation_context()
        usage = context_tracker.calculate_usage(
            system_context=system_context_str,
            session_history=session_history_str,
            current_query=""
        )
        render_context_status(usage, model=ai_backend.model, backend=ai_backend.backend)
        
        from dav.terminal import format_interactive_prompt
        prompt_text = format_interactive_prompt(mode=current_mode)
        console.print(prompt_text, end="")
        
        user_input = input()
        return user_input.strip()
    
    while True:
        try:
            user_input = display_prompt_with_context()
            
            if not user_input:
                continue
            
            if user_input.lower() in ("exit", "quit", "q"):
                break
            
            if user_input.lower() == "clear":
                session_manager.clear_session()
                console.print("Session cleared.\n")
                continue
            
            new_mode, should_exit = _route_input(
                user_input,
                current_mode,
                ai_backend,
                session_manager,
                execute,
                auto_confirm,
                command_outputs,
            )
            
            if new_mode:
                current_mode = new_mode
            
            if should_exit:
                break
        
        except KeyboardInterrupt:
            console.print("\n\n[bold yellow]Interrupted. Type 'exit' or '/exit' to quit.[/bold yellow]\n")
        except EOFError:
            break
        except Exception as e:
            render_error(f"Error: {str(e)}")
    
    console.print("\n[bold]Goodbye![/bold]")


def _handle_schedule_command(schedule_input: str) -> None:
    """Handle --schedule command to set up cron jobs."""
    from dav.ai_backend import FailoverAIBackend
    from dav.cron_helper import add_cron_job
    from dav.schedule_parser import parse_schedule
    from dav.terminal import render_error, render_warning
    
    console.print("[cyan]Parsing schedule and setting up cron job...[/cyan]\n")
    
    if _auto_setup_if_needed():
        import importlib
        from dav import config
        importlib.reload(config)
    
    ai_backend = None
    try:
        ai_backend = FailoverAIBackend()
    except ValueError as e:
        console.print("[dim]AI backend not available, using fallback parsers...[/dim]\n")
    
    result = parse_schedule(schedule_input, ai_backend=ai_backend)
    
    if not result.success:
        render_error("Could not parse schedule")
        if result.error:
            error_lines = result.error.split('\n')
            for line in error_lines:
                if line.strip():
                    console.print(f"[red]{line}[/red]")
        else:
            console.print("[red]Unknown parsing error[/red]")
        
        if result.attempts > 0:
            console.print(f"\n[dim]AI parsing attempts: {result.attempts}[/dim]")
        console.print("\n[yellow]Tip:[/yellow] Try rephrasing your schedule request.")
        sys.exit(1)
    
    # Extract task and schedule from result
    task = result.task or schedule_input
    cron_schedule = result.schedule
    
    if not cron_schedule:
        render_error("Could not determine schedule from input")
        sys.exit(1)
    
    method_names = {
        "ai": "AI parsing",
        "dateparser": "dateparser library",
        "regex": "pattern matching"
    }
    method_name = method_names.get(result.method, "unknown method")
    console.print(f"[dim]Parsed using: {method_name}[/dim]\n")
    
    from dav.sudo_handler import SudoHandler
    from rich.prompt import Confirm
    
    sudo_handler = SudoHandler()
    is_configured, status_msg = sudo_handler.check_sudoers_setup()
    
    task_lower = task.lower()
    sudo_keywords = [
        "update", "upgrade", "install", "remove", "system", "service",
        "restart", "start", "stop", "enable", "disable", "configure",
        "maintenance", "security", "package", "apt", "yum", "dnf",
        "systemctl", "journalctl", "log", "firewall", "ufw"
    ]
    might_need_sudo = any(keyword in task_lower for keyword in sudo_keywords)
    
    if not is_configured and might_need_sudo:
        console.print()
        render_warning("Password-less sudo (NOPASSWD) is not configured.")
        console.print(f"[yellow]⚠ {status_msg}[/yellow]")
        console.print()
        console.print("[bold]Important:[/bold] Scheduled tasks that require sudo will fail silently")
        console.print("if password-less sudo is not configured.")
        console.print()
        console.print("[bold]Would you like to configure password-less sudo now?[/bold]")
        console.print("[dim]This will create /etc/sudoers.d/dav-automation with appropriate permissions.[/dim]")
        console.print()
        
        if Confirm.ask("Configure sudoers NOPASSWD automatically?", default=True):
            console.print()
            console.print("[cyan]Configuring sudoers...[/cyan]")
            console.print("[dim]You may be prompted for your sudo password.[/dim]")
            console.print()
            
            use_specific = Confirm.ask(
                "Use specific commands only (more secure)?",
                default=True
            )
            
            success, message = sudo_handler.configure_sudoers(specific_commands=use_specific)
            
            if success:
                console.print()
                console.print(f"[green]✓ {message}[/green]")
                console.print()
            else:
                console.print()
                console.print(f"[red]✗ {message}[/red]")
                console.print()
                console.print("[yellow]You can still schedule the task, but it may fail if sudo is required.[/yellow]")
                console.print(sudo_handler.get_sudoers_instructions())
            console.print()
            
            if not Confirm.ask("Continue scheduling anyway?", default=True):
                console.print("[yellow]Scheduling cancelled.[/yellow]")
                sys.exit(0)
        else:
            console.print()
            console.print("[yellow]Skipping automatic configuration.[/yellow]")
            console.print(sudo_handler.get_sudoers_instructions())
            console.print()
            console.print("[yellow]Warning: The scheduled task may fail if it requires sudo.[/yellow]")
            console.print()
            
            if not Confirm.ask("Continue scheduling anyway?", default=True):
                console.print("[yellow]Scheduling cancelled.[/yellow]")
                sys.exit(0)
    elif not is_configured:
        console.print()
        render_warning("Password-less sudo is not configured.")
        console.print("[dim]If this task requires sudo, it will fail. Run 'dav --cron-setup' to configure.[/dim]")
        console.print()
    
    success, message, match_type, existing_entry = add_cron_job(cron_schedule, task, auto_confirm=True)
    
    if success:
        console.print(f"[green]✓ {message}[/green]")
        console.print(f"\n[cyan]Cron job added successfully![/cyan]")
        console.print(f"[dim]View with: crontab -l[/dim]")
        
        if not is_configured and might_need_sudo:
            console.print()
            render_warning("Remember: Configure password-less sudo with 'dav --cron-setup' if this task requires sudo.")
    else:
        if match_type == "exact" or match_type == "task_and_schedule":
            render_error(message)
            if existing_entry:
                console.print(f"\n[dim]Existing entry: {existing_entry}[/dim]")
            console.print("\n[yellow]Tip:[/yellow] Use 'crontab -e' to manually edit or remove the existing job.")
            sys.exit(1)
        
        elif match_type == "task_only":
            from dav.cron_helper import find_similar_cron_jobs, replace_cron_job
            
            console.print()
            render_warning("A similar task is already scheduled with a different time.")
            console.print()
            
            similar_jobs = find_similar_cron_jobs(task, cron_schedule)
            
            if similar_jobs:
                console.print("[bold]Existing scheduled jobs:[/bold]")
                for idx, (existing_schedule, existing_entry_full) in enumerate(similar_jobs, 1):
                    console.print(f"  {idx}. Schedule: [cyan]{existing_schedule}[/cyan]")
                    console.print(f"     Entry: [dim]{existing_entry_full}[/dim]")
                console.print()
            
            console.print(f"[bold]New schedule:[/bold] [cyan]{cron_schedule}[/cyan]")
            console.print(f"[bold]Task:[/bold] {task}")
            console.print()
            console.print("[bold]Choose an action:[/bold]")
            console.print("  1. Skip (keep existing schedule)")
            console.print("  2. Replace (update to new schedule)")
            console.print("  3. Add anyway (both will run)")
            console.print()
            
            choice = None
            while choice not in ["1", "2", "3"]:
                try:
                    choice = input("Enter choice (1-3): ").strip()
                    if choice not in ["1", "2", "3"]:
                        console.print("[red]Invalid choice. Please enter 1, 2, or 3.[/red]")
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[yellow]Cancelled.[/yellow]")
                    sys.exit(0)
            
            if choice == "1":
                # Skip
                console.print("\n[yellow]Skipping. Existing schedule kept.[/yellow]")
                sys.exit(0)
            
            elif choice == "2":
                if not similar_jobs:
                    if existing_entry:
                        old_entry = existing_entry
                    else:
                        render_error("Could not find existing entry to replace.")
                        sys.exit(1)
                else:
                    old_entry = similar_jobs[0][1]
                
                console.print()
                console.print("[cyan]Replacing existing cron job...[/cyan]")
                
                replace_success, replace_message = replace_cron_job(old_entry, cron_schedule, task)
                
                if replace_success:
                    console.print(f"[green]✓ {replace_message}[/green]")
                    console.print(f"\n[cyan]Cron job updated successfully![/cyan]")
                    console.print(f"[dim]View with: crontab -l[/dim]")
                else:
                    render_error(replace_message)
                    sys.exit(1)
            
            elif choice == "3":
                from dav.cron_helper import detect_dav_path, get_current_crontab, _write_crontab
                
                dav_path = detect_dav_path()
                new_cron_entry = f'{cron_schedule} {dav_path} --automation "{task}"'
                
                current_crontab = get_current_crontab()
                new_crontab = current_crontab + [new_cron_entry]
                
                success, error_msg = _write_crontab(new_crontab)
                
                if success:
                    console.print()
                    console.print(f"[green]✓ Scheduled: {task} (schedule: {cron_schedule})[/green]")
                    console.print(f"\n[cyan]Cron job added successfully![/cyan]")
                    console.print(f"[dim]View with: crontab -l[/dim]")
                    console.print()
                    console.print("[yellow]Note:[/yellow] Multiple jobs with the same task are now scheduled.")
                else:
                    error_message = f"Failed to install crontab: {error_msg}" if error_msg else "Failed to install crontab"
                    render_error(error_message)
                    sys.exit(1)
        
        else:
            render_error(message)
            sys.exit(1)


if __name__ == "__main__":
    app()

