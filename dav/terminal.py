"""Terminal formatting and rendering for Dav."""

import sys
import threading
import time
from typing import Any, ContextManager, Iterator, Optional, Tuple

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.syntax import Syntax
from rich.text import Text

console = Console()

# Constants
RAINBOW_COLORS = ["red", "yellow", "green", "cyan", "blue", "magenta"]
STREAM_UPDATE_THRESHOLD = 20  # Only update every N characters to reduce flashing
SPINNER_UPDATE_INTERVAL = 0.1  # Seconds between spinner frame updates


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
                console.print("[yellow]No TTY available for confirmation. Skipping execution (use --yes to auto-confirm).[/yellow]")
                return False
    except EOFError:
        console.print("[yellow]No input received. Skipping execution (use --yes to auto-confirm).[/yellow]")
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


class RainbowSpinner:
    """Custom spinner that cycles through rainbow colors."""
    
    def __init__(self, frames: Optional[list] = None):
        if frames is None:
            # Default spinner frames
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.frames = frames
        self.current_frame = 0
        self.current_color = 0
    
    def get_next(self) -> Tuple[str, str]:
        """
        Get next spinner frame and color.
        
        Returns:
            Tuple of (frame_character, color_name)
        """
        frame = self.frames[self.current_frame]
        color = RAINBOW_COLORS[self.current_color]
        
        # Advance to next frame and color
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        self.current_color = (self.current_color + 1) % len(RAINBOW_COLORS)
        
        return frame, color


def show_rainbow_loading(message: str = "Generating response...") -> ContextManager[Any]:
    """Show a rainbow-colored loading spinner with animated dots (no text)."""
    rainbow_spinner = RainbowSpinner()
    # Use a list to hold the current text content (mutable container for Live)
    current_text = [Text()]
    running = threading.Event()
    running.set()
    
    def update_spinner():
        """Update spinner in a loop."""
        while running.is_set():
            spinner_char, spinner_color = rainbow_spinner.get_next()
            # Create new Text object with just the spinner character (no message text)
            new_text = Text()
            new_text.append(spinner_char, style=spinner_color)
            current_text[0] = new_text  # Update the mutable container
            time.sleep(SPINNER_UPDATE_INTERVAL)
    
    # Start spinner update thread
    spinner_thread = threading.Thread(target=update_spinner, daemon=True)
    spinner_thread.start()
    
    # Use Live with a renderable that reads from the mutable container
    class RainbowRenderable:
        """Renderable that displays the current spinner text."""
        def __init__(self, text_container):
            self.text_container = text_container
        
        def __rich_console__(self, console, options):
            yield self.text_container[0]
    
    renderable = RainbowRenderable(current_text)
    
    # Use Live with the renderable
    class RainbowLiveContext:
        def __init__(self, renderable_obj, run_event, thread):
            self.renderable = renderable_obj
            self.running = run_event
            self.thread = thread
            self.live = None
        
        def __enter__(self):
            self.live = Live(self.renderable, console=console, refresh_per_second=10)
            self.live.__enter__()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.running.clear()
            if self.thread.is_alive():
                self.thread.join(timeout=0.2)
            if self.live:
                self.live.__exit__(exc_type, exc_val, exc_tb)
    
    return RainbowLiveContext(renderable, running, spinner_thread)


def render_streaming_response_with_loading(
    stream: Iterator[str], 
    loading_message: str = "Generating response...",
    show_markdown: bool = True
) -> str:
    """Render streaming AI response with rainbow loading indicator before first chunk."""
    accumulated = ""
    buffer = ""
    last_update_length = 0
    
    # Show rainbow loading spinner while waiting for first chunk
    # The spinner will automatically disappear when we exit the context manager
    with show_rainbow_loading(loading_message):
        try:
            # Try to get first chunk (this will block until data arrives)
            first_chunk = next(stream, None)
            if first_chunk is None:
                console.print("[bold red]No response received[/bold red]")
                return ""
            
            # We have content - spinner will disappear when context manager exits
            accumulated += first_chunk
            buffer += first_chunk
        
        except StopIteration:
            console.print("[bold red]No response received[/bold red]")
            return ""
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/bold red]")
            return ""
    
    # Spinner has now disappeared, continue with Live rendering
    
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
                    elif new_content_length >= STREAM_UPDATE_THRESHOLD:
                        # Update periodically to show progress
                        should_update = True
                else:
                    # For non-markdown, update more frequently but still throttled
                    if new_content_length >= STREAM_UPDATE_THRESHOLD:
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

