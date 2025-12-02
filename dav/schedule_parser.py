"""Schedule parsing utilities with hybrid AI + dateparser + regex fallback chain."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import dateparser

from dav.ai_backend import AIBackend


@dataclass
class ScheduleParseResult:
    """Result of schedule parsing."""
    success: bool
    task: Optional[str] = None
    schedule: Optional[str] = None
    method: Optional[str] = None  # "ai", "dateparser", "regex", or None
    error: Optional[str] = None
    attempts: int = 0


def validate_and_normalize_cron(cron_string: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize cron syntax.
    
    Args:
        cron_string: Cron schedule string (e.g., "0 3 * * *")
    
    Returns:
        Tuple of (is_valid, normalized_cron, error_message)
    """
    if not cron_string:
        return False, None, "Empty cron string"
    
    cron_string = cron_string.strip()
    
    # Handle special cron strings (@daily, @weekly, etc.)
    special_strings = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }
    
    if cron_string.lower() in special_strings:
        return True, special_strings[cron_string.lower()], None
    
    # Basic cron format: minute hour day month weekday
    parts = cron_string.split()
    
    if len(parts) != 5:
        return False, None, f"Invalid cron format: expected 5 fields, got {len(parts)}"
    
    # Validate each part
    field_names = ["minute", "hour", "day", "month", "weekday"]
    ranges = [
        (0, 59),  # minute
        (0, 23),  # hour
        (1, 31),  # day
        (1, 12),  # month
        (0, 7),   # weekday (0 and 7 both mean Sunday)
    ]
    
    normalized_parts = []
    for i, (part, field_name, (min_val, max_val)) in enumerate(zip(parts, field_names, ranges)):
        # Check if part contains valid characters
        if not re.match(r'^[\d\*\/\-,]+$', part):
            return False, None, f"Invalid {field_name} field: contains invalid characters"
        
        # If it's just * or */N, it's valid
        if part == "*" or re.match(r'^\*/\d+$', part):
            normalized_parts.append(part)
            continue
        
        # Check ranges and lists
        if "," in part:
            # List of values
            values = part.split(",")
            for value in values:
                if "-" in value:
                    # Range in list
                    range_parts = value.split("-")
                    if len(range_parts) != 2:
                        return False, None, f"Invalid {field_name} range: {value}"
                    try:
                        start = int(range_parts[0])
                        end = int(range_parts[1])
                        if start < min_val or end > max_val or start > end:
                            return False, None, f"Invalid {field_name} range: {start}-{end} (must be {min_val}-{max_val})"
                    except ValueError:
                        return False, None, f"Invalid {field_name} range: {value}"
                else:
                    # Single value in list
                    try:
                        val = int(value)
                        if val < min_val or val > max_val:
                            return False, None, f"Invalid {field_name} value: {val} (must be {min_val}-{max_val})"
                    except ValueError:
                        return False, None, f"Invalid {field_name} value: {value}"
            normalized_parts.append(part)
        elif "-" in part:
            # Range
            range_parts = part.split("-")
            if len(range_parts) != 2:
                return False, None, f"Invalid {field_name} range: {part}"
            try:
                start = int(range_parts[0])
                end = int(range_parts[1])
                if start < min_val or end > max_val or start > end:
                    return False, None, f"Invalid {field_name} range: {start}-{end} (must be {min_val}-{max_val})"
            except ValueError:
                return False, None, f"Invalid {field_name} range: {part}"
            normalized_parts.append(part)
        elif "/" in part:
            # Step value (e.g., */5, 0-30/5)
            if part.startswith("*/"):
                # */N format
                try:
                    step = int(part[2:])
                    if step < 1:
                        return False, None, f"Invalid {field_name} step: {step} (must be >= 1)"
                except ValueError:
                    return False, None, f"Invalid {field_name} step: {part}"
            else:
                # N/M format (range with step)
                parts_step = part.split("/")
                if len(parts_step) != 2:
                    return False, None, f"Invalid {field_name} step format: {part}"
                try:
                    step = int(parts_step[1])
                    if step < 1:
                        return False, None, f"Invalid {field_name} step: {step} (must be >= 1)"
                    # Validate the range part
                    range_part = parts_step[0]
                    if "-" in range_part:
                        range_parts = range_part.split("-")
                        if len(range_parts) != 2:
                            return False, None, f"Invalid {field_name} range: {range_part}"
                        start = int(range_parts[0])
                        end = int(range_parts[1])
                        if start < min_val or end > max_val or start > end:
                            return False, None, f"Invalid {field_name} range: {start}-{end} (must be {min_val}-{max_val})"
                    else:
                        val = int(range_part)
                        if val < min_val or val > max_val:
                            return False, None, f"Invalid {field_name} value: {val} (must be {min_val}-{max_val})"
                except ValueError:
                    return False, None, f"Invalid {field_name} step format: {part}"
            normalized_parts.append(part)
        else:
            # Single value
            try:
                val = int(part)
                if val < min_val or val > max_val:
                    return False, None, f"Invalid {field_name} value: {val} (must be {min_val}-{max_val})"
            except ValueError:
                return False, None, f"Invalid {field_name} value: {part}"
            normalized_parts.append(part)
    
    normalized = " ".join(normalized_parts)
    return True, normalized, None


