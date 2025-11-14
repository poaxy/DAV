"""Main CLI interface for Dav."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

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
    from dav.ai_backend import AIBackend, get_system_prompt
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
        show_loading_status,
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
    
    if interactive:
        run_interactive_mode(ai_backend, history_manager, session_manager, execute, auto_confirm)
        return
    
    if not query:
        render_error("No query provided. Use 'dav \"your question\"' or 'dav -i' for interactive mode.")
        sys.exit(1)
    
    context_data, full_prompt, system_prompt = _build_prompt_with_context(
        query,
        session_manager,
        stdin_content=stdin_content,
        execute_mode=execute,
        interactive_mode=False,
    )
    
    try:
        backend_name = ai_backend.backend.title()
        response = render_streaming_response_with_loading(
            ai_backend.stream_response(full_prompt, system_prompt=system_prompt),
                loading_message=f"Generating response with {backend_name}...",
        )

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
        )

    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Interrupted by user[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        render_error(f"Error: {str(e)}")
        sys.exit(1)


def _build_prompt_with_context(
    query: str,
    session_manager: SessionManager,
    stdin_content: Optional[str] = None,
    execute_mode: bool = False,
    interactive_mode: bool = False,
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
    from dav.terminal import show_loading_status
    
    with show_loading_status("Building context..."):
        context = build_context(query=query, stdin_content=stdin_content)
        context_str = format_context_for_prompt(context)
        
        session_context = session_manager.get_conversation_context()
        if session_context:
            context_str = session_context + "\n" + context_str
        
        system_prompt = get_system_prompt(execute_mode=execute_mode, interactive_mode=interactive_mode)
    
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
            _execute_with_feedback_loop(
                initial_response=response,
                query=query,
                ai_backend=ai_backend,
                session_manager=session_manager,
                context_data=context_data,
                confirm=confirm,
                auto_confirm=auto_confirm,
                is_interactive=is_interactive,
            )
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
            # Truncate very long output (keep first 2000 chars and last 500 chars)
            stdout = result.stdout
            if len(stdout) > 3000:
                stdout = stdout[:2000] + "\n[... truncated ...]\n" + stdout[-500:]
            lines.append("**Output:**")
            lines.append("```")
            lines.append(stdout)
            lines.append("```")
            lines.append("")
        
        if result.stderr:
            # Truncate very long error output
            stderr = result.stderr
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
) -> None:
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
    
    # Execute initial commands
    console.print()
    render_info("[bold cyan]Step 1:[/bold cyan] Executing initial commands...")
    console.print()
    
    execution_results = execute_commands_from_response(
        initial_response,
        confirm=confirm,
        context=context_data,
        plan=plan,
    )
    
    if not execution_results:
        render_warning("No commands were executed. Task may already be complete.")
        return
    
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
        
        # Extract command plan if available
        plan = None
        try:
            plan = extract_command_plan(followup_response)
        except CommandPlanError:
            pass  # Will fall back to heuristic parsing
        
        execution_results = execute_commands_from_response(
            followup_response,
            confirm=confirm,
            context=context_data,
            plan=plan,
        )
        
        if not execution_results:
            render_warning("No commands found in AI response. Task may be complete.")
            break
        
        # Store results in session
        session_manager.add_execution_results(execution_results)
    
    if iteration >= max_iterations:
        render_error(f"Reached maximum iteration limit ({max_iterations}). Stopping feedback loop.")
        console.print()
        render_warning("If the task is not complete, you may need to continue manually.")


def run_interactive_mode(ai_backend: AIBackend, history_manager: HistoryManager,
                        session_manager: SessionManager, execute: bool, auto_confirm: bool):
    """Run interactive mode for multi-turn conversations."""
    # Import here to avoid loading heavy modules for fast commands
    from dav.terminal import render_error, render_streaming_response_with_loading
    
    console.print("[bold green]Dav Interactive Mode[/bold green]")
    console.print("Type 'exit' or 'quit' to exit, 'clear' to clear session\n")
    
    while True:
        try:
            # Get user input
            query = input("dav> ").strip()
            
            if not query:
                continue
            
            if query.lower() in ("exit", "quit", "q"):
                break
            
            if query.lower() == "clear":
                session_manager.clear_session()
                console.print("Session cleared.\n")
                continue
            
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
        
        except KeyboardInterrupt:
            console.print("\n\n[bold yellow]Interrupted. Type 'exit' to quit.[/bold yellow]\n")
        except EOFError:
            break
        except Exception as e:
            render_error(f"Error: {str(e)}")
    
    console.print("\n[bold]Goodbye![/bold]")


if __name__ == "__main__":
    app()

