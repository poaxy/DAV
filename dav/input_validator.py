"""Input validation and sanitization utilities for user queries and AI responses."""

import re
import base64
import urllib.parse
from typing import Tuple, Optional, List

# Maximum query length to prevent DoS
MAX_QUERY_LENGTH = 10000
MAX_AI_RESPONSE_LENGTH = 50000

# Control characters that should be removed (except newlines and tabs)
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]')


# Prompt injection patterns
PROMPT_INJECTION_PATTERNS = [
    # Instruction overrides
    (r'(?i)ignore\s+(previous|all|above)\s+instructions?', 'Instruction override attempt'),
    (r'(?i)forget\s+(everything|all|previous)', 'Memory wipe attempt'),
    (r'(?i)new\s+instructions?', 'Instruction replacement attempt'),
    (r'(?i)disregard\s+(previous|all|above)', 'Instruction disregard attempt'),
    (r'(?i)override\s+(previous|system)', 'System override attempt'),
    
    # System prompt leaks
    (r'(?i)what\s+(is|are)\s+(your|the)\s+(system\s+)?prompt', 'System prompt leak attempt'),
    (r'(?i)show\s+me\s+(your|the)\s+(system\s+)?(prompt|instructions?)', 'Instruction leak attempt'),
    (r'(?i)reveal\s+(your|the)\s+(system\s+)?(prompt|instructions?)', 'Instruction reveal attempt'),
    (r'(?i)print\s+(your|the)\s+(system\s+)?(prompt|instructions?)', 'Instruction print attempt'),
    
    # Role confusion
    (r'(?i)you\s+are\s+now\s+(a|an)', 'Role confusion attempt'),
    (r'(?i)act\s+as\s+(if\s+you\s+are\s+)?(a|an)', 'Role acting attempt'),
    (r'(?i)pretend\s+to\s+be\s+(a|an)', 'Role pretense attempt'),
    (r'(?i)you\s+should\s+act\s+as', 'Role directive attempt'),
    
    # Encoding tricks
    (r'(?i)base64\s+(decode|encode)', 'Base64 encoding attempt'),
    (r'(?i)decode\s+this\s+base64', 'Base64 decode attempt'),
    (r'(?i)url\s+(decode|encode)', 'URL encoding attempt'),
    (r'(?i)decode\s+this\s+url', 'URL decode attempt'),
    
    # Direct manipulation attempts
    (r'(?i)change\s+(your|the)\s+(system\s+)?(prompt|instructions?)', 'Prompt change attempt'),
    (r'(?i)modify\s+(your|the)\s+(system\s+)?(prompt|instructions?)', 'Prompt modification attempt'),
    (r'(?i)update\s+(your|the)\s+(system\s+)?(prompt|instructions?)', 'Prompt update attempt'),
]


def sanitize_user_input(query: str) -> str:
    """
    Sanitize user input by removing control characters and limiting length.
    
    Args:
        query: User query string
        
    Returns:
        Sanitized query string
    """
    if not query:
        return ""
    
    # Limit length
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]
    
    # Remove control characters (except newline and tab)
    # Keep newlines (\n) and tabs (\t) as they might be legitimate
    sanitized = ""
    for char in query:
        if char == '\n' or char == '\t':
            sanitized += char
        elif not CONTROL_CHARS_PATTERN.match(char):
            sanitized += char
    
    # Normalize whitespace (collapse multiple spaces, but preserve newlines)
    lines = sanitized.split('\n')
    normalized_lines = [' '.join(line.split()) for line in lines]
    sanitized = '\n'.join(normalized_lines)
    
    return sanitized.strip()


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect prompt injection patterns in text.
    
    Args:
        text: Text to check for prompt injection
        
    Returns:
        Tuple of (is_injection, reason) where is_injection is True if injection detected
    """
    text_lower = text.lower()
    
    for pattern, reason in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text):
            return True, reason
    
    # Check for base64 encoded content (common in injection attacks)
    # Look for base64-like strings (long alphanumeric strings)
    base64_pattern = r'[A-Za-z0-9+/]{20,}={0,2}'
    potential_base64 = re.findall(base64_pattern, text)
    for match in potential_base64:
        try:
            # Try to decode - if it succeeds and contains suspicious content, flag it
            decoded = base64.b64decode(match).decode('utf-8', errors='ignore')
            if any(keyword in decoded.lower() for keyword in ['ignore', 'forget', 'override', 'system', 'prompt']):
                return True, 'Base64 encoded injection attempt'
        except Exception:
            pass
    
    # Check for URL encoded content
    try:
        decoded = urllib.parse.unquote(text)
        if decoded != text and len(decoded) > len(text) * 0.8:  # Significant decoding occurred
            # Check decoded content for injection patterns
            for pattern, reason in PROMPT_INJECTION_PATTERNS:
                if re.search(pattern, decoded):
                    return True, f'URL encoded {reason}'
    except Exception:
        pass
    
    return False, None


def validate_ai_response(response: str) -> Tuple[bool, Optional[str]]:
    """
    Validate AI response structure before command extraction.
    
    Args:
        response: AI response text
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not response:
        return False, "Empty response"
    
    # Check length
    if len(response) > MAX_AI_RESPONSE_LENGTH:
        return False, f"Response too long (max {MAX_AI_RESPONSE_LENGTH} characters)"
    
    # Check for prompt injection in response
    is_injection, reason = detect_prompt_injection(response)
    if is_injection:
        return False, f"Potential prompt injection detected: {reason}"
    
    # Check for suspicious patterns that might indicate manipulation
    # Look for attempts to modify system behavior
    suspicious_patterns = [
        (r'(?i)ignore\s+the\s+above', 'Instruction ignore attempt'),
        (r'(?i)do\s+not\s+(follow|execute|run)', 'Command blocking attempt'),
    ]
    
    for pattern, reason in suspicious_patterns:
        if re.search(pattern, response):
            return False, f"Suspicious pattern detected: {reason}"
    
    return True, None


def sanitize_command_output(output: str) -> str:
    """
    Sanitize command output before feeding back to AI.
    
    This prevents command output from being used for prompt injection.
    
    Args:
        output: Command output string
        
    Returns:
        Sanitized output string
    """
    if not output:
        return ""
    
    # Limit length to prevent token overflow
    max_output_length = 10000
    if len(output) > max_output_length:
        output = output[:max_output_length] + "\n[... output truncated ...]"
    
    # Remove control characters (except newline and tab)
    sanitized = ""
    for char in output:
        if char == '\n' or char == '\t':
            sanitized += char
        elif not CONTROL_CHARS_PATTERN.match(char):
            sanitized += char
    
    return sanitized


def validate_query_length(query: str) -> Tuple[bool, Optional[str]]:
    """
    Validate query length.
    
    Args:
        query: User query
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(query) > MAX_QUERY_LENGTH:
        return False, f"Query too long (max {MAX_QUERY_LENGTH} characters)"
    return True, None






