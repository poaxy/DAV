"""Context usage tracking for interactive mode."""

from dataclasses import dataclass
from typing import Optional

from dav.token_counter import count_tokens


@dataclass
class ContextUsage:
    """Context usage breakdown."""
    system_prompt: int = 0
    system_context: int = 0
    session_history: int = 0
    current_query: int = 0
    total_used: int = 0
    remaining: int = 0
    max_tokens: int = 0
    usage_percentage: float = 0.0


class ContextTracker:
    """Track context usage across all components."""
    
    def __init__(self, backend: str, model: Optional[str] = None):
        """
        Initialize context tracker.
        
        Args:
            backend: AI backend ("openai" or "anthropic")
            model: Model name
        """
        self.backend = backend
        self.model = model or self._get_default_model()
        self.max_tokens = self._get_max_tokens()
        self.system_prompt_tokens = 0
        self._cache_system_prompt()
    
    def _get_default_model(self) -> str:
        """Get default model for backend."""
        if self.backend == "openai":
            return "gpt-4-turbo-preview"
        elif self.backend == "anthropic":
            return "claude-3-5-sonnet-20241022"
        return "gpt-4-turbo-preview"
    
    def _get_max_tokens(self) -> int:
        """
        Get maximum context window for current model.
        
        Returns:
            Maximum tokens for the model
        """
        if self.backend == "openai":
            # OpenAI models typically have 128K context window
            if "gpt-4" in self.model.lower():
                return 128_000
            elif "gpt-3.5" in self.model.lower():
                return 16_385  # GPT-3.5 has smaller context
            return 128_000  # Default for newer models
        elif self.backend == "anthropic":
            # Anthropic Claude models have 200K context window
            if "claude-3" in self.model.lower() or "claude-3.5" in self.model.lower():
                return 200_000
            return 200_000  # Default for Claude models
        return 80_000  # Safe default
    
    def _cache_system_prompt(self):
        """Cache system prompt token count (only calculated once)."""
        from dav.ai_backend import get_system_prompt
        
        # Get system prompt for interactive execute mode
        system_prompt = get_system_prompt(execute_mode=True, interactive_mode=True)
        self.system_prompt_tokens = count_tokens(
            system_prompt, 
            self.backend, 
            self.model
        )
    
    def calculate_usage(
        self,
        system_context: str,
        session_history: str,
        current_query: str
    ) -> ContextUsage:
        """
        Calculate current context usage.
        
        Args:
            system_context: System context string (OS info, directory, etc.)
            session_history: Session conversation history
            current_query: Current user query
        
        Returns:
            ContextUsage object with breakdown
        """
        # Count tokens for each component
        system_context_tokens = count_tokens(
            system_context, 
            self.backend, 
            self.model
        )
        history_tokens = count_tokens(
            session_history, 
            self.backend, 
            self.model
        )
        query_tokens = count_tokens(
            current_query, 
            self.backend, 
            self.model
        )
        
        # Calculate totals
        total_used = (
            self.system_prompt_tokens +
            system_context_tokens +
            history_tokens +
            query_tokens
        )
        
        remaining = max(0, self.max_tokens - total_used)
        usage_percentage = (total_used / self.max_tokens) * 100 if self.max_tokens > 0 else 0
        
        return ContextUsage(
            system_prompt=self.system_prompt_tokens,
            system_context=system_context_tokens,
            session_history=history_tokens,
            current_query=query_tokens,
            total_used=total_used,
            remaining=remaining,
            max_tokens=self.max_tokens,
            usage_percentage=usage_percentage
        )











