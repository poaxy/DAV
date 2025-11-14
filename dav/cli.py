"""Main CLI interface for Dav."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Dict, Optional, Tuple

import typer
from rich.console import Console

# Type hints only - not imported at runtime
if TYPE_CHECKING:
    from dav.ai_backend import AIBackend
    from dav.history import HistoryManager
    from dav.session import SessionManager

# Lazy imports for heavy modules - only load when needed
# Fast commands (setup, update, uninstall, etc.) don't need these

app = typer.Typer(help="Dav - An intelligent, context-aware AI assistant for the Linux terminal")
console = Console()


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
    uninstall_data: bool = typer.Option(False, "--uninstall-data", help="Remove all Dav data files and directories"),
    list_data: bool = typer.Option(False, "--list-data", help="List all Dav data files and directories"),
    uninstall_info: bool = typer.Option(False, "--uninstall-info", help="Show uninstall instructions"),
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
    
    if uninstall_info:
        from dav.uninstall import show_uninstall_info
        show_uninstall_info()
        return
    
    if list_data:
        from dav.uninstall import list_dav_files
        list_dav_files()
        return
    
    if uninstall_data:
        from dav.uninstall import remove_dav_files
        remove_dav_files(confirm=True)
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
    
    # Only import heavy AI/execution modules when actually needed
    from dav.ai_backend import AIBackend, get_system_prompt
    from dav.command_plan import CommandPlanError, extract_command_plan
    from dav.config import get_default_backend, get_execute_permission
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
    
    stdin_content = None
    if not query:
        try:
            if not sys.stdin.isatty():
                stdin_content = sys.stdin.read()
        except Exception:
            pass
        
        if stdin_content:
            query = "analyze this"
        else:
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
        plan = None
        has_marker = COMMAND_EXECUTION_MARKER in response
        
        if has_marker:
            try:
                plan = extract_command_plan(response)
            except CommandPlanError as err:
                render_warning(f"Command plan missing or invalid: {err}. Falling back to heuristic parsing.")

        confirm = not auto_confirm
        execution_results = None
        if plan:
            execution_results = execute_commands_from_response(
                response,
                confirm=confirm,
                context=context_data,
                plan=plan,
            )
        else:
            execution_results = execute_commands_from_response(response, confirm=confirm, context=context_data)
        
        if is_interactive and execution_results:
            session_manager.add_execution_results(execution_results)


def run_interactive_mode(ai_backend: AIBackend, history_manager: HistoryManager,
                        session_manager: SessionManager, execute: bool, auto_confirm: bool):
    """Run interactive mode for multi-turn conversations."""
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

