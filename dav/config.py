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
        return Path(db_path)
    return Path.home() / ".dav" / "history.db"

def get_session_dir() -> Path:
    """Get directory for session files."""
    session_dir = os.getenv("DAV_SESSION_DIR")
    if session_dir:
        return Path(session_dir)
    return Path.home() / ".dav" / "sessions"

