"""Terminal formatting and rendering for Dav."""

import re
import sys
import threading
import time
import termios
import tty
from typing import Any, ContextManager, Iterator, Optional, Tuple

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.box import ROUNDED
from rich.status import Status
from rich.syntax import Syntax
from rich.text import Text
from rich.style import Style

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
    
    # Format rate limit display
    if remaining_requests == 0:
        # Show time until next token when at 0
        time_until = api_rate_limiter.get_time_until_next_token()
        if time_until > 0:
            # Round to nearest second
            seconds = int(time_until) + (1 if time_until % 1 >= 0.5 else 0)
            formatted = f"rate: {remaining_requests}/{total_requests} ({seconds}s)"
        else:
            formatted = f"rate: {remaining_requests}/{total_requests}"
    else:
        formatted = f"rate: {remaining_requests}/{total_requests}"
    
    return formatted, color, remaining_requests, total_requests


def format_interactive_prompt(mode: str = "interactive") -> Text:
    """Format the interactive mode prompt with mode, username and path.
    
    Args:
        mode: Current mode ("interactive" or "command")
    
    Returns:
        Rich Text object with formatted two-line prompt:
        Line 1: [MODE]-[USERNAME]-[PATH] (brackets: cyan, mode: purple, username: bright_red, path: blue)
        Line 2: [Dav]➜ (brackets: cyan, Dav: white, arrow: cyan)
    """
    import os
    from pathlib import Path
    
    # Get username
    try:
        import pwd
        username = pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        username = os.getenv("USER", os.getenv("USERNAME", "user"))
    
    # Get current directory and replace home with ~
    cwd = os.getcwd()
    home = str(Path.home())
    if cwd.startswith(home):
        path = "~" + cwd[len(home):]
    else:
        path = cwd
    
    # Build formatted prompt
    prompt_text = Text()
    
    # Line 1: [MODE]-[USERNAME]-[PATH]
    prompt_text.append("[", style="cyan")
    prompt_text.append(mode, style="purple")
    prompt_text.append("]-[", style="cyan")
    prompt_text.append(username, style="bright_red")
    prompt_text.append("]-[", style="cyan")
    prompt_text.append(path, style="blue")
    prompt_text.append("]", style="cyan")
    prompt_text.append("\n")
    
    # Line 2: [Dav]➜
    prompt_text.append("[", style="cyan")
    prompt_text.append("Dav", style="white")
    prompt_text.append("]", style="cyan")
    prompt_text.append("➜ ", style="cyan")
    
    return prompt_text


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
    
    # Determine color based on usage percentage (for border only)
    if usage.usage_percentage < 50:
        border_color = "green"
    elif usage.usage_percentage < 80:
        border_color = "yellow"
    else:
        border_color = "red"
    
    # Context color is fixed to light orange (using RGB for light orange)
    context_color_rgb = "rgb(255,200,100)"  # Light orange
    
    # Get model info
    model_short = _get_shortened_model_name(model, backend)
    
    # Get rate limit info
    rate_text, rate_color, rate_remaining, rate_total = _get_rate_limit_info()
    
    # Build panel content
    # Format: [light orange]context: 4.2K/128.0K (3.3%)[/light orange] | [cyan]model: gpt-4[/cyan] | [yellow]rate: 7/10[/yellow]
    content = (
        f"[{context_color_rgb}]context: {used_k:.1f}K/{max_k:.1f}K ({usage.usage_percentage:.1f}%)[/{context_color_rgb}] "
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


def _get_raw_char(fd: int) -> str:
    """
    Read a single character from file descriptor in raw mode.
    
    Args:
        fd: File descriptor to read from
    
    Returns:
        Single character string
    """
    return sys.stdin.read(1)


def _get_arrow_key(fd: int) -> Optional[str]:
    """
    Detect arrow key presses from ANSI escape sequences.
    
    Called after ESC character (\x1b) has been detected.
    Expects the next characters to be '[' followed by A/B/C/D.
    
    Args:
        fd: File descriptor to read from
    
    Returns:
        'up', 'down', 'left', 'right', or None if not an arrow key
    """
    # Arrow keys send escape sequence: \x1b[A (up), \x1b[B (down), etc.
    # ESC has already been read, so we expect '[' next
    second_char = _get_raw_char(fd)
    if second_char != '[':
        return None
    
    third_char = _get_raw_char(fd)
    arrow_map = {
        'A': 'up',
        'B': 'down',
        'C': 'right',
        'D': 'left',
    }
    return arrow_map.get(third_char)


def _display_confirmation_menu(message: str, selected: int = 0, is_first: bool = False) -> None:
    """
    Display confirmation menu with Allow and Deny options.
    
    Args:
        message: Confirmation message to display
        selected: Which option is selected (0 = Allow, 1 = Deny)
        is_first: Whether this is the first display (True) or an update (False)
    """
    if is_first:
        # First display - just show the menu
        sys.stdout.write(f"{message}?\n")
    else:
        # Update display - clear previous lines and redraw
        # Move up 2 lines (past the options) and clear
        sys.stdout.write('\033[2A')  # Move up 2 lines
        sys.stdout.write('\r\033[K')  # Clear current line (message line)
        sys.stdout.write('\033[1B\r\033[K')  # Move down, clear option 1
        sys.stdout.write('\033[1B\r\033[K')  # Move down, clear option 2
        sys.stdout.write('\033[2A')  # Move back up to message line
        sys.stdout.write(f"{message}?\n")
    
    # Display options with highlighting
    if selected == 0:
        # Allow is selected
        sys.stdout.write("  \033[1;32m▶ Allow\033[0m\n")  # Bold green
        sys.stdout.write("  \033[31m  Deny\033[0m\n")  # Red
    else:
        # Deny is selected
        sys.stdout.write("  \033[32m  Allow\033[0m\n")  # Green
        sys.stdout.write("  \033[1;31m▶ Deny\033[0m\n")  # Bold red
    
    # Move cursor up 2 lines to be ready for next input
    sys.stdout.write('\033[2A')
    sys.stdout.flush()


def confirm_action(message: str) -> bool:
    """
    Confirm an action with the user using arrow key navigation.
    
    Displays "Allow" (green) and "Deny" (red) options that can be navigated
    with arrow keys. Press Enter to confirm selection.
    
    Args:
        message: Confirmation message to display
    
    Returns:
        True if "Allow" selected, False if "Deny" selected or cancelled
    """
    # Check if we're in a TTY environment
    if not sys.stdin.isatty():
        # Fall back to /dev/tty for piped input scenarios
        try:
            with open("/dev/tty", "r+") as tty_file:
                tty_file.write(f"{message} (y/N): ")
                tty_file.flush()
                response = tty_file.readline().strip().lower()
                return response in ("y", "yes")
        except OSError:
            console.print("[yellow]No TTY available for confirmation. Skipping execution (use --yes to auto-confirm).[/yellow]")
            return False
    
    # Try to use arrow key navigation
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        
        try:
            # Set terminal to raw mode
            tty.setraw(fd)
            
            selected = 0  # 0 = Allow, 1 = Deny
            _display_confirmation_menu(message, selected, is_first=True)
            
            while True:
                char = _get_raw_char(fd)
                
                # Check for arrow keys
                if char == '\x1b':  # ESC sequence
                    arrow = _get_arrow_key(fd)
                    if arrow in ('up', 'down', 'left', 'right'):
                        # Toggle selection
                        selected = 1 - selected
                        _display_confirmation_menu(message, selected, is_first=False)
                        continue
                
                # Check for Enter key (CR or LF)
                if char in ('\r', '\n'):
                    # Clear the menu - move to beginning and clear lines
                    sys.stdout.write('\r')  # Return to start of line
                    sys.stdout.write('\033[2B')  # Move down 2 lines (past the menu)
                    sys.stdout.write('\r\033[K')  # Clear current line
                    sys.stdout.flush()
                    
                    # Restore terminal settings before returning
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    return selected == 0  # True for Allow, False for Deny
                
                # Check for Ctrl+C
                if char == '\x03':  # Ctrl+C
                    # Clear the menu and move to next line
                    sys.stdout.write('\r')  # Return to start of line
                    sys.stdout.write('\033[2B')  # Move down 2 lines
                    sys.stdout.write('\r\033[K\n')  # Clear and newline
                    sys.stdout.flush()
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    return False
                
                # Ignore other characters
                
        finally:
            # Always restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    except (termios.error, OSError, AttributeError):
        # Fall back to simple y/N prompt if raw mode fails
        try:
            prompt = f"{message} (y/N): "
            response = input(prompt).strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            console.print("[yellow]No input received. Skipping execution (use --yes to auto-confirm).[/yellow]")
            return False
    except (EOFError, KeyboardInterrupt):
        console.print("[yellow]No input received. Skipping execution (use --yes to auto-confirm).[/yellow]")
        return False


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


def _interpolate_rgb(start_rgb: Tuple[int, int, int], end_rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    """
    Interpolate between two RGB colors.
    
    Args:
        start_rgb: Starting RGB color (r, g, b)
        end_rgb: Ending RGB color (r, g, b)
        factor: Interpolation factor (0.0 to 1.0)
    
    Returns:
        Interpolated RGB color tuple
    """
    factor = max(0.0, min(1.0, factor))  # Clamp between 0 and 1
    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * factor)
    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * factor)
    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * factor)
    return (r, g, b)


