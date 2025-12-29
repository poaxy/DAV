"""Token counting utilities for accurate context tracking."""

from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=10)
def _get_encoding(model: str) -> 'tiktoken.Encoding':
    """
    Get tiktoken encoding for a model, with caching.
    
    Encoding objects are expensive to create, so we cache them.
    Cache size is small (10) since few different encodings are used.
    
    Args:
        model: Model name or encoding name
        
    Returns:
        tiktoken.Encoding object
    """
    try:
        import tiktoken
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            # If model not found, try cl100k_base (used by GPT-4 and newer)
            return tiktoken.get_encoding("cl100k_base")
    except ImportError:
        # tiktoken not available - this shouldn't happen if we're calling this
        # but we need to handle it for type checking
        raise ImportError("tiktoken is required for token counting")


@lru_cache(maxsize=512)
def _count_tokens_cached(text: str, encoding_name: str) -> int:
    """
    Count tokens with caching for repeated strings.
    
    This caches token counts for repeated strings (like system prompts,
    context strings) which are frequently reused. Cache size is 512 to
    handle common repeated strings.
    
    Args:
        text: Text to count tokens for
        encoding_name: Model name or encoding identifier
        
    Returns:
        Number of tokens
    """
    encoding = _get_encoding(encoding_name)
    return len(encoding.encode(text))


def count_tokens(text: str, backend: str, model: Optional[str] = None) -> int:
    """
    Count tokens accurately for the given backend and model.
    
    Args:
        text: Text to count tokens for
        backend: AI backend ("openai", "anthropic", or "gemini")
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
    elif backend == "gemini":
        # Gemini tokenization is different, but for context estimation we can
        # approximate using the same cl100k_base encoding used for Claude/GPT-4.
        try:
            return _count_tokens_cached(text, "cl100k_base")
        except Exception:
            return _estimate_tokens(text)
    else:
        # Fallback to estimation
        return _estimate_tokens(text)


def _count_tokens_openai(text: str, model: Optional[str] = None) -> int:
    """Count tokens for OpenAI models using tiktoken with caching."""
    try:
        # Default model if not specified
        model = model or "gpt-4-turbo-preview"
        
        # Use cached token counting for better performance
        return _count_tokens_cached(text, model)
    except ImportError:
        # tiktoken not available, fall back to estimation
        return _estimate_tokens(text)
    except Exception:
        # Any other error, fall back to estimation
        return _estimate_tokens(text)


def _count_tokens_anthropic(text: str, model: Optional[str] = None) -> int:
    """Count tokens for Anthropic models using tiktoken with caching."""
    try:
        # Anthropic uses similar tokenization to OpenAI
        # Use cl100k_base as approximation (this is what Claude models use)
        # Use "cl100k_base" as encoding name for consistent caching
        return _count_tokens_cached(text, "cl100k_base")
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








