"""Failover management for API providers."""

from typing import List, Optional, Set

from dav.config import get_api_key, get_provider_priority


class FailoverManager:
    """Manages failover between API providers."""
    
    def __init__(self, initial_backend: str):
        """
        Initialize failover manager.
        
        Args:
            initial_backend: The initial backend to use
        """
        self.initial_backend = initial_backend
        self.current_backend = initial_backend
        self.failed_backends: Set[str] = set()
        self.available_providers = self._get_available_providers()
        
        # If initial backend is not available, try to switch to first available
        if initial_backend not in self.available_providers:
            if self.available_providers:
                # Switch to first available provider
                self.current_backend = self.available_providers[0]
            else:
                raise ValueError(
                    f"Initial backend '{initial_backend}' is not configured and no other providers are available. "
                    f"Please configure at least one API provider."
                )
    
    def _get_available_providers(self) -> List[str]:
        """Get list of configured providers."""
        available = []
        priority_order = get_provider_priority()
        
        for backend in priority_order:
            if get_api_key(backend):
                available.append(backend)
            elif backend == "gemini":
                # Check for GOOGLE_API_KEY as fallback
                import os
                if os.getenv("GOOGLE_API_KEY"):
                    available.append(backend)
        
        return available
    
    def has_failed(self, backend: str) -> bool:
        """Check if a backend has failed."""
        return backend in self.failed_backends
    
    def mark_failed(self, backend: str) -> None:
        """Mark a backend as failed."""
        self.failed_backends.add(backend)
    
    def get_next_provider(self) -> Optional[str]:
        """
        Get the next available provider to try (excluding current backend).
        
        Returns:
            Next provider name, or None if no more providers available
        """
        available = [
            p for p in self.available_providers
            if p not in self.failed_backends and p != self.current_backend
        ]
        
        if not available:
            return None
        
        # Return the first available provider (already in priority order)
        return available[0]
    
    def switch_to_backup(self) -> Optional[str]:
        """
        Switch to backup provider and return it.
        
        Returns:
            Backup provider name, or None if no backup available
        """
        backup = self.get_next_provider()
        if backup and backup != self.current_backend:
            self.current_backend = backup
            return backup
        return None
    
    def get_current_backend(self) -> str:
        """Get current active backend."""
        return self.current_backend
    
    def has_backups(self) -> bool:
        """Check if backup providers are available."""
        return len(self.available_providers) > 1
    
    def get_failed_backends(self) -> List[str]:
        """Get list of failed backends."""
        return list(self.failed_backends)


def is_failover_error(error: Exception) -> bool:
    """
    Determine if an error should trigger failover.
    
    Args:
        error: The exception that occurred
        
    Returns:
        True if error should trigger failover, False otherwise
    """
    error_type = type(error).__name__
    error_str = str(error).lower()
    
    # Network errors
    network_errors = (
        "ConnectionError",
        "TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "Connection",
        "Network",
        "socket",
        "urllib3.exceptions",
        "requests.exceptions",
    )
    
    if any(net_err in error_type for net_err in network_errors):
        return True
    
    # Rate limit errors
    rate_limit_indicators = (
        "rate limit",
        "rate_limit",
        "429",
        "too many requests",
        "quota exceeded",
        "quota_exceeded",
    )
    
    if any(indicator in error_str for indicator in rate_limit_indicators):
        return True
    
    # Authentication errors
    auth_indicators = (
        "401",
        "unauthorized",
        "invalid api key",
        "authentication",
        "api key",
        "api_key",
        "forbidden",
        "403",
    )
    
    if any(indicator in error_str for indicator in auth_indicators):
        return True
    
    # Server errors
    server_indicators = (
        "500",
        "502",
        "503",
        "504",
        "internal server error",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "server error",
    )
    
    if any(indicator in error_str for indicator in server_indicators):
        return True
    
    # Check for specific SDK exceptions
    # OpenAI exceptions
    if "openai" in error_type.lower():
        if any(indicator in error_str for indicator in rate_limit_indicators + auth_indicators + server_indicators):
            return True
    
    # Anthropic exceptions
    if "anthropic" in error_type.lower():
        if any(indicator in error_str for indicator in rate_limit_indicators + auth_indicators + server_indicators):
            return True
    
    # Google/Gemini exceptions
    if "google" in error_type.lower() or "genai" in error_type.lower():
        if any(indicator in error_str for indicator in rate_limit_indicators + auth_indicators + server_indicators):
            return True
    
    # All other exceptions should trigger failover (catch-all)
    return True

