"""Rate limiting for API calls and command execution."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class RateLimitState:
    """State for rate limiting."""
    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)
    request_count: int = 0


class RateLimiter:
    """
    Token bucket rate limiter for API calls and command execution.
    
    Implements a token bucket algorithm:
    - Tokens are added at a constant rate (refill_rate per second)
    - Each request consumes tokens (cost)
    - Requests are allowed if sufficient tokens are available
    """
    
    def __init__(
        self,
        capacity: float = 10.0,  # Maximum tokens
        refill_rate: float = 1.0,  # Tokens per second
        cost_per_request: float = 1.0,  # Tokens consumed per request
        window_seconds: int = 60,  # Time window for counting
    ):
        """
        Initialize rate limiter.
        
        Args:
            capacity: Maximum number of tokens in bucket
            refill_rate: Tokens added per second
            cost_per_request: Tokens consumed per request
            window_seconds: Time window for request counting
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.cost_per_request = cost_per_request
        self.window_seconds = window_seconds
        
        # Per-user rate limit state (in-memory)
        # Key: user identifier (or 'default' for single-user systems)
        self._buckets: Dict[str, RateLimitState] = defaultdict(
            lambda: RateLimitState(tokens=capacity, last_update=time.time())
        )
        
        # Request history for window-based limiting
        self._request_history: Dict[str, List[float]] = defaultdict(list)
    
    def _refill_tokens(self, user_id: str = "default") -> None:
        """Refill tokens based on elapsed time."""
        state = self._buckets[user_id]
        now = time.time()
        elapsed = now - state.last_update
        
        # Add tokens based on refill rate
        new_tokens = min(
            self.capacity,
            state.tokens + (elapsed * self.refill_rate)
        )
        
        state.tokens = new_tokens
        state.last_update = now
    
    def _cleanup_old_requests(self, user_id: str = "default") -> None:
        """Remove requests outside the time window."""
        now = time.time()
        cutoff = now - self.window_seconds
        
        history = self._request_history[user_id]
        # Keep only requests within the window
        self._request_history[user_id] = [
            timestamp for timestamp in history if timestamp > cutoff
        ]
    
    def is_allowed(
        self,
        user_id: str = "default",
        cost: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            user_id: User identifier (defaults to "default" for single-user)
            cost: Token cost for this request (defaults to cost_per_request)
            
        Returns:
            Tuple of (is_allowed, error_message)
        """
        if cost is None:
            cost = self.cost_per_request
        
        # Refill tokens
        self._refill_tokens(user_id)
        
        # Check token bucket
        state = self._buckets[user_id]
        if state.tokens < cost:
            return False, f"Rate limit exceeded. Please wait before making another request."
        
        # Check request count in time window
        self._cleanup_old_requests(user_id)
        history = self._request_history[user_id]
        
        # Allow if we have tokens and haven't exceeded window limit
        if state.tokens >= cost:
            # Consume tokens
            state.tokens -= cost
            state.request_count += 1
            
            # Record request timestamp
            self._request_history[user_id].append(time.time())
            
            return True, None
        
        return False, "Rate limit exceeded"
    
    def get_remaining_tokens(self, user_id: str = "default") -> float:
        """Get remaining tokens for user."""
        self._refill_tokens(user_id)
        return self._buckets[user_id].tokens
    
    def get_time_until_next_token(self, user_id: str = "default") -> float:
        """
        Get time in seconds until next token will be available.
        
        Args:
            user_id: User identifier
        
        Returns:
            Seconds until next token (0 if tokens already available)
        """
        self._refill_tokens(user_id)
        state = self._buckets[user_id]
        
        # If we already have tokens, return 0
        if state.tokens >= 1.0:
            return 0.0
        
        # Calculate how much time needed to get 1 token
        tokens_needed = 1.0 - state.tokens
        if tokens_needed <= 0:
            return 0.0
        
        # Time = tokens_needed / refill_rate
        time_needed = tokens_needed / self.refill_rate
        return time_needed
    
    def get_request_count(self, user_id: str = "default") -> int:
        """Get number of requests in current window."""
        self._cleanup_old_requests(user_id)
        return len(self._request_history[user_id])


# Global rate limiter instances
# API rate limiter: 10 requests per minute, 100 per hour
api_rate_limiter = RateLimiter(
    capacity=10.0,
    refill_rate=10.0 / 60.0,  # 10 tokens per 60 seconds
    cost_per_request=1.0,
    window_seconds=60,
)

# Command execution rate limiter: 20 commands per minute
command_rate_limiter = RateLimiter(
    capacity=20.0,
    refill_rate=20.0 / 60.0,  # 20 tokens per 60 seconds
    cost_per_request=1.0,
    window_seconds=60,
)


def check_api_rate_limit(user_id: str = "default") -> Tuple[bool, Optional[str]]:
    """
    Check if API call is allowed under rate limit.
    
    Args:
        user_id: User identifier
        
    Returns:
        Tuple of (is_allowed, error_message)
    """
    return api_rate_limiter.is_allowed(user_id)


def check_command_rate_limit(user_id: str = "default") -> Tuple[bool, Optional[str]]:
    """
    Check if command execution is allowed under rate limit.
    
    Args:
        user_id: User identifier
        
    Returns:
        Tuple of (is_allowed, error_message)
    """
    return command_rate_limiter.is_allowed(user_id)

