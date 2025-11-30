"""Terminal formatting and rendering for Dav."""

import re
import sys
import threading
import time
from typing import Any, ContextManager, Iterator, Optional, Tuple

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.box import ROUNDED
from rich.status import Status
from rich.syntax import Syntax
from rich.text import Text

console = Console()

# Constants
RAINBOW_COLORS = ["red", "yellow", "green", "cyan", "blue", "magenta"]
STREAM_UPDATE_THRESHOLD = 20  # Only update every N characters to reduce flashing
SPINNER_UPDATE_INTERVAL = 0.1  # Seconds between spinner frame updates

# Pattern to match JSON command plan blocks (for filtering from display)
# Matches ```json ... ``` blocks that contain JSON objects
JSON_COMMAND_PLAN_PATTERN = re.compile(
    r"```json\s*\{.*?\}\s*```",  # Match ```json { ... } ``` blocks
    re.DOTALL | re.IGNORECASE
)


def strip_json_command_plan(text: str) -> str:
    """Remove JSON command plan blocks from response text for display purposes.
    
    The JSON command plan is used internally for command extraction but should
    not be shown to users as it's not helpful.
    
    Args:
        text: Response text that may contain JSON command plan blocks
        
    Returns:
        Text with JSON command plan blocks removed
    """
    # Remove JSON command plan blocks
    cleaned = JSON_COMMAND_PLAN_PATTERN.sub("", text)
    
    # Clean up any extra whitespace/newlines left behind
    # Remove 3+ consecutive newlines (likely from removed JSON blocks)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    
    # Remove trailing whitespace
    cleaned = cleaned.rstrip()
    
    return cleaned


def render_error(message: str) -> None:
    """Render error message."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def render_warning(message: str) -> None:
    """Render warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def render_info(message: str) -> None:
    """Render info message."""
    console.print(f"[bold blue]Info:[/bold blue] {message}")


def _get_shortened_model_name(model: str, backend: str) -> str:
    """
    Get shortened model name for display.
    
    Args:
        model: Full model name
        backend: Backend name (openai or anthropic)
    
    Returns:
        Shortened model name
    """
    model_lower = model.lower()
    
    if backend == "openai":
        if "gpt-4" in model_lower:
            if "turbo" in model_lower:
                return "gpt-4-turbo"
            return "gpt-4"
        elif "gpt-3.5" in model_lower:
            return "gpt-3.5"
        return "gpt"
    elif backend == "anthropic":
        if "claude-3.5" in model_lower:
            return "claude-3.5"
        elif "claude-3" in model_lower:
            return "claude-3"
        elif "claude" in model_lower:
            return "claude"
    
    # Fallback: return first 10 chars
    return model[:10] if len(model) > 10 else model


def _get_rate_limit_info() -> tuple[str, str, int, int]:
    """
    Get rate limiting information for display.
    
    Returns:
        Tuple of (formatted_string, color, remaining, total)
    """
    from dav.rate_limiter import api_rate_limiter
    
    # Get remaining tokens and capacity
    remaining_tokens = api_rate_limiter.get_remaining_tokens()
    capacity = api_rate_limiter.capacity
    
    # The rate limiter uses tokens, where each request costs 1 token
    # So remaining tokens = remaining requests
    remaining_requests = max(0, int(remaining_tokens))
    total_requests = int(capacity)
    
    # Determine color based on remaining percentage
    remaining_pct = (remaining_requests / total_requests * 100) if total_requests > 0 else 100
    
    if remaining_pct > 70:
        color = "green"
    elif remaining_pct > 30:
        color = "yellow"
    else:
        color = "red"
    
    formatted = f"rate: {remaining_requests}/{total_requests}"
    
    return formatted, color, remaining_requests, total_requests


def render_context_status_panel(usage, model: str, backend: str) -> None:
    """
    Render context usage status in a colored border panel.
    
    Args:
        usage: ContextUsage object from context_tracker
        model: Model name
        backend: Backend name
    """
    from dav.context_tracker import ContextUsage
    
    if not isinstance(usage, ContextUsage):
        return
    
    # Format token counts (show in K with 1 decimal)
    used_k = usage.total_used / 1000
    max_k = usage.max_tokens / 1000
    
    # Determine color based on usage percentage (for border)
    if usage.usage_percentage < 50:
        border_color = "green"
        context_color = "green"
        accent_color = "bright_green"
    elif usage.usage_percentage < 80:
        border_color = "yellow"
        context_color = "yellow"
        accent_color = "bright_yellow"
    else:
        border_color = "red"
        context_color = "red"
        accent_color = "bright_red"
    
    # Get model info
    model_short = _get_shortened_model_name(model, backend)
    
    # Get rate limit info
    rate_text, rate_color, rate_remaining, rate_total = _get_rate_limit_info()
    
    # Build panel content
    # Format: [green]context: 4.2K/128.0K (3.3%)[/green] | [cyan]model: gpt-4[/cyan] | [yellow]rate: 7/10[/yellow]
    content = (
        f"[{context_color}]context: {used_k:.1f}K/{max_k:.1f}K ({usage.usage_percentage:.1f}%)[/{context_color}] "
        f"[dim]│[/dim] "
        f"[cyan]model: {model_short}[/cyan] "
        f"[dim]│[/dim] "
        f"[{rate_color}]{rate_text}[/{rate_color}]"
    )
    
    # Create panel with colored border
    panel = Panel(
        content,
        border_style=border_color,
        box=ROUNDED,
        padding=(0, 1),
    )
    
    console.print(panel)


def render_context_status(usage, model: Optional[str] = None, backend: Optional[str] = None) -> None:
    """
    Render context usage status in a colored border panel.
    
    Args:
        usage: ContextUsage object from context_tracker
        model: Model name (optional, for panel display)
        backend: Backend name (optional, for panel display)
    """
    if model and backend:
        render_context_status_panel(usage, model, backend)
    else:
        # Fallback to simple line if model/backend not provided
        from dav.context_tracker import ContextUsage
        if isinstance(usage, ContextUsage):
            used_k = usage.total_used / 1000
            max_k = usage.max_tokens / 1000
            if usage.usage_percentage < 50:
                color = "green"
            elif usage.usage_percentage < 80:
                color = "yellow"
            else:
                color = "red"
            status_line = (
                f"[{color}]context: {used_k:.1f}K/{max_k:.1f}K ({usage.usage_percentage:.1f}%)[/{color}]"
            )
            console.print(status_line)


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
        # Render first chunk immediately (filter JSON for display)
        display_text = strip_json_command_plan(accumulated)
        if show_markdown:
            try:
                markdown = Markdown(display_text)
                live.update(markdown)
            except Exception:
                live.update(Text(display_text))
        else:
            live.update(Text(display_text))
        
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
                        # Filter JSON for display but keep original for return
                        display_text = strip_json_command_plan(accumulated)
                        if show_markdown:
                            markdown = Markdown(display_text)
                            live.update(markdown)
                        else:
                            live.update(Text(display_text))
                        last_update_length = len(accumulated)
                    except Exception:
                        # If markdown parsing fails, just show text
                        display_text = strip_json_command_plan(accumulated)
                        live.update(Text(display_text))
                        last_update_length = len(accumulated)
        except Exception as e:
            live.update(Text(f"[bold red]Error: {str(e)}[/bold red]"))
            return ""
    
    # Return original (unfiltered) for command extraction, but display was filtered
    return accumulated

