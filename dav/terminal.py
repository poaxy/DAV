"""Terminal formatting and rendering for Dav."""

import sys
from typing import Iterator, Optional, ContextManager
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.status import Status

console = Console()


def render_streaming_response(stream: Iterator[str], show_markdown: bool = True) -> str:
    """Render streaming AI response with markdown formatting."""
    accumulated = ""
    buffer = ""
    
    # Use Live for real-time updates
    with Live(console=console, refresh_per_second=10) as live:
        for chunk in stream:
            accumulated += chunk
            buffer += chunk
            
            # Try to render complete markdown blocks
            if show_markdown:
                try:
                    # Check if we have a complete code block or paragraph
                    if "```" in buffer or "\n\n" in buffer:
                        # Render accumulated content
                        markdown = Markdown(accumulated)
                        live.update(markdown)
                        buffer = ""
                except Exception:
                    # If markdown parsing fails, just show text
                    live.update(Text(accumulated))
            else:
                live.update(Text(accumulated))
    
    # Final render
    if show_markdown:
        try:
            console.print(Markdown(accumulated))
        except Exception:
            console.print(accumulated)
    else:
        console.print(accumulated)
    
    return accumulated


def render_response(response: str, show_markdown: bool = True) -> None:
    """Render complete AI response with markdown formatting."""
    if show_markdown:
        try:
            console.print(Markdown(response))
        except Exception:
            console.print(response)
    else:
        console.print(response)


def render_error(message: str) -> None:
    """Render error message."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def render_warning(message: str) -> None:
    """Render warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def render_info(message: str) -> None:
    """Render info message."""
    console.print(f"[bold blue]Info:[/bold blue] {message}")


def render_command(command: str) -> None:
    """Render command in a highlighted code block."""
    syntax = Syntax(command, "bash", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, border_style="cyan", title="Command"))


def confirm_action(message: str) -> bool:
    """Confirm an action with the user."""
    prompt = f"{message} (y/N): "
    response = ""

    try:
        if sys.stdin.isatty():
            response = input(prompt)
        else:
            # Attempt to prompt using /dev/tty when stdin is not interactive (e.g. piped input)
            try:
                with open("/dev/tty", "r+") as tty:
                    tty.write(prompt)
                    tty.flush()
                    response = tty.readline()
            except OSError:
                console.print("[yellow]No TTY available for confirmation. Skipping execution.[/yellow]")
                return False
    except EOFError:
        console.print("[yellow]No input received. Skipping execution.[/yellow]")
        return False

    response = response.strip().lower()
    return response in ("y", "yes")


def show_loading_status(message: str = "Processing...") -> ContextManager[Status]:
    """Show a loading status with spinner and message."""
    return Status(
        f"[bold cyan]{message}[/bold cyan]",
        spinner="dots",
        console=console,
        spinner_style="cyan",
    )


def render_streaming_response_with_loading(
    stream: Iterator[str], 
    loading_message: str = "Generating response...",
    show_markdown: bool = True
) -> str:
    """Render streaming AI response with loading indicator before first chunk."""
    accumulated = ""
    buffer = ""
    first_chunk_received = False
    last_update_length = 0
    update_threshold = 20  # Only update every N characters to reduce flashing
    
    # Show loading status while waiting for first chunk
    with show_loading_status(loading_message):
        try:
            # Try to get first chunk (this will block until data arrives)
            first_chunk = next(stream, None)
            if first_chunk is None:
                console.print("[bold red]No response received[/bold red]")
                return ""
            
            # We have content, now switch to Live rendering
            first_chunk_received = True
            accumulated += first_chunk
            buffer += first_chunk
        
        except StopIteration:
            console.print("[bold red]No response received[/bold red]")
            return ""
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/bold red]")
            return ""
    
    # Now render the rest with Live
    with Live(console=console, refresh_per_second=15, transient=False) as live:
        # Render first chunk immediately
        if show_markdown:
            try:
                markdown = Markdown(accumulated)
                live.update(markdown)
            except Exception:
                live.update(Text(accumulated))
        else:
            live.update(Text(accumulated))
        
        last_update_length = len(accumulated)
        
        # Continue with rest of stream
        try:
            for chunk in stream:
                accumulated += chunk
                buffer += chunk
                
                # Only update if we have enough new content or detect a complete block
                should_update = False
                new_content_length = len(accumulated) - last_update_length
                
                if show_markdown:
                    # Update on complete code blocks or paragraphs to reduce flashing
                    if "```" in buffer:
                        # Check if we have a complete code block (opening and closing)
                        code_blocks = buffer.count("```")
                        if code_blocks >= 2:
                            should_update = True
                            buffer = ""
                    elif "\n\n" in buffer:
                        # Update on paragraph breaks
                        should_update = True
                        buffer = ""
                    elif new_content_length >= update_threshold:
                        # Update periodically to show progress
                        should_update = True
                else:
                    # For non-markdown, update more frequently but still throttled
                    if new_content_length >= update_threshold:
                        should_update = True
                
                if should_update:
                    try:
                        if show_markdown:
                            markdown = Markdown(accumulated)
                            live.update(markdown)
                        else:
                            live.update(Text(accumulated))
                        last_update_length = len(accumulated)
                    except Exception:
                        # If markdown parsing fails, just show text
                        live.update(Text(accumulated))
                        last_update_length = len(accumulated)
        except Exception as e:
            live.update(Text(f"[bold red]Error: {str(e)}[/bold red]"))
            return ""
    
    # Final render (no need to re-render, Live already showed it)
    return accumulated