def _get_rainbow_color(position: float) -> Tuple[int, int, int]:
    """
    Get a rainbow color based on position (0.0 to 1.0).
    Creates a smooth gradient through the full rainbow spectrum.
    
    Args:
        position: Position in gradient (0.0 = start/blue, 1.0 = end/pink)
    
    Returns:
        RGB color tuple
    """
    position = max(0.0, min(1.0, position))  # Clamp between 0 and 1
    
    # Define rainbow color stops (full spectrum)
    # Blue → Cyan → Green → Yellow → Orange → Red → Magenta → Pink
    color_stops = [
        (100, 150, 255),   # Blue (start)
        (100, 255, 255),   # Cyan
        (100, 255, 150),   # Green
        (255, 255, 100),   # Yellow
        (255, 200, 100),   # Orange
        (255, 100, 100),   # Red
        (255, 100, 200),   # Magenta
        (255, 150, 100),   # Pink/Orange (end)
    ]
    
    # Map position to color stops
    num_stops = len(color_stops)
    segment_size = 1.0 / (num_stops - 1)
    
    # Find which segment we're in
    segment_index = int(position / segment_size)
    segment_index = min(segment_index, num_stops - 2)  # Don't go past last segment
    
    # Calculate position within the segment
    segment_start = segment_index * segment_size
    segment_pos = (position - segment_start) / segment_size
    
    # Interpolate between the two color stops
    start_color = color_stops[segment_index]
    end_color = color_stops[segment_index + 1]
    
    return _interpolate_rgb(start_color, end_color, segment_pos)