def extract_json_from_response(response: str) -> Optional[str]:
    """
    Extract JSON from AI response with robust parsing.
    
    Args:
        response: AI response text
    
    Returns:
        JSON string or None if not found
    """
    # First try to find JSON in code blocks
    json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL | re.MULTILINE)
    if json_block_match:
        return json_block_match.group(1)
    
    # Try to find inline JSON object (match balanced braces)
    brace_count = 0
    start_pos = response.find('{')
    if start_pos != -1:
        for i in range(start_pos, len(response)):
            if response[i] == '{':
                brace_count += 1
            elif response[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return response[start_pos:i+1]
    
    return None


def parse_schedule_with_ai(
    schedule_input: str,
    ai_backend: AIBackend,
    max_retries: int = 2
) -> ScheduleParseResult:
    """
    Parse schedule using AI with retry logic.
    
    Args:
        schedule_input: Natural language schedule input
        ai_backend: AI backend instance
        max_retries: Maximum number of retries (default 2, so 3 total attempts)
    
    Returns:
        ScheduleParseResult with parsing outcome
    """
    attempts = 0
    last_error = None
    
    for attempt in range(max_retries + 1):
        attempts += 1
        
        # Refine prompt on retries
        if attempt == 0:
            schedule_prompt = f"""Parse this schedule request and extract:
1. The task description (what to do)
2. The schedule in cron format (e.g., "0 3 * * *" for daily at 3 AM)

User request: {schedule_input}

IMPORTANT: The user request may contain both the task AND the schedule together.
For example: "update my system everyday at 3am" should be parsed as:
- task: "update my system"
- schedule: "0 3 * * *" (everyday at 3 AM)

Respond with ONLY a JSON object in this format:
{{
  "task": "task description here",
  "schedule": "0 3 * * *"
}}

Common schedule patterns:
- "everyday at 3am" or "every day at 3am" → "0 3 * * *"
- "every night at 3" or "daily at 3" → "0 3 * * *"
- "every day" or "everyday" → "0 0 * * *"
- "weekly" or "every week" → "0 0 * * 0"
- "monthly" → "0 0 1 * *"
- "every 6 hours" → "0 */6 * * *"
- "at 3 PM" → "0 15 * * *"
- "at 3 AM" → "0 3 * * *"
"""
        else:
            schedule_prompt = f"""Previous attempt failed: {last_error}

User request: {schedule_input}

Please parse this schedule request again. Extract:
1. The task description (what to do)
2. The schedule in cron format (e.g., "0 3 * * *" for daily at 3 AM)

IMPORTANT: Return ONLY valid JSON in this exact format:
{{
  "task": "task description here",
  "schedule": "0 3 * * *"
}}

The schedule must be in standard cron format: "minute hour day month weekday"
Examples:
- Daily at 3 AM: "0 3 * * *"
- Every 6 hours: "0 */6 * * *"
- Weekly on Monday: "0 0 * * 1"
- Monthly on 1st: "0 0 1 * *"
"""
        
        system_prompt = """You are a schedule parser. Extract the task description and convert the schedule to cron format.
The user input may contain both the task and schedule in one sentence. Separate them correctly.
Return ONLY valid JSON with "task" and "schedule" fields. Do not include any explanation or markdown formatting.
The schedule field must be a valid 5-field cron expression."""
        
        try:
            response = ai_backend.get_response(schedule_prompt, system_prompt=system_prompt)
            
            # Extract JSON
            json_str = extract_json_from_response(response)
            
            if not json_str:
                last_error = "No JSON found in response"
                continue
            
            # Parse JSON
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {str(e)}"
                continue
            
            # Extract task and schedule
            task = parsed.get("task", schedule_input)
            cron_schedule = parsed.get("schedule")
            
            if not cron_schedule:
                last_error = "No schedule field in JSON"
                continue
            
            # Validate cron syntax
            is_valid, normalized_cron, cron_error = validate_and_normalize_cron(cron_schedule)
            if not is_valid:
                last_error = f"Invalid cron syntax: {cron_error}"
                continue
            
            # Success!
            return ScheduleParseResult(
                success=True,
                task=task,
                schedule=normalized_cron,
                method="ai",
                attempts=attempts
            )
        
        except Exception as e:
            last_error = f"AI error: {str(e)}"
            continue
    
    # All attempts failed
    return ScheduleParseResult(
        success=False,
        error=f"AI parsing failed after {attempts} attempts: {last_error}",
        attempts=attempts
    )


def extract_time_with_dateparser(schedule_input: str) -> Optional[str]:
    """
    Extract time expression using dateparser and convert to cron format.
    
    Args:
        schedule_input: Natural language schedule input
    
    Returns:
        Cron format string or None if cannot parse
    """
    text = schedule_input.lower().strip()
    
    # Check for recurring patterns first (these are easier to handle)
    hour_match = re.search(r"every\s+(\d+)\s+hours?", text)
    if hour_match:
        hours = int(hour_match.group(1))
        if 1 <= hours <= 23:
            return f"0 */{hours} * * *"
    
    day_match = re.search(r"every\s+(\d+)\s+days?", text)
    if day_match:
        days = int(day_match.group(1))
        if days == 1:
            # Daily - try to extract time
            time_match = re.search(r"at\s+(\d+)\s*(am|pm)?", text)
            if time_match:
                hour = int(time_match.group(1))
                if time_match.group(2) == "pm" and hour != 12:
                    hour += 12
                elif time_match.group(2) == "am" and hour == 12:
                    hour = 0
                return f"0 {hour} * * *"
            return "0 0 * * *"  # Daily at midnight
    
    # Try to extract time phrases for dateparser
    # Look for patterns like "at 3am", "at 3 pm", "everyday at 3", etc.
    time_patterns = [
        (r"everyday\s+at\s+(\d+)\s*(am|pm)?", True),  # recurring daily
        (r"every\s+day\s+at\s+(\d+)\s*(am|pm)?", True),  # recurring daily
        (r"daily\s+at\s+(\d+)\s*(am|pm)?", True),  # recurring daily
        (r"at\s+(\d+)\s*(am|pm)", True),  # recurring daily (default)
        (r"(\d+)\s*(am|pm)", True),  # recurring daily (default)
    ]
    
    for pattern, is_recurring in time_patterns:
        match = re.search(pattern, text)
        if match:
            # Reconstruct time phrase for dateparser
            hour_str = match.group(1)
            am_pm = match.group(2) if len(match.groups()) > 1 else None
            
            # Build time string for dateparser
            if am_pm:
                time_str = f"{hour_str} {am_pm}"
            else:
                time_str = hour_str
            
            # Parse with dateparser
            parsed_date = dateparser.parse(time_str, settings={'RELATIVE_BASE': datetime.now()})
            if parsed_date:
                hour = parsed_date.hour
                minute = parsed_date.minute
                # Always return daily schedule (is_recurring is always True for these patterns)
                return f"{minute} {hour} * * *"
    
    # Try parsing the whole input with dateparser (for relative times, etc.)
    parsed_date = dateparser.parse(text, settings={'RELATIVE_BASE': datetime.now()})
    if parsed_date:
        # If it parsed successfully, convert to daily schedule at that time
        hour = parsed_date.hour
        minute = parsed_date.minute
        return f"{minute} {hour} * * *"
    
    return None


def parse_schedule_to_cron_enhanced(natural_language: str) -> Optional[str]:
    """
    Parse natural language schedule to cron format using enhanced regex patterns.
    
    This is an enhanced version of the original regex parser with more patterns.
    
    Args:
        natural_language: Natural language schedule (e.g., "every night at 3")
    
    Returns:
        Cron format string or None if cannot parse
    """
    text = natural_language.lower().strip()
    
    # Weekday list for cron mapping (cron: 0=Sunday, 1=Monday, ..., 6=Saturday, 7=Sunday)
    # Our list: Monday=0, Tuesday=1, ..., Sunday=6, so we add 1 to get cron day
    WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    
    # Enhanced patterns (order matters - more specific patterns first)
    patterns = [
        # Patterns with time specifications
        (r"everyday\s+at\s+(\d+)\s*am", lambda m: f"0 {int(m.group(1)) if int(m.group(1)) != 12 else 0} * * *"),
        (r"every\s+day\s+at\s+(\d+)\s*am", lambda m: f"0 {int(m.group(1)) if int(m.group(1)) != 12 else 0} * * *"),
        (r"everyday\s+at\s+(\d+)\s*pm", lambda m: f"0 {int(m.group(1)) + 12 if int(m.group(1)) != 12 else 12} * * *"),
        (r"every\s+day\s+at\s+(\d+)\s*pm", lambda m: f"0 {int(m.group(1)) + 12 if int(m.group(1)) != 12 else 12} * * *"),
        (r"everyday\s+at\s+(\d+)", lambda m: f"0 {int(m.group(1))} * * *"),
        (r"every\s+day\s+at\s+(\d+)", lambda m: f"0 {int(m.group(1))} * * *"),
        (r"every\s+night\s+at\s+(\d+)", lambda m: f"0 {int(m.group(1))} * * *"),
        (r"daily\s+at\s+(\d+)\s*am", lambda m: f"0 {int(m.group(1)) if int(m.group(1)) != 12 else 0} * * *"),
        (r"daily\s+at\s+(\d+)\s*pm", lambda m: f"0 {int(m.group(1)) + 12 if int(m.group(1)) != 12 else 12} * * *"),
        (r"daily\s+at\s+(\d+)", lambda m: f"0 {int(m.group(1))} * * *"),
        (r"at\s+(\d+)\s*am", lambda m: f"0 {int(m.group(1)) if int(m.group(1)) != 12 else 0} * * *"),
        (r"at\s+(\d+)\s*pm", lambda m: f"0 {int(m.group(1)) + 12 if int(m.group(1)) != 12 else 12} * * *"),
        # Every N hours
        (r"every\s+(\d+)\s+hours?", lambda m: f"0 */{m.group(1)} * * *"),
        # Every N days
        (r"every\s+(\d+)\s+days?", lambda m: "0 0 * * *" if int(m.group(1)) == 1 else None),
        # Weekday patterns (cron: 0=Sunday, 1=Monday, ..., 6=Saturday)
        (r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d+)\s*am", 
         lambda m: f"0 {int(m.group(2)) if int(m.group(2)) != 12 else 0} * * {WEEKDAYS.index(m.group(1).lower()) + 1}"),
        (r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d+)\s*pm",
         lambda m: f"0 {int(m.group(2)) + 12 if int(m.group(2)) != 12 else 12} * * {WEEKDAYS.index(m.group(1).lower()) + 1}"),
        (r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
         lambda m: f"0 0 * * {WEEKDAYS.index(m.group(1).lower()) + 1}"),
        # Patterns without time (default to midnight)
        (r"everyday", "0 0 * * *"),
        (r"every\s+day", "0 0 * * *"),
        (r"daily", "0 0 * * *"),
        (r"weekly", "0 0 * * 0"),
        (r"every\s+week", "0 0 * * 0"),
        (r"monthly", "0 0 1 * *"),
        (r"every\s+month", "0 0 1 * *"),
    ]
    
    for pattern, replacement in patterns:
        match = re.search(pattern, text)
        if match:
            if callable(replacement):
                result = replacement(match)
                if result:
                    return result
            else:
                return replacement
    
    return None


