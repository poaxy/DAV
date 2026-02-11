"""Configuration management for Dav."""

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

env_paths = [
    Path.home() / ".dav" / ".env",
    Path.cwd() / ".env",
]
for env_path in env_paths:
    if env_path.exists():
        try:
            from dav.file_security import check_and_warn_permissions
            check_and_warn_permissions(env_path, "Configuration file")
        except Exception:
            pass
        
        try:
            if env_path.stat().st_size > 0:
                load_dotenv(env_path)
        except Exception:
            load_dotenv(env_path)
        break

DEFAULT_MODEL_OPENAI = "gpt-4-turbo-preview"
DEFAULT_MODEL_ANTHROPIC = "claude-3-5-sonnet-20241022"
DEFAULT_MODEL_GEMINI = "gemini-1.5-pro-latest"
DEFAULT_BACKEND = "openai"
DEFAULT_MAX_STDIN_CHARS = 32000
DEFAULT_MAX_CONTEXT_TOKENS = 80000
DEFAULT_MAX_CONTEXT_MESSAGES = 100
def get_api_key(backend: str) -> Optional[str]:
    """Get API key for the specified backend."""
    if backend == "openai":
        return os.getenv("OPENAI_API_KEY")
    elif backend == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    elif backend == "gemini":
        return os.getenv("GEMINI_API_KEY")
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
    elif backend == "gemini":
        return os.getenv("DAV_GEMINI_MODEL", DEFAULT_MODEL_GEMINI)
    
    return DEFAULT_MODEL_OPENAI

def get_default_backend() -> str:
    """Get default AI backend."""
    return os.getenv("DAV_BACKEND", DEFAULT_BACKEND)

def get_execute_permission() -> bool:
    """Check if command execution is enabled."""
    return os.getenv("DAV_ALLOW_EXECUTE", "false").lower() == "true"

def get_session_dir() -> Path:
    """Get directory for session files."""
    session_dir = os.getenv("DAV_SESSION_DIR")
    if session_dir:
        return Path(session_dir).expanduser()
    return Path.home() / ".dav" / "sessions"


def get_max_stdin_chars() -> int:
    """Get maximum number of stdin characters to capture."""
    value = os.getenv("DAV_MAX_STDIN_CHARS")
    if value:
        try:
            parsed = int(value)
            if parsed <= 0:
                return DEFAULT_MAX_STDIN_CHARS
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
            if parsed <= 0:
                return DEFAULT_MAX_CONTEXT_TOKENS
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
            if parsed <= 0:
                return DEFAULT_MAX_CONTEXT_MESSAGES
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
            return min(parsed, 365)
        except ValueError:
            return 30
    return 30


def get_scripts_dir() -> Path:
    """Get directory for user-created automation scripts.

    Scripts are stored under the user's .dav directory by default, but can be
    overridden via DAV_SCRIPTS_DIR.
    """
    scripts_dir = os.getenv("DAV_SCRIPTS_DIR")
    if scripts_dir:
        return Path(scripts_dir).expanduser()
    return Path.home() / ".dav" / "scripts"


def is_provider_configured(backend: str) -> bool:
    """Check if a provider has an API key configured."""
    api_key = get_api_key(backend)
    if api_key:
        return True
    
    # Special case for Gemini - check GOOGLE_API_KEY
    if backend == "gemini":
        return os.getenv("GOOGLE_API_KEY") is not None
    
    return False


def get_available_providers() -> List[str]:
    """Get list of configured providers."""
    available = []
    priority_order = get_provider_priority()
    
    for backend in priority_order:
        if is_provider_configured(backend):
            available.append(backend)
    
    return available


def get_provider_priority() -> List[str]:
    """Get provider priority order."""
    # Default priority: OpenAI > Anthropic > Gemini
    return ["openai", "anthropic", "gemini"]


def get_nvd_api_key() -> Optional[str]:
    """Get NVD API key from environment."""
    return os.getenv("DAV_NVD_API_KEY") or os.getenv("NVD_API_KEY")


def get_cve_cache_dir() -> Path:
    """Get directory for CVE cache files."""
    cache_dir = os.getenv("DAV_CVE_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser()
    return Path.home() / ".dav" / "cve_cache"


def get_cve_cache_ttl() -> int:
    """Get CVE cache TTL in seconds (default: 24 hours)."""
    try:
        return int(os.getenv("DAV_CVE_CACHE_TTL", "86400"))
    except ValueError:
        return 86400

