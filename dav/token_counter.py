"""Token counting utilities for accurate context tracking."""

from typing import Optional


def count_tokens(text: str, backend: str, model: Optional[str] = None) -> int:
    """
    Count tokens accurately for the given backend and model.
    
    Args:
        text: Text to count tokens for
        backend: AI backend ("openai" or "anthropic")
        model: Model name (optional, for better accuracy)
    
    Returns:
        Number of tokens
    """
    if not text:
        return 0
    
    if backend == "openai":
        return _count_tokens_openai(text, model)
    elif backend == "anthropic":
        return _count_tokens_anthropic(text, model)
    else:
        # Fallback to estimation
        return _estimate_tokens(text)


def _count_tokens_openai(text: str, model: Optional[str] = None) -> int:
    """Count tokens for OpenAI models using tiktoken."""
    try:
        import tiktoken
        
        # Default model if not specified
        model = model or "gpt-4-turbo-preview"
        
        # Map model names to tiktoken encodings
        # For newer models, try to get encoding, fallback to cl100k_base
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # If model not found, try cl100k_base (used by GPT-4 and newer)
            encoding = tiktoken.get_encoding("cl100k_base")
        
        return len(encoding.encode(text))
    except ImportError:
        # tiktoken not available, fall back to estimation
        return _estimate_tokens(text)
    except Exception:
        # Any other error, fall back to estimation
        return _estimate_tokens(text)


def _count_tokens_anthropic(text: str, model: Optional[str] = None) -> int:
    """Count tokens for Anthropic models."""
    try:
        import tiktoken
        
        # Anthropic uses similar tokenization to OpenAI
        # Use cl100k_base as approximation (this is what Claude models use)
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        # tiktoken not available, fall back to estimation
        return _estimate_tokens(text)
    except Exception:
        # Any other error, fall back to estimation
        return _estimate_tokens(text)


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count using character-based approximation.
    
    Rough approximation: ~4 characters per token (varies by language).
    This is less accurate but works without dependencies.
    """
    return len(text) // 4

