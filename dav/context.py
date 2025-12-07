"""Context detection and collection for Dav."""

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dav.config import get_max_stdin_chars

# Input validation & truncation limits
MAX_DIR_FILES = 15
MAX_STDIN_CHARS = get_max_stdin_chars()
MAX_PATH_LENGTH = 200

# Cached OS info (does not change during the process lifetime)
_CACHED_OS_INFO: Optional[Dict[str, Any]] = None


def truncate_path(path: str) -> str:
    """Truncate path if it exceeds MAX_PATH_LENGTH."""
    if len(path) > MAX_PATH_LENGTH:
        return path[:MAX_PATH_LENGTH] + "..."
    return path


def get_linux_distro() -> Dict[str, str]:
    """Get Linux distribution information."""
    distro_info = {}
    
    # Try /etc/os-release first (most common)
    os_release_paths = [
        Path("/etc/os-release"),
        Path("/usr/lib/os-release"),
    ]
    
    for os_release_path in os_release_paths:
        if os_release_path.exists():
            try:
                with open(os_release_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, value = line.split("=", 1)
                            # Remove quotes if present
                            value = value.strip('"\'')
                            distro_info[key.lower()] = value
                break
            except Exception:
                continue
    
    # Fallback: try /etc/lsb-release (Ubuntu/Debian)
    if not distro_info:
        lsb_release_path = Path("/etc/lsb-release")
        if lsb_release_path.exists():
            try:
                with open(lsb_release_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line:
                            key, value = line.split("=", 1)
                            value = value.strip('"\'')
                            distro_info[key.lower()] = value
            except Exception:
                pass
    
    return distro_info


def get_os_info() -> Dict[str, Any]:
    """Get operating system information.

    Results are cached for the lifetime of the process since OS identity
    (kernel, distribution) does not change while Dav is running.
    """
    global _CACHED_OS_INFO
    if _CACHED_OS_INFO is not None:
        return _CACHED_OS_INFO

    os_info: Dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "platform": platform.platform(),
    }
    
    # Add Linux distribution info if on Linux
    if platform.system() == "Linux":
        distro_info = get_linux_distro()
        if distro_info:
            # Extract key distribution information
            os_info["distribution"] = distro_info.get("name", distro_info.get("distrib_id", "Unknown"))
            os_info["distribution_id"] = distro_info.get("id", distro_info.get("distrib_id", "unknown"))
            os_info["distribution_version"] = distro_info.get("version_id", distro_info.get("distrib_release", "unknown"))
            os_info["distribution_pretty_name"] = distro_info.get("pretty_name", distro_info.get("distrib_description", ""))
            
            # Add version codename if available
            if "version_codename" in distro_info:
                os_info["distribution_codename"] = distro_info["version_codename"]
            elif "distrib_codename" in distro_info:
                os_info["distribution_codename"] = distro_info["distrib_codename"]
    
    _CACHED_OS_INFO = os_info
    return os_info


def get_current_directory() -> Dict[str, Any]:
    """Get current working directory information."""
    try:
        cwd = os.getcwd()
        cwd_path = Path(cwd)
        
        # Truncate path if too long
        cwd_display = truncate_path(cwd)
        
        context = {
            "path": cwd_display,
            "exists": cwd_path.exists(),
        }
        
        # List directory contents (limited)
        if cwd_path.exists() and cwd_path.is_dir():
            try:
                # List directory contents once and reuse slice/length
                all_items = list(cwd_path.iterdir())
                items = all_items[:MAX_DIR_FILES]
                context["contents"] = [
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                    for item in items
                ]
                if len(all_items) > MAX_DIR_FILES:
                    context["contents_truncated"] = True
            except PermissionError:
                context["contents"] = "permission denied"
        else:
            context["contents"] = []
        
        return context
    except Exception as e:
        return {"path": "unknown", "error": str(e)}


def get_stdin_input() -> Optional[str]:
    """Get piped input from stdin if available."""
    if not sys.stdin.isatty():
        try:
            stdin_content = sys.stdin.read()
            # Truncate if too long
            if len(stdin_content) > MAX_STDIN_CHARS:
                stdin_content = stdin_content[:MAX_STDIN_CHARS] + "\n... (truncated)"
            return stdin_content
        except Exception:
            return None
    return None


def build_context(query: Optional[str] = None, stdin_content: Optional[str] = None) -> Dict[str, Any]:
    """Build complete context dictionary for AI prompt."""
    context = {
        "os": get_os_info(),
        "directory": get_current_directory(),
    }
    
    # Add stdin content if available
    if stdin_content:
        context["stdin"] = stdin_content
    else:
        stdin_input = get_stdin_input()
        if stdin_input:
            context["stdin"] = stdin_input
    
    # Add query if provided
    if query:
        context["query"] = query
    
    return context


def format_context_for_prompt(context: Dict[str, Any], command_outputs: Optional[List[Dict[str, Any]]] = None) -> str:
    """Format context dictionary into a readable prompt string.
    
    Args:
        context: Context dictionary
        command_outputs: Optional list of recent command outputs to include
    """
    
    lines = []
    
    # OS Information
    lines.append("## System Information (for your awareness; mention only if relevant)")
    os_info = context.get("os", {})
    system = os_info.get("system", "unknown")
    lines.append(f"- Operating System: {system}")
    
    # Add Linux distribution details if available
    if system == "Linux":
        if "distribution" in os_info:
            distro_name = os_info.get("distribution_pretty_name") or os_info.get("distribution", "Unknown")
            distro_version = os_info.get("distribution_version", "")
            if distro_version and distro_version != "unknown":
                lines.append(f"- Linux Distribution: {distro_name} (Version: {distro_version})")
            else:
                lines.append(f"- Linux Distribution: {distro_name}")
            
            if "distribution_codename" in os_info:
                lines.append(f"- Distribution Codename: {os_info['distribution_codename']}")
        
        lines.append(f"- Kernel Version: {os_info.get('release', 'unknown')}")
    else:
        lines.append(f"- Release: {os_info.get('release', 'unknown')}")
    
    lines.append(f"- Platform: {os_info.get('platform', 'unknown')}")
    lines.append(f"- Architecture: {os_info.get('machine', 'unknown')}")
    lines.append("")
    
    # Directory Information
    lines.append("## Current Directory (internal context)")
    dir_info = context.get("directory", {})
    lines.append(f"- Path: {dir_info.get('path', 'unknown')}")
    
    contents = dir_info.get("contents", [])
    if isinstance(contents, list) and contents:
        lines.append("- Contents:")
        for item in contents:
            item_type = item.get("type", "unknown")
            item_name = item.get("name", "unknown")
            if item_type == "file":
                size = item.get("size", 0)
                lines.append(f"  - {item_name} (file, {size} bytes)")
            else:
                lines.append(f"  - {item_name} (directory)")
        
        if dir_info.get("contents_truncated"):
            lines.append(f"  ... (showing first {MAX_DIR_FILES} items)")
    elif contents == "permission denied":
        lines.append("- Contents: permission denied")
    lines.append("")
    
    # Command Outputs (visible to Dav)
    if command_outputs:
        lines.append("## Recent Command Outputs (visible to Dav)")
        for output_entry in command_outputs:
            command = output_entry.get("command", "unknown")
            success = output_entry.get("success", False)
            stdout = output_entry.get("stdout", "")
            stderr = output_entry.get("stderr", "")
            
            status = "Success" if success else "Failed"
            lines.append(f"### Command: {command}")
            lines.append(f"Status: {status}")
            
            if stdout or stderr:
                lines.append("Output:")
                lines.append("```")
                if stdout:
                    lines.append(stdout)
                if stderr:
                    if stdout:
                        lines.append("")  # Blank line between stdout and stderr
                    lines.append(f"[stderr] {stderr}")
                lines.append("```")
            else:
                lines.append("Output: (no output)")
            lines.append("")
        lines.append("")
    
    # Stdin Input
    if "stdin" in context:
        lines.append("## Piped Input (internal content to analyze)")
        lines.append("```")
        lines.append(context["stdin"])
        lines.append("```")
        lines.append("")
    
    # Query
    if "query" in context:
        lines.append("## User Query")
        lines.append(context["query"])
        lines.append("")
    
    return "\n".join(lines)

