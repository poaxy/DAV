"""Main CLI interface for Dav."""

import sys
from typing import Optional
import typer
from rich.console import Console

from dav.context import build_context, format_context_for_prompt
from dav.ai_backend import AIBackend, get_system_prompt
from dav.terminal import (
    render_streaming_response,
    render_streaming_response_with_loading,
    render_response,
    render_error,
    render_info,
    render_warning,
    show_loading_status,
)
from dav.history import HistoryManager
from dav.session import SessionManager
from dav.executor import execute_commands_from_response
from dav.config import get_default_backend, get_execute_permission

app = typer.Typer(help="Dav - An intelligent, context-aware AI assistant for the Linux terminal")
console = Console()


@app.command()
def main(
    query: Optional[str] = typer.Argument(None, help="Natural language query"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="Interactive mode for multi-turn conversations"),
    session: Optional[str] = typer.Option(None, "--session", help="Session ID to maintain context"),
    execute: bool = typer.Option(False, "--execute", help="Execute commands found in response (with confirmation)"),
    history: bool = typer.Option(False, "--history", help="Show query history"),
    backend: Optional[str] = typer.Option(None, "--backend", help="AI backend (openai or anthropic)"),
    model: Optional[str] = typer.Option(None, "--model", help="AI model to use"),
    clear_history: bool = typer.Option(False, "--clear-history", help="Clear query history"),
):
    """Dav - An intelligent, context-aware AI assistant for the Linux terminal."""
    
    # Handle history commands
    if history:
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
        history_manager = HistoryManager()
        history_manager.clear_history()
        console.print("History cleared.")
        return
    
    # Initialize components
    try:
        ai_backend = AIBackend(backend=backend, model=model)
    except ValueError as e:
        render_error(str(e))
        sys.exit(1)
    
    history_manager = HistoryManager()
    session_manager = SessionManager(session_id=session)
    
    # Interactive mode
    if interactive:
        run_interactive_mode(ai_backend, history_manager, session_manager, execute)
        return
    
    # Single query mode
    stdin_content = None
    if not query:
        # Check for piped input
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
    
    # Build context and prompt
    with show_loading_status("Building context..."):
        context = build_context(query=query, stdin_content=stdin_content)
        context_str = format_context_for_prompt(context)
        
        # Add session context if available
        session_context = session_manager.get_conversation_context()
        if session_context:
            context_str = session_context + "\n" + context_str
        
        # Build full prompt
        full_prompt = context_str
        
        # Get system prompt
        system_prompt = get_system_prompt()
    
    # Stream response with loading indicator
    try:
        backend_name = ai_backend.backend.title()
        response = render_streaming_response_with_loading(
            ai_backend.stream_response(full_prompt, system_prompt=system_prompt),
            loading_message=f"Connecting to {backend_name}...",
        )
        
        # Save to history
        history_manager.add_query(
            query=query,
            response=response,
            session_id=session_manager.session_id,
            executed=execute
        )
        
        # Save to session
        session_manager.add_message("user", query)
        session_manager.add_message("assistant", response)
        
        # Execute commands if requested
        if execute:
            execute_commands_from_response(response, confirm=True)
        elif get_execute_permission():
            # Auto-execute if permission is enabled (still with confirmation)
            execute_commands_from_response(response, confirm=True)
    
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Interrupted by user[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        render_error(f"Error: {str(e)}")
        sys.exit(1)


def run_interactive_mode(ai_backend: AIBackend, history_manager: HistoryManager, 
                        session_manager: SessionManager, execute: bool):
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
            
            # Build context
            with show_loading_status("Building context..."):
                context = build_context(query=query)
                context_str = format_context_for_prompt(context)
                
                # Add session context
                session_context = session_manager.get_conversation_context()
                if session_context:
                    context_str = session_context + "\n" + context_str
                
                # Get system prompt
                system_prompt = get_system_prompt()
            
            # Stream response with loading indicator
            backend_name = ai_backend.backend.title()
            console.print()  # Empty line
            response = render_streaming_response_with_loading(
                ai_backend.stream_response(context_str, system_prompt=system_prompt),
                loading_message=f"Connecting to {backend_name}...",
            )
            console.print()  # Empty line
            
            # Save to history
            history_manager.add_query(
                query=query,
                response=response,
                session_id=session_manager.session_id,
                executed=execute
            )
            
            # Save to session
            session_manager.add_message("user", query)
            session_manager.add_message("assistant", response)
            
            # Execute commands if requested
            if execute:
                execute_commands_from_response(response, confirm=True)
        
        except KeyboardInterrupt:
            console.print("\n\n[bold yellow]Interrupted. Type 'exit' to quit.[/bold yellow]\n")
        except EOFError:
            break
        except Exception as e:
            render_error(f"Error: {str(e)}")
    
    console.print("\n[bold]Goodbye![/bold]")


if __name__ == "__main__":
    app()