def parse_schedule(
    schedule_input: str,
    ai_backend: Optional[AIBackend] = None
) -> ScheduleParseResult:
    """
    Main entry point for schedule parsing with hybrid fallback chain.
    
    Fallback chain:
    1. Try AI parsing (with retries)
    2. If fails: Extract time phrase → Use dateparser → Convert to cron
    3. If fails: Try enhanced regex patterns
    4. If all fail: Return detailed error
    
    Args:
        schedule_input: Natural language schedule input (may include task)
        ai_backend: Optional AI backend instance (will create if not provided)
    
    Returns:
        ScheduleParseResult with parsing outcome
    """
    # Step 1: Try AI parsing (if backend available)
    ai_result = None
    if ai_backend:
        ai_result = parse_schedule_with_ai(schedule_input, ai_backend, max_retries=2)
        if ai_result.success:
            return ai_result
    
    # Step 2: Try dateparser
    cron_schedule = extract_time_with_dateparser(schedule_input)
    if cron_schedule:
        # Validate the cron schedule
        is_valid, normalized_cron, error = validate_and_normalize_cron(cron_schedule)
        if is_valid:
            # Extract task (everything except the schedule part)
            # This is a simple heuristic - AI would do better
            task = schedule_input  # Use full input as task for now
            return ScheduleParseResult(
                success=True,
                task=task,
                schedule=normalized_cron,
                method="dateparser"
            )
    
    # Step 3: Try enhanced regex patterns
    cron_schedule = parse_schedule_to_cron_enhanced(schedule_input)
    if cron_schedule:
        # Validate the cron schedule
        is_valid, normalized_cron, error = validate_and_normalize_cron(cron_schedule)
        if is_valid:
            task = schedule_input  # Use full input as task
            return ScheduleParseResult(
                success=True,
                task=task,
                schedule=normalized_cron,
                method="regex"
            )
    
    # All methods failed - provide detailed error message
    methods_tried = []
    attempts = 0
    if ai_backend and ai_result:
        methods_tried.append("AI parsing")
        attempts = ai_result.attempts
    
    methods_tried.extend(["dateparser library", "regex pattern matching"])
    
    error_msg = (
        f"Could not parse schedule after trying: {', '.join(methods_tried)}.\n"
        f"Input: '{schedule_input}'\n\n"
        f"Please use one of these formats:\n"
        f"  • 'task every day at 3am'\n"
        f"  • 'task daily at 3pm'\n"
        f"  • 'task every 6 hours'\n"
        f"  • 'task weekly'\n"
        f"  • 'task every Monday at 9am'\n"
        f"  • 'task at 3pm' (defaults to daily)"
    )
    
    return ScheduleParseResult(
        success=False,
        error=error_msg,
        attempts=attempts
    )

