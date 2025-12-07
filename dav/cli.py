"""Main CLI interface for Dav."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import typer
from rich.console import Console

# Type hints only - not imported at runtime
if TYPE_CHECKING:
    from dav.ai_backend import AIBackend
    from dav.executor import ExecutionResult
    from dav.history import HistoryManager
    from dav.session import SessionManager

# Lazy imports for heavy modules - only load when needed
# Fast commands (setup, update, uninstall, etc.) don't need these

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
    
    # If .env file doesn't exist, setup is needed
    if not env_file.exists():
        return True
    
    # If .env file exists but is empty, setup is needed
    try:
        if env_file.stat().st_size == 0:
            return True
    except Exception:
        # If we can't check size, assume setup might be needed
        pass
    
    # Check if we have at least one API key configured
    backend = get_default_backend()
    api_key = get_api_key(backend)
    
    # If no API key for default backend, check the other backend
    if not api_key:
        other_backend = "anthropic" if backend == "openai" else "openai"
        api_key = get_api_key(other_backend)
    
    # Setup needed if no API keys found
    return not api_key


def _auto_setup_if_needed() -> bool:
    """Automatically run setup if configuration is missing.
    
    Returns:
        True if setup was run, False if setup was not needed
    """
    if not _check_setup_needed():
        return False
    
    # Setup is needed - run it automatically
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
    history: bool = typer.Option(False, "--history", help="Show query history"),
    backend: Optional[str] = typer.Option(None, "--backend", help="AI backend (openai or anthropic)"),
    model: Optional[str] = typer.Option(None, "--model", help="AI model to use"),
    clear_history: bool = typer.Option(False, "--clear-history", help="Clear query history"),
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
):
    """Dav - An intelligent, context-aware AI assistant for the Linux terminal."""
    
    # Handle setup/update/uninstall commands first (these don't need configuration)
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
    
    if history:
        from dav.history import HistoryManager
        history_manager = HistoryManager()
        queries = history_manager.get_recent_queries(limit=20)
        if queries:
            console.print("\n[bold]Recent Queries:[/bold]\n")
            for q in queries:
                timestamp = q.get("timestamp", "unknown")
                query_text = q.get("query", "")[:80]
                console.print(f"  [{timestamp}] {query_text}")
        else:
            console.print("No history found.")
        return
    
    if clear_history:
        from dav.history import HistoryManager
        history_manager = HistoryManager()
        history_manager.clear_history()
        console.print("History cleared.")
        return
    
    # Handle automation-related commands
    if cron_setup:
        from dav.cron_helper import show_cron_examples
        from dav.sudo_handler import SudoHandler
        from rich.prompt import Confirm
        
        console.print("\n[bold]Cron Setup Guide[/bold]\n")
        console.print(show_cron_examples())
        
        # Check sudoers status
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
                
                # Ask for security preference
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
    
    # Detect automation mode early (before reading stdin)
    is_automation_mode = automation
    if not is_automation_mode and not sys.stdin.isatty() and not sys.stdout.isatty():
        # Auto-detect non-TTY environment (both stdin and stdout are not TTY)
        # This distinguishes true automation (cron/scripts) from piped input (user present)
        is_automation_mode = True
        console.print("[yellow]Auto-detected automation mode (non-TTY)[/yellow]")
    
    # Check for stdin input (for piped commands like: echo "test" | dav)
    stdin_content = None
    if not query:
        try:
            if not sys.stdin.isatty():
                stdin_content = sys.stdin.read()
        except Exception:
            pass
        
        if stdin_content:
            query = "analyze this"
    
    # Check if setup is needed BEFORE trying to use the AI backend
    # This ensures setup runs automatically on first use, regardless of how the tool is invoked
    if _auto_setup_if_needed():
        # Setup was just completed - reload config and continue
        # Re-import config to reload environment variables
        import importlib
        from dav import config
        importlib.reload(config)
    
    # Only import heavy AI/execution modules when actually needed
    from dav.ai_backend import AIBackend
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.context import build_context, format_context_for_prompt
    from dav.executor import COMMAND_EXECUTION_MARKER, execute_commands_from_response
    from dav.history import HistoryManager
    from dav.session import SessionManager
    from dav.terminal import (
        render_error,
        render_info,
        render_streaming_response_with_loading,
        render_warning,
    )
    
    # Try to initialize AI backend - this will fail if no API keys are configured
    # But we've already run setup above if needed, so this should work now
    try:
        ai_backend = AIBackend(backend=backend, model=model)
    except ValueError as e:
        error_msg = str(e)
        render_error(error_msg)
        if "API key not found" in error_msg:
            console.print("\n[yellow]Tip:[/yellow] Run [cyan]dav --setup[/cyan] to configure your API keys.")
        sys.exit(1)
    
    history_manager = HistoryManager()
    session_manager = SessionManager(session_id=session)
    
    # Initialize automation logger if in automation mode
    automation_logger = None
    if is_automation_mode:
        from dav.automation import AutomationLogger
        automation_logger = AutomationLogger()
        if query:
            automation_logger.set_task(query)
        # Auto-enable execute mode in automation
        execute = True
        auto_confirm = True
        
        # In automation mode, require a query (can't use interactive mode)
        if not query:
            render_error("Automation mode requires a query. Use 'dav --automation \"your task\"'")
            if automation_logger:
                automation_logger.log_error("Automation mode requires a query")
                automation_logger.close()
            sys.exit(1)
    
    # If no query provided and not in interactive mode, default to interactive execute mode
    if not query and not interactive:
        interactive = True
        execute = True  # Default to execute mode for easier access to main functionality
    
    if interactive:
        # In automation mode, don't use interactive mode (they're mutually exclusive)
        if is_automation_mode:
            render_warning("Automation mode and interactive mode are mutually exclusive. Using automation mode.")
        else:
            run_interactive_mode(ai_backend, history_manager, session_manager, execute, auto_confirm)
            return
    
    if not query:
        render_error("No query provided. Use 'dav \"your question\"' or 'dav -i' for interactive mode.")
        sys.exit(1)
    
    # Validate and sanitize user input
    from dav.input_validator import (
        sanitize_user_input,
        detect_prompt_injection,
        validate_query_length,
    )
    from dav.rate_limiter import check_api_rate_limit
    
    # Check rate limit
    is_allowed, rate_limit_error = check_api_rate_limit()
    if not is_allowed:
        render_error(rate_limit_error or "Rate limit exceeded")
        sys.exit(1)
    
    # Validate query length
    is_valid, length_error = validate_query_length(query)
    if not is_valid:
        render_error(length_error or "Query validation failed")
        sys.exit(1)
    
    # Sanitize user input
    query = sanitize_user_input(query)
    
    # Check for prompt injection
    is_injection, injection_reason = detect_prompt_injection(query)
    if is_injection:
        render_warning(f"Potential prompt injection detected: {injection_reason}")
        render_warning("This query may be blocked or modified for security.")
        # Continue but log the warning
    
    context_data, full_prompt, system_prompt = _build_prompt_with_context(
        query,
        session_manager,
        stdin_content=stdin_content,
        execute_mode=execute,
        interactive_mode=False,
        automation_mode=is_automation_mode,
    )
    
    try:
        backend_name = ai_backend.backend.title()
        response = render_streaming_response_with_loading(
            ai_backend.stream_response(full_prompt, system_prompt=system_prompt),
                loading_message=f"Generating response with {backend_name}...",
        )
        
        # Validate AI response
        from dav.input_validator import validate_ai_response
        is_valid_response, validation_error = validate_ai_response(response)
        if not is_valid_response:
            render_error(f"AI response validation failed: {validation_error}")
            if automation_logger:
                automation_logger.log_error(f"Response validation failed: {validation_error}")
            sys.exit(1)
        
        # Record AI response for summary
        if automation_logger:
            automation_logger.record_ai_response(response)

        _process_response(
            response,
            query,
            ai_backend,
            history_manager,
            session_manager,
            execute,
            auto_confirm,
            context_data,
            is_interactive=False,
            automation_mode=is_automation_mode,
            automation_logger=automation_logger,
        )
        
        # Close logger (summary is logged in feedback loop if commands were executed)
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
) -> Tuple[Dict, str, str]:
    """
    Build prompt with context and session history.
    
    Args:
        query: User query
        session_manager: Session manager instance
        stdin_content: Optional stdin content
        execute_mode: Whether in execute mode (affects system prompt)
        interactive_mode: Whether in interactive mode (affects system prompt)
    
    Returns:
        Tuple of (context_dict, context_string, system_prompt)
    """
    # Import here to avoid loading heavy modules for fast commands
    from dav.context import build_context, format_context_for_prompt
    from dav.ai_backend import get_system_prompt
    
    context = build_context(query=query, stdin_content=stdin_content)
    context_str = format_context_for_prompt(context)
    
    session_context = session_manager.get_conversation_context()
    if session_context:
        context_str = session_context + "\n" + context_str
    
    system_prompt = get_system_prompt(execute_mode=execute_mode, interactive_mode=interactive_mode, automation_mode=automation_mode)
    
    return context, context_str, system_prompt


def _process_response(
    response: str,
    query: str,
    ai_backend: AIBackend,
    history_manager: HistoryManager,
    session_manager: SessionManager,
    execute: bool,
    auto_confirm: bool,
    context_data: Optional[Dict],
    is_interactive: bool = False,
    automation_mode: bool = False,
    automation_logger: Optional[Any] = None,
) -> None:
    """
    Process and save response, optionally execute commands.
    
    Args:
        response: AI response text
        query: User query
        ai_backend: AI backend instance
        history_manager: History manager instance
        session_manager: Session manager instance
        execute: Whether to execute commands
        auto_confirm: Whether to auto-confirm execution
        context_data: Context data dictionary
        is_interactive: Whether in interactive mode (affects execution result storage)
    """
    # Import here to avoid loading heavy modules for fast commands
    from dav.config import get_execute_permission
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.executor import COMMAND_EXECUTION_MARKER, execute_commands_from_response
    from dav.terminal import render_warning
    
    history_manager.add_query(
        query=query,
        response=response,
        session_id=session_manager.session_id,
        executed=execute
    )
    
    session_manager.add_message("user", query)
    session_manager.add_message("assistant", response)
    
    should_execute = execute or get_execute_permission()
    if should_execute:
        has_marker = COMMAND_EXECUTION_MARKER in response
        
        if has_marker:
            # Use feedback loop for conditional execution
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
            
            # Execution results are logged in the feedback loop
            pass
        else:
            # No commands to execute, just save response
            pass


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
            # Sanitize and truncate output before feeding back to AI
            stdout = sanitize_command_output(result.stdout)
            # Truncate very long output (keep first 2000 chars and last 500 chars)
            if len(stdout) > 3000:
                stdout = stdout[:2000] + "\n[... truncated ...]\n" + stdout[-500:]
            lines.append("**Output:**")
            lines.append("```")
            lines.append(stdout)
            lines.append("```")
            lines.append("")
        
        if result.stderr:
            # Sanitize error output
            stderr = sanitize_command_output(result.stderr)
            # Truncate very long error output
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
    
    # Check if execution marker is present (means more commands coming)
    if COMMAND_EXECUTION_MARKER in response:
        return False
    
    # Check for completion phrases (case insensitive)
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
    ai_backend: AIBackend,
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
    # Import here to avoid loading heavy modules for fast commands
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.executor import COMMAND_EXECUTION_MARKER, execute_commands_from_response
    from dav.terminal import render_error, render_info, render_streaming_response_with_loading, render_warning
    
    # Extract command plan if available (preferred over heuristic extraction)
    plan = None
    try:
        plan = extract_command_plan(initial_response)
    except CommandPlanError:
        pass  # Will fall back to heuristic parsing
    
    # Initialize execution results list
    execution_results: List = []
    
    # Execute initial commands
    console.print()
    render_info("[bold cyan]Step 1:[/bold cyan] Executing initial commands...")
    console.print()
    
    # Step 1 is tracked in the summary report
    
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
    
    # Store initial results in session
    session_manager.add_execution_results(execution_results)
    
    # Feedback loop
    max_iterations = 10  # Safety limit to prevent infinite loops
    iteration = 1
    
    while iteration < max_iterations:
        iteration += 1
        
        # Format execution results for AI
        feedback_prompt = _format_execution_feedback(execution_results, query)
        
        # Get AI's analysis and next steps
        console.print()
        render_info(f"[bold cyan]Step {iteration}:[/bold cyan] Analyzing results and determining next steps...")
        console.print()
        
        # Build prompt with session context
        from dav.ai_backend import get_system_prompt
        
        # Get current session context (includes all previous messages and execution results)
        session_context = session_manager.get_conversation_context()
        
        # Combine session context with feedback prompt
        # The feedback prompt provides the most recent execution results in a clear format
        full_feedback_prompt = ""
        if session_context:
            full_feedback_prompt = session_context + "\n\n" + feedback_prompt
        else:
            full_feedback_prompt = feedback_prompt
        
        # Get system prompt
        system_prompt = get_system_prompt(execute_mode=True, interactive_mode=is_interactive)
        
        # Get AI's response
        backend_name = ai_backend.backend.title()
        followup_response = render_streaming_response_with_loading(
            ai_backend.stream_response(full_feedback_prompt, system_prompt=system_prompt),
            loading_message=f"Analyzing with {backend_name}...",
        )
        console.print()
        
        # Store AI's response in session
        session_manager.add_message("assistant", followup_response)
        
        # Check if task is complete
        if _is_task_complete(followup_response):
            render_info("[bold green]✓ Task complete![/bold green]")
            console.print()
            break
        
        # Check if AI provided more commands
        if COMMAND_EXECUTION_MARKER not in followup_response:
            # AI didn't provide commands but also didn't say complete
            # This might be an analysis-only response, check again
            render_info("AI provided analysis but no commands. Checking if task is complete...")
            # Re-check with a more lenient check
            if "complete" in followup_response.lower() or "done" in followup_response.lower():
                render_info("[bold green]✓ Task complete![/bold green]")
                console.print()
                break
            else:
                render_warning("AI response unclear. Assuming task needs more steps.")
                # Continue loop to see if AI provides commands in next iteration
                continue
        
        # Execute next commands
        render_info(f"[bold cyan]Step {iteration} (continued):[/bold cyan] Executing follow-up commands...")
        console.print()
        
        # Step tracking is done in the summary report
        
        # Extract command plan if available
        plan = None
        try:
            plan = extract_command_plan(followup_response)
        except CommandPlanError:
            pass  # Will fall back to heuristic parsing
        
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
        
        # Store results in session
        session_manager.add_execution_results(step_results)
    
    if iteration >= max_iterations:
        render_error(f"Reached maximum iteration limit ({max_iterations}). Stopping feedback loop.")
        console.print()
        render_warning("If the task is not complete, you may need to continue manually.")
        if automation_logger:
            automation_logger.log_warning(f"Reached maximum iteration limit ({max_iterations})")
    
    # Log final summary if in automation mode (only once at the end)
    if automation_logger and execution_results:
        task_status = "Task (incomplete)" if iteration >= max_iterations else "Task completed"
        automation_logger.log_summary(f"{task_status}: {query}", execution_results)
    
    return execution_results


def run_interactive_mode(ai_backend: AIBackend, history_manager: HistoryManager,
                        session_manager: SessionManager, execute: bool, auto_confirm: bool):
    """Run interactive mode for multi-turn conversations."""
    # Import here to avoid loading heavy modules for fast commands
    from dav.terminal import render_error, render_streaming_response_with_loading, render_context_status, render_warning, render_dav_banner
    from dav.context_tracker import ContextTracker
    from dav.context import format_context_for_prompt, build_context
    
    # Initialize context tracker
    context_tracker = ContextTracker(backend=ai_backend.backend, model=ai_backend.model)
    
    # Display ASCII art banner
    render_dav_banner()
    
    console.print("[bold green]Dav Interactive Mode[/bold green]")
    console.print("Type 'exit' or 'quit' to exit, 'clear' to clear session\n")
    
    # Helper function to display context and prompt
    def display_prompt_with_context():
        """Display context status panel and prompt."""
        # Calculate current context usage (no query yet)
        context_data = build_context(query=None)
        system_context_str = format_context_for_prompt(context_data)
        session_history_str = session_manager.get_conversation_context()
        usage = context_tracker.calculate_usage(
            system_context=system_context_str,
            session_history=session_history_str,
            current_query=""  # No query when showing prompt
        )
        # Pass model and backend for panel display
        render_context_status(usage, model=ai_backend.model, backend=ai_backend.backend)
        return input("dav> ").strip()
    
    while True:
        try:
            # Get user input with context display
            query = display_prompt_with_context()
            
            if not query:
                continue
            
            if query.lower() in ("exit", "quit", "q"):
                break
            
            if query.lower() == "clear":
                session_manager.clear_session()
                console.print("Session cleared.\n")
                continue
            
            # Validate and sanitize user input in interactive mode
            from dav.input_validator import (
                sanitize_user_input,
                detect_prompt_injection,
                validate_query_length,
            )
            from dav.rate_limiter import check_api_rate_limit
            
            # Check rate limit
            is_allowed, rate_limit_error = check_api_rate_limit()
            if not is_allowed:
                render_warning(rate_limit_error or "Rate limit exceeded. Please wait.")
                continue
            
            # Validate query length
            is_valid, length_error = validate_query_length(query)
            if not is_valid:
                render_error(length_error or "Query validation failed")
                continue
            
            # Sanitize user input
            query = sanitize_user_input(query)
            
            # Check for prompt injection
            is_injection, injection_reason = detect_prompt_injection(query)
            if is_injection:
                render_warning(f"Potential prompt injection detected: {injection_reason}")
                # Continue but warn user
            
            context_data, full_prompt, system_prompt = _build_prompt_with_context(
                query, session_manager, execute_mode=execute, interactive_mode=True
            )
            
            backend_name = ai_backend.backend.title()
            console.print()
            response = render_streaming_response_with_loading(
                ai_backend.stream_response(full_prompt, system_prompt=system_prompt),
                loading_message=f"Generating response with {backend_name}...",
            )
            console.print()
            
            _process_response(
                response,
                query,
                ai_backend,
                history_manager,
                session_manager,
                execute,
                auto_confirm,
                context_data,
                is_interactive=True,
            )
            
            # Context status will be shown again before next prompt
            console.print()
        
        except KeyboardInterrupt:
            console.print("\n\n[bold yellow]Interrupted. Type 'exit' to quit.[/bold yellow]\n")
        except EOFError:
            break
        except Exception as e:
            render_error(f"Error: {str(e)}")
    
    console.print("\n[bold]Goodbye![/bold]")


def _handle_schedule_command(schedule_input: str) -> None:
    """Handle --schedule command to set up cron jobs."""
    from dav.ai_backend import AIBackend
    from dav.cron_helper import add_cron_job
    from dav.schedule_parser import parse_schedule
    from dav.terminal import render_error, render_warning
    
    console.print("[cyan]Parsing schedule and setting up cron job...[/cyan]\n")
    
    # Check if setup is needed
    if _auto_setup_if_needed():
        import importlib
        from dav import config
        importlib.reload(config)
    
    # Initialize AI backend (may fail, but that's okay - we have fallbacks)
    ai_backend = None
    try:
        ai_backend = AIBackend()
    except ValueError as e:
        # AI backend not available, but we can still try dateparser and regex
        console.print("[dim]AI backend not available, using fallback parsers...[/dim]\n")
    
    # Parse schedule using hybrid parser
    result = parse_schedule(schedule_input, ai_backend=ai_backend)
    
    if not result.success:
        render_error("Could not parse schedule")
        if result.error:
            # Print the detailed error message (may contain multiple lines)
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
    
    # Show which method succeeded
    method_names = {
        "ai": "AI parsing",
        "dateparser": "dateparser library",
        "regex": "pattern matching"
    }
    method_name = method_names.get(result.method, "unknown method")
    console.print(f"[dim]Parsed using: {method_name}[/dim]\n")
    
    # Check if NOPASSWD is configured before scheduling
    # This is important because scheduled tasks in automation mode will fail
    # if they require sudo and password-less sudo is not available
    from dav.sudo_handler import SudoHandler
    from rich.prompt import Confirm
    
    sudo_handler = SudoHandler()
    is_configured, status_msg = sudo_handler.check_sudoers_setup()
    
    # Check if task might require sudo (common keywords)
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
            
            # Ask for security preference
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
        # NOPASSWD not configured but task probably doesn't need sudo
        # Just show a brief warning
        console.print()
        render_warning("Password-less sudo is not configured.")
        console.print("[dim]If this task requires sudo, it will fail. Run 'dav --cron-setup' to configure.[/dim]")
        console.print()
    
    # Add cron job
    success, message, match_type, existing_entry = add_cron_job(cron_schedule, task, auto_confirm=True)
    
    if success:
        console.print(f"[green]✓ {message}[/green]")
        console.print(f"\n[cyan]Cron job added successfully![/cyan]")
        console.print(f"[dim]View with: crontab -l[/dim]")
        
        # Final reminder if NOPASSWD not configured and task might need sudo
        if not is_configured and might_need_sudo:
            console.print()
            render_warning("Remember: Configure password-less sudo with 'dav --cron-setup' if this task requires sudo.")
    else:
        # Handle different duplicate match types
        if match_type == "exact" or match_type == "task_and_schedule":
            # Exact or task+schedule duplicate - just inform user
            render_error(message)
            if existing_entry:
                console.print(f"\n[dim]Existing entry: {existing_entry}[/dim]")
            console.print("\n[yellow]Tip:[/yellow] Use 'crontab -e' to manually edit or remove the existing job.")
            sys.exit(1)
        
        elif match_type == "task_only":
            # Task exists with different schedule - prompt user for action
            from dav.cron_helper import find_similar_cron_jobs, replace_cron_job
            
            console.print()
            render_warning("A similar task is already scheduled with a different time.")
            console.print()
            
            # Find all similar jobs
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
                # Replace
                if not similar_jobs:
                    # Fallback to existing_entry if similar_jobs is empty
                    if existing_entry:
                        old_entry = existing_entry
                    else:
                        render_error("Could not find existing entry to replace.")
                        sys.exit(1)
                else:
                    # If multiple similar jobs, replace the first one (or could prompt which one)
                    # For now, replace the first one found
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
                # Add anyway - proceed with adding the new job
                # We need to bypass the duplicate check, so we'll add it directly
                from dav.cron_helper import detect_dav_path, get_current_crontab, _write_crontab
                
                dav_path = detect_dav_path()
                new_cron_entry = f'{cron_schedule} {dav_path} --automation "{task}"'
                
                current_crontab = get_current_crontab()
                new_crontab = current_crontab + [new_cron_entry]
                
                # Write crontab using helper function
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
            # Other error (not a duplicate)
            render_error(message)
            sys.exit(1)


if __name__ == "__main__":
    app()

