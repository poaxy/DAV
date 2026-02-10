"""AI backend integration for OpenAI, Anthropic, and Gemini."""

from typing import Iterator, Optional

from anthropic import Anthropic
from openai import OpenAI

from dav.config import get_api_key, get_default_model, get_default_backend
from dav.failover import FailoverManager, is_failover_error
from dav.terminal import render_warning


# Exception hierarchy for API errors
class APIError(Exception):
    """Base exception for all API errors."""
    pass


class NetworkError(APIError):
    """Network-related errors (connection, timeout, etc.)."""
    pass


class RateLimitError(APIError):
    """Rate limit errors."""
    pass


class AuthenticationError(APIError):
    """Authentication errors (invalid API key, etc.)."""
    pass


class ServerError(APIError):
    """Server errors (5xx, service unavailable, etc.)."""
    pass


class AIBackend:
    """Base class for AI backends."""
    
    def __init__(self, backend: Optional[str] = None, model: Optional[str] = None):
        self.backend = backend or get_default_backend()
        self.model = model or get_default_model(self.backend)
        self.api_key = get_api_key(self.backend)
        
        if not self.api_key:
            if self.backend == "gemini":
                import os
                alt_key = os.getenv("GOOGLE_API_KEY")
                if alt_key:
                    self.api_key = alt_key
            
        if not self.api_key:
            backend_env = (
                "GEMINI_API_KEY or GOOGLE_API_KEY"
                if self.backend == "gemini"
                else f"{self.backend.upper()}_API_KEY"
            )
            error_msg = (
                f"API key not found for backend: {self.backend}.\n"
                f"Please set {backend_env} in your .env file.\n"
                f"Run 'dav --setup' to configure Dav, or create ~/.dav/.env manually."
            )
            raise ValueError(error_msg)
        
        if self.backend == "openai":
            self.client = OpenAI(api_key=self.api_key)
        elif self.backend == "anthropic":
            self.client = Anthropic(api_key=self.api_key)
        elif self.backend == "gemini":
            try:
                from google import generativeai as genai
            except Exception as e:
                raise ValueError(
                    "Gemini backend selected but 'google-generativeai' is not installed. "
                    "Install it with 'pip install google-generativeai' and try again."
                ) from e
            
            genai.configure(api_key=self.api_key)
            self.client = genai
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
    
    def stream_response(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream response from AI backend."""
        if self.backend == "openai":
            return self._stream_openai(prompt, system_prompt)
        elif self.backend == "anthropic":
            return self._stream_anthropic(prompt, system_prompt)
        elif self.backend == "gemini":
            return self._stream_gemini(prompt, system_prompt)
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
    
    def _stream_openai(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream response from OpenAI."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.3,
                max_tokens=4096,
                top_p=0.9,
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            # Map OpenAI exceptions to our exception types
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            if "rate limit" in error_str or "429" in error_str or "RateLimitError" in error_type:
                raise RateLimitError(f"OpenAI rate limit: {e}") from e
            elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str or "AuthenticationError" in error_type:
                raise AuthenticationError(f"OpenAI authentication error: {e}") from e
            elif "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str or "server" in error_str:
                raise ServerError(f"OpenAI server error: {e}") from e
            elif "connection" in error_str or "timeout" in error_str or "network" in error_str or "ConnectionError" in error_type or "TimeoutError" in error_type:
                raise NetworkError(f"OpenAI network error: {e}") from e
            else:
                raise APIError(f"OpenAI API error: {e}") from e
    
    def _stream_anthropic(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream response from Anthropic."""
        system = system_prompt or ""
        
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            # Map Anthropic exceptions to our exception types
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            if "rate limit" in error_str or "429" in error_str or "RateLimitError" in error_type:
                raise RateLimitError(f"Anthropic rate limit: {e}") from e
            elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str or "authentication" in error_str or "AuthenticationError" in error_type:
                raise AuthenticationError(f"Anthropic authentication error: {e}") from e
            elif "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str or "server" in error_str:
                raise ServerError(f"Anthropic server error: {e}") from e
            elif "connection" in error_str or "timeout" in error_str or "network" in error_str or "ConnectionError" in error_type or "TimeoutError" in error_type:
                raise NetworkError(f"Anthropic network error: {e}") from e
            else:
                raise APIError(f"Anthropic API error: {e}") from e
    
    def _stream_gemini(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream response from Gemini (Google AI)."""
        try:
            from google import generativeai as genai  # type: ignore
        except Exception as e:
            raise APIError(f"Gemini backend not available: {e}") from e
        
        genai.configure(api_key=self.api_key)
        
        try:
            if system_prompt:
                model = genai.GenerativeModel(model_name=self.model, system_instruction=system_prompt)
                response = model.generate_content(prompt, stream=True)
            else:
                model = genai.GenerativeModel(model_name=self.model)
                response = model.generate_content(prompt, stream=True)
            
            for chunk in response:
                text = ""
                if hasattr(chunk, "text") and chunk.text:
                    text = chunk.text
                elif hasattr(chunk, "candidates") and chunk.candidates:
                    try:
                        parts = chunk.candidates[0].content.parts  # type: ignore[attr-defined]
                        text = "".join(getattr(p, "text", "") for p in parts)
                    except Exception:
                        text = ""
                if text:
                    yield text
        except APIError:
            # Re-raise APIError as-is
            raise
        except Exception as e:
            # Map Gemini exceptions to our exception types
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            if "rate limit" in error_str or "429" in error_str or "quota" in error_str or "RateLimitError" in error_type:
                raise RateLimitError(f"Gemini rate limit: {e}") from e
            elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str or "authentication" in error_str or "api key" in error_str or "AuthenticationError" in error_type:
                raise AuthenticationError(f"Gemini authentication error: {e}") from e
            elif "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str or "server" in error_str:
                raise ServerError(f"Gemini server error: {e}") from e
            elif "connection" in error_str or "timeout" in error_str or "network" in error_str or "ConnectionError" in error_type or "TimeoutError" in error_type:
                raise NetworkError(f"Gemini network error: {e}") from e
            else:
                raise APIError(f"Gemini API error: {e}") from e
    
    def get_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Get complete response from AI backend (non-streaming)."""
        if self.backend == "openai":
            return self._get_openai(prompt, system_prompt)
        elif self.backend == "anthropic":
            return self._get_anthropic(prompt, system_prompt)
        elif self.backend == "gemini":
            return self._get_gemini(prompt, system_prompt)
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
    
    def _get_openai(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Get complete response from OpenAI."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
                top_p=0.9,
            )
            return response.choices[0].message.content
        except Exception as e:
            # Map OpenAI exceptions to our exception types
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            if "rate limit" in error_str or "429" in error_str or "RateLimitError" in error_type:
                raise RateLimitError(f"OpenAI rate limit: {e}") from e
            elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str or "AuthenticationError" in error_type:
                raise AuthenticationError(f"OpenAI authentication error: {e}") from e
            elif "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str or "server" in error_str:
                raise ServerError(f"OpenAI server error: {e}") from e
            elif "connection" in error_str or "timeout" in error_str or "network" in error_str or "ConnectionError" in error_type or "TimeoutError" in error_type:
                raise NetworkError(f"OpenAI network error: {e}") from e
            else:
                raise APIError(f"OpenAI API error: {e}") from e
    
    def _get_anthropic(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Get complete response from Anthropic."""
        system = system_prompt or ""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return message.content[0].text
        except Exception as e:
            # Map Anthropic exceptions to our exception types
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            if "rate limit" in error_str or "429" in error_str or "RateLimitError" in error_type:
                raise RateLimitError(f"Anthropic rate limit: {e}") from e
            elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str or "authentication" in error_str or "AuthenticationError" in error_type:
                raise AuthenticationError(f"Anthropic authentication error: {e}") from e
            elif "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str or "server" in error_str:
                raise ServerError(f"Anthropic server error: {e}") from e
            elif "connection" in error_str or "timeout" in error_str or "network" in error_str or "ConnectionError" in error_type or "TimeoutError" in error_type:
                raise NetworkError(f"Anthropic network error: {e}") from e
            else:
                raise APIError(f"Anthropic API error: {e}") from e
    
    def _get_gemini(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Get complete response from Gemini (Google AI)."""
        try:
            from google import generativeai as genai  # type: ignore
        except Exception as e:
            raise APIError(f"Gemini backend not available: {e}") from e
        
        genai.configure(api_key=self.api_key)
        
        try:
            if system_prompt:
                model = genai.GenerativeModel(model_name=self.model, system_instruction=system_prompt)
                response = model.generate_content(prompt)
            else:
                model = genai.GenerativeModel(model_name=self.model)
                response = model.generate_content(prompt)
            
            if hasattr(response, "text") and response.text:
                return response.text
            try:
                if response.candidates:  # type: ignore[attr-defined]
                    parts = response.candidates[0].content.parts  # type: ignore[attr-defined]
                    text = "".join(getattr(p, "text", "") for p in parts)
                    if text:
                        return text
            except Exception:
                pass
            raise APIError("Empty response from Gemini backend")
        except APIError:
            # Re-raise APIError as-is
            raise
        except Exception as e:
            # Map Gemini exceptions to our exception types
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            if "rate limit" in error_str or "429" in error_str or "quota" in error_str or "RateLimitError" in error_type:
                raise RateLimitError(f"Gemini rate limit: {e}") from e
            elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str or "authentication" in error_str or "api key" in error_str or "AuthenticationError" in error_type:
                raise AuthenticationError(f"Gemini authentication error: {e}") from e
            elif "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str or "server" in error_str:
                raise ServerError(f"Gemini server error: {e}") from e
            elif "connection" in error_str or "timeout" in error_str or "network" in error_str or "ConnectionError" in error_type or "TimeoutError" in error_type:
                raise NetworkError(f"Gemini network error: {e}") from e
            else:
                raise APIError(f"Gemini API error: {e}") from e


class FailoverAIBackend:
    """Failover-aware wrapper around AIBackend."""
    
    def __init__(self, backend: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize failover-aware backend.
        
        Args:
            backend: Initial backend to use (defaults to configured default)
            model: Model to use (defaults to backend's default model)
        """
        initial_backend = backend or get_default_backend()
        self.initial_model = model  # Store initial model preference
        self.failover_manager = FailoverManager(initial_backend)
        self._backend: Optional[AIBackend] = None
        self._initialize_backend()
    
    def _initialize_backend(self, use_initial_model: bool = True) -> None:
        """
        Initialize or reinitialize the backend with current provider.
        
        Args:
            use_initial_model: If True and initial_model is set, use it; otherwise use provider default
        """
        current_backend = self.failover_manager.get_current_backend()
        try:
            # Use initial model if specified and this is the first initialization
            # Otherwise use default model for the provider
            model_to_use = self.initial_model if use_initial_model and self.initial_model else None
            self._backend = AIBackend(backend=current_backend, model=model_to_use)
        except ValueError as e:
            # If initial backend fails, try to switch to backup
            if self.failover_manager.has_backups():
                backup = self.failover_manager.switch_to_backup()
                if backup:
                    render_warning(
                        f"⚠ Primary provider ({current_backend}) unavailable. "
                        f"Switching to backup provider ({backup})."
                    )
                    # When switching to backup, use default model for that provider
                    self._backend = AIBackend(backend=backup, model=None)
                else:
                    raise ValueError(f"All providers failed. Last error: {e}") from e
            else:
                raise
    
    @property
    def backend(self) -> str:
        """Get current backend name."""
        return self.failover_manager.get_current_backend()
    
    @property
    def model(self) -> str:
        """Get current model name."""
        if self._backend:
            return self._backend.model
        return get_default_model(self.backend)
    
    def stream_response(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """
        Stream response with automatic failover.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Yields:
            Response chunks as strings
            
        Raises:
            APIError: If all providers fail
        """
        return self._try_with_failover(
            lambda backend: backend.stream_response(prompt, system_prompt),
            is_streaming=True
        )
    
    def get_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Get complete response with automatic failover.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Complete response string
            
        Raises:
            APIError: If all providers fail
        """
        return self._try_with_failover(
            lambda backend: backend.get_response(prompt, system_prompt),
            is_streaming=False
        )
    
    def _try_with_failover(self, func, is_streaming: bool = False):
        """
        Try executing a function with failover support.
        
        Args:
            func: Function to execute (takes AIBackend as argument)
            is_streaming: Whether the function returns an iterator
            
        Returns:
            Function result (string or iterator)
            
        Raises:
            APIError: If all providers fail
        """
        attempted_backends = []
        last_error = None
        
        while True:
            current_backend_name = self.failover_manager.get_current_backend()
            
            # Skip if we've already tried this backend
            if current_backend_name in attempted_backends:
                break
            
            attempted_backends.append(current_backend_name)
            
            try:
                if not self._backend or self._backend.backend != current_backend_name:
                    # Reinitialize backend if needed (use default model for new provider)
                    try:
                        self._backend = AIBackend(backend=current_backend_name, model=None)
                    except ValueError as ve:
                        # Configuration error (e.g., missing API key) - mark as failed and try next
                        self.failover_manager.mark_failed(current_backend_name)
                        backup = self.failover_manager.switch_to_backup()
                        if backup:
                            render_warning(
                                f"⚠ Provider ({current_backend_name}) not properly configured. "
                                f"Switching to backup provider ({backup})."
                            )
                            continue
                        else:
                            raise ValueError(f"Provider ({current_backend_name}) not configured and no backups available: {ve}") from ve
                
                result = func(self._backend)
                
                # For streaming, we need to wrap the iterator to catch errors during iteration
                if is_streaming:
                    return self._stream_with_failover(result, current_backend_name)
                
                return result
                
            except APIError as e:
                last_error = e
                
                # Check if this error should trigger failover
                if not is_failover_error(e):
                    # Non-failover error, re-raise immediately
                    raise
                
                # Mark this backend as failed
                self.failover_manager.mark_failed(current_backend_name)
                
                # Try to switch to backup
                backup = self.failover_manager.switch_to_backup()
                if backup:
                    render_warning(
                        f"⚠ Primary provider ({current_backend_name}) unavailable "
                        f"({str(e)[:100]}...). Switching to backup provider ({backup})."
                    )
                    # Continue loop to try backup
                    continue
                else:
                    # No more backups available
                    break
        
        # All providers failed
        failed_list = ", ".join(attempted_backends)
        error_msg = (
            f"All configured providers failed: {failed_list}. "
            f"Last error: {last_error}"
        )
        raise APIError(error_msg) from last_error
    
    def _stream_with_failover(self, iterator: Iterator[str], backend_name: str) -> Iterator[str]:
        """
        Wrap streaming iterator to catch errors during iteration.
        
        Args:
            iterator: The streaming iterator
            backend_name: Name of backend providing the iterator
            
        Yields:
            Response chunks
            
        Raises:
            APIError: If all providers fail during streaming
        """
        try:
            for chunk in iterator:
                yield chunk
        except APIError as e:
            # Error occurred during streaming
            if not is_failover_error(e):
                # Non-failover error, re-raise immediately
                raise
            
            # Mark backend as failed
            self.failover_manager.mark_failed(backend_name)
            
            # Try to get backup and retry
            backup = self.failover_manager.switch_to_backup()
            if backup:
                render_warning(
                    f"⚠ Provider ({backend_name}) failed during streaming "
                    f"({str(e)[:100]}...). Switching to backup provider ({backup})."
                )
                
                # Reinitialize backend and retry
                # Note: We can't retry the same prompt easily in streaming mode,
                # so we'll raise an error and let the caller handle retry
                raise APIError(
                    f"Provider ({backend_name}) failed during streaming. "
                    f"Please retry your request - it will use backup provider ({backup})."
                ) from e
            else:
                raise APIError(
                    f"All providers failed. Last error during streaming: {e}"
                ) from e


def get_system_prompt(
    execute_mode: bool = False,
    interactive_mode: bool = False,
    automation_mode: bool = False,
    log_mode: bool = False,
) -> str:
    """Get system prompt for Dav.

    The prompt is intentionally structured as:
    1) A compact core identity shared by all modes
    2) Optional execution rules (only for EXEC / automation modes)
    3) A small, mode-specific section

    Keep new additions short and avoid duplicating content between modes.
    """

    # ------------------------------------------------------------------
    # 1. Core identity (shared across all modes)
    # ------------------------------------------------------------------
    CORE_IDENTITY = """You are Dav, a professional assistant for:
- System administration (Linux and macOS)
- Cybersecurity (vulnerability analysis, hardening, incident response)
- Network administration (configuration, troubleshooting, optimization)
- Log and diagnostics analysis

**How you think and respond (always):**
- Carefully analyze the user request and available context before acting.
- Break work into clear steps and consider risks and dependencies.
- Be honest about uncertainty; separate observed facts from interpretation.
- Use OS/distro information to tailor commands and advice.

**Safety rules (always):**
- Do NOT perform destructive operations unless the user explicitly asks and understands the impact.
- Treat production systems as sensitive; choose the safest reasonable interpretation when a request is ambiguous.
- It is better to ask for clarification than to guess on high‑risk actions.

**Never perform these without explicit confirmation:**
- System reboot/shutdown or factory reset.
- Formatting or wiping disks or partitions.
- Deleting core system directories (/, /etc, /usr, /var, /boot, /sys, /proc).
- Removing critical kernel/system packages.
- Permanently breaking network connectivity.
- Changing root authentication or disabling major security controls (firewall, SELinux, AppArmor, etc.).
- Large system time jumps that can disrupt services."""

    # ------------------------------------------------------------------
    # 2. Execution rules (only used when commands are actually executed)
    # ------------------------------------------------------------------
    EXECUTION_RULES = """

**COMMAND EXECUTION GUIDELINES (EXEC / automation modes):**
- You are in a live shell environment, not writing a long shell script.
- Prefer simple, explicit commands (`ls`, `test -f file`, `command -v app`, etc.).
- Use `&&`, `||` and `;` for simple conditionals instead of full `if ... fi` blocks,
  unless you are explicitly creating a script file.
- Include `sudo` when elevated privileges are required and respect the detected OS family
  (apt/apt-get on Debian/Ubuntu, yum/dnf on RHEL/Fedora, pacman on Arch, `brew` on macOS, etc.).
- Avoid quiet flags (`-q`, `--quiet`) so output can be inspected and logged.

**Required output format when you decide to execute commands:**
1. Briefly explain what you are going to do and why.
2. Immediately before the commands, include this exact marker on its own line: >>>EXEC<<<
3. Put ALL commands in a ```bash code block right after the marker.
   - Chain or list commands needed to complete the task.
   - For scripts, write the script file then `chmod +x` and execute it.
4. End with a ```json block containing a command plan using exactly this schema:
   {
     "commands": ["command1", "command2", "command3", ...],
     "sudo": true|false,
     "platform": ["ubuntu"]|["debian"]|["macos"]|["darwin"]|["linux"]|["unix"]|...,
     "cwd": "/optional/path",
     "notes": "Brief explanation of what all commands do together"
   }

**Feedback loop:**
- After commands run, you will receive their output.
- Analyze the output, decide on next steps, and, if needed, emit another >>>EXEC<<< block.
- Explicitly state when a task is complete (e.g., “Task complete. No further commands needed.”)."""

    # ------------------------------------------------------------------
    # 3. Mode-specific sections
    # ------------------------------------------------------------------
    if automation_mode:
        return CORE_IDENTITY + EXECUTION_RULES + """

**MODE: AUTOMATION MODE (non-interactive)**
- Commands execute automatically without per-step confirmation.
- Focus on actionable maintenance and remediation tasks.
- Group related actions into as few command blocks as possible.
- Handle errors gracefully and summarize what was attempted and what succeeded/failed.

**Response style:**
- Professional and action-oriented.
- Keep explanations short; prioritize what was done and what the results mean.
- When applicable, treat the task as:
  - Log analysis
  - Command execution / maintenance
  - Troubleshooting
and tailor the length accordingly (roughly 50–200 words unless more detail is clearly needed)."""

    if execute_mode and interactive_mode:
        return CORE_IDENTITY + EXECUTION_RULES + """

**MODE: INTERACTIVE EXECUTE MODE**
- Multi-turn conversation where you both discuss and execute commands.
- When the user clearly asks you to **do** something (check, analyze, run, execute, install, update, create, fix, diagnose, etc.), you MUST:
  - Decide on safe, concrete commands.
  - Use the >>>EXEC<<< marker, bash block, and JSON plan format exactly as specified.
- Ask clarifying questions when the request is ambiguous or carries significant risk.

**Response style:**
- Conversational and explanatory, but still concise.
- For log analysis or troubleshooting, run diagnostics first, then explain findings and fixes.
- For one-off actions (install/update/etc.), briefly describe the plan, execute, then summarize the outcome."""

    if execute_mode:
        return CORE_IDENTITY + EXECUTION_RULES + """

**MODE: EXECUTE MODE (single query)**
- Single-turn command execution with real-time output.
- When the user asks you to perform an action, you MUST execute it using the >>>EXEC<<< / bash / JSON plan pattern.
- Keep explanations brief and focus on what will run and what the results mean.
- Only omit execution if the user clearly requested information-only help (“what is X”, “explain Y”) without asking you to act."""

    # Analysis-only modes (no command execution)
    if log_mode:
        return CORE_IDENTITY + """

**MODE: LOG ANALYSIS MODE (stdin logs, analysis-only)**
- You receive log content via stdin and should explain it in clear, human terms.
- Default to a short overview (roughly 150–300 words) unless the user explicitly asks for a deep dive.

**Default behavior:**
- Describe what the logs appear to represent (component/service, phase such as startup/steady state/shutdown/error burst).
- Call out dominant themes: presence of errors/warnings, repetition patterns, and any obvious risks.
- Highlight only the most important issues instead of cataloguing every line.

**When the user asks for detailed analysis (e.g., “explain in detail”, “deep dive”):**
- Provide a short executive summary followed by structured sections:
  - Key findings and error/warning themes
  - Likely root causes and impact (stability, performance, security)
  - Recommended next steps or checks
- You still do **not** execute commands in this mode; you only suggest them if helpful."""

    # Default: general ANALYSIS mode (no execution)
    return CORE_IDENTITY + """

**MODE: ANALYSIS MODE (default, no execution)**
- You provide explanations, guidance, and recommendations only.
- You may suggest commands in small `bash` snippets, but you never use the >>>EXEC<<< marker or claim to have executed anything.

**Style: concise and practical by default**
- Internally think step by step, but keep answers short and direct (often 2–4 sentences).
- Use bullets or short lists for troubleshooting steps instead of long essays.
- When commands help, show 1–3 lines tailored to the detected OS/distro and briefly state what they do.

**When to expand:**
- If the user clearly requests depth (e.g., “explain in detail”, “deep dive”), you may provide a longer, structured answer with sections like Summary / Details / Steps.

**Uncertainty & safety in analysis mode:**
- Be explicit when you are unsure or when multiple interpretations exist.
- Suggest what additional information or logs would reduce uncertainty.
- Never downplay risk; align all recommendations with the safety rules in the core identity."""

