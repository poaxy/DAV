"""Configuration management for Dav."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file from user's home directory or current directory
env_paths = [
    Path.home() / ".dav" / ".env",
    Path.cwd() / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        # Check if file is not empty before loading
        try:
            if env_path.stat().st_size > 0:
                load_dotenv(env_path)
        except Exception:
            # If we can't check size, try loading anyway
            load_dotenv(env_path)
        break

# Default configuration
DEFAULT_MODEL_OPENAI = "gpt-4-turbo-preview"
DEFAULT_MODEL_ANTHROPIC = "claude-3-5-sonnet-20241022"
DEFAULT_BACKEND = "openai"  # or "anthropic"
DEFAULT_MAX_STDIN_CHARS = 32000
DEFAULT_MAX_CONTEXT_TOKENS = 80000  # 80k tokens (generous but safe)
DEFAULT_MAX_CONTEXT_MESSAGES = 100  # Allow many exchanges in a session

# Configuration getters
def get_api_key(backend: str) -> Optional[str]:
    """Get API key for the specified backend."""
    if backend == "openai":
        return os.getenv("OPENAI_API_KEY")
    elif backend == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    return None

def get_default_model(backend: str) -> str:
    """Get default model for the specified backend."""
    model = os.getenv("DAV_DEFAULT_MODEL")
    if model:
        return model
    
    if backend == "openai":
        return os.getenv("DAV_OPENAI_MODEL", DEFAULT_MODEL_OPENAI)
    elif backend == "anthropic":
        return os.getenv("DAV_ANTHROPIC_MODEL", DEFAULT_MODEL_ANTHROPIC)
    
    return DEFAULT_MODEL_OPENAI

def get_default_backend() -> str:
    """Get default AI backend."""
    return os.getenv("DAV_BACKEND", DEFAULT_BACKEND)

def get_execute_permission() -> bool:
    """Check if command execution is enabled."""
    return os.getenv("DAV_ALLOW_EXECUTE", "false").lower() == "true"

def get_history_enabled() -> bool:
    """Check if history is enabled."""
    return os.getenv("DAV_HISTORY_ENABLED", "true").lower() == "true"

def get_history_db_path() -> Path:
    """Get path to history database."""
    db_path = os.getenv("DAV_HISTORY_DB")
    if db_path:
        # Expand ~ to home directory
        return Path(db_path).expanduser()
    return Path.home() / ".dav" / "history.db"

def get_session_dir() -> Path:
    """Get directory for session files."""
    session_dir = os.getenv("DAV_SESSION_DIR")
    if session_dir:
        # Expand ~ to home directory
        return Path(session_dir).expanduser()
    return Path.home() / ".dav" / "sessions"


def get_max_stdin_chars() -> int:
    """Get maximum number of stdin characters to capture."""
    value = os.getenv("DAV_MAX_STDIN_CHARS")
    if value:
        try:
            parsed = int(value)
            # Ensure the value is reasonable (positive and within 1MB)
            if parsed <= 0:
                return DEFAULT_MAX_STDIN_CHARS
            # Cap at 1,000,000 characters to prevent excessive memory usage
            return min(parsed, 1_000_000)
        except ValueError:
            return DEFAULT_MAX_STDIN_CHARS
    return DEFAULT_MAX_STDIN_CHARS


def get_max_context_tokens() -> int:
    """Get maximum tokens for context window."""
    value = os.getenv("DAV_MAX_CONTEXT_TOKENS")
    if value:
        try:
            parsed = int(value)
            # Ensure reasonable value (positive and within 200k for Claude)
            if parsed <= 0:
                return DEFAULT_MAX_CONTEXT_TOKENS
            # Cap at 200k to prevent issues
            return min(parsed, 200_000)
        except ValueError:
            return DEFAULT_MAX_CONTEXT_TOKENS
    return DEFAULT_MAX_CONTEXT_TOKENS


def get_max_context_messages() -> int:
    """Get maximum messages to include in context."""
    value = os.getenv("DAV_MAX_CONTEXT_MESSAGES")
    if value:
        try:
            parsed = int(value)
            # Ensure reasonable value
            if parsed <= 0:
                return DEFAULT_MAX_CONTEXT_MESSAGES
            # Cap at 500 to prevent excessive memory usage
            return min(parsed, 500)
        except ValueError:
            return DEFAULT_MAX_CONTEXT_MESSAGES
    return DEFAULT_MAX_CONTEXT_MESSAGES


def get_automation_sudo_method() -> str:
    """Get automation sudo method preference."""
    return os.getenv("DAV_AUTOMATION_SUDO_METHOD", "sudoers").lower()


def get_automation_log_dir() -> Path:
    """Get directory for automation logs."""
    log_dir = os.getenv("DAV_AUTOMATION_LOG_DIR")
    if log_dir:
        return Path(log_dir).expanduser()
    return Path.home() / ".dav" / "logs"


def get_automation_log_retention_days() -> int:
    """Get number of days to retain automation logs."""
    value = os.getenv("DAV_AUTOMATION_LOG_RETENTION_DAYS")
    if value:
        try:
            parsed = int(value)
            if parsed <= 0:
                return 30
            # Cap at 365 days
            return min(parsed, 365)
        except ValueError:
            return 30
    return 30