def render_dav_banner() -> None:
    """Render colorful ASCII art banner for Dav with smooth RGB gradients."""
    # ASCII art design for "DAV" with full rainbow gradient
    # Color gradient spans full spectrum: Blue → Cyan → Green → Yellow → Orange → Red → Magenta → Pink
    
    # Define the ASCII art lines
    banner_lines = [
        "",
        "",
        "    ,---,       ,---,                   ",
        "  .'  .' `\\    '  .' \\            ,---. ",
        ",---.'     \\  /  ;    '.         /__./| ",
        "|   |  .`\\  |:  :       \\   ,---.;  ; | ",
        ":   : |  '  |:  |   /\\   \\ /___/ \\  | | ",
        "|   ' '  ;  :|  :  ' ;.   :\\   ;  \\ ' | ",
        "'   | ;  .  ||  |  ;/  \\   \\\\   \\  \\: | ",
        "|   | :  |  ''  :  | \\  \\ ,' ;   \\  ' . ",
        "'   : | /  ; |  |  '  '--'    \\   \\   ' ",
        "|   | '` ,/  |  :  :           \\   `  ; ",
        ";   :  .'    |  | ,'            :   \\ | ",
        "|   ,.'      `--''               '---\"  ",
        "'---'                                   ",
        "",
    ]
    
    # Find the maximum width to determine gradient span
    max_width = 0
    for line in banner_lines:
        if len(line) > max_width:
            max_width = len(line)
    
    # Create a Text object to build the colored banner
    banner_text = Text()
    
    for line in banner_lines:
        line_text = Text()
        char_index = 0
        line_width = len(line)
        
        for char in line:
            # Calculate position as fraction of total width (0.0 to 1.0)
            # Use max_width to ensure consistent gradient across all lines
            position = char_index / max(1, max_width - 1)
            
            # Get rainbow color based on position
            # This creates a smooth gradient across the entire banner width
            rgb = _get_rainbow_color(position)
            
            # Create style with RGB color
            # Apply color to all non-space characters
            if char != ' ':
                # Full brightness for all ASCII art characters
                style = Style(color=f"rgb({rgb[0]},{rgb[1]},{rgb[2]})")
            else:
                # No style for spaces
                style = None
            
            if style:
                line_text.append(char, style=style)
            else:
                line_text.append(char)
            
            char_index += 1
        
        banner_text.append(line_text)
        banner_text.append("\n")
    
    # Print the banner
    console.print(banner_text)
    console.print()  # Extra blank line for spacing

