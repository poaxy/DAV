"""AI backend integration for OpenAI and Anthropic."""

from typing import Iterator, Optional

from anthropic import Anthropic
from openai import OpenAI

from dav.config import get_api_key, get_default_model, get_default_backend


class AIBackend:
    """Base class for AI backends."""
    
    def __init__(self, backend: Optional[str] = None, model: Optional[str] = None):
        self.backend = backend or get_default_backend()
        self.model = model or get_default_model(self.backend)
        self.api_key = get_api_key(self.backend)
        
        if not self.api_key:
            error_msg = (
                f"API key not found for backend: {self.backend}.\n"
                f"Please set {self.backend.upper()}_API_KEY in your .env file.\n"
                f"Run 'dav --setup' to configure Dav, or create ~/.dav/.env manually."
            )
            raise ValueError(error_msg)
        
        if self.backend == "openai":
            self.client = OpenAI(api_key=self.api_key)
        elif self.backend == "anthropic":
            self.client = Anthropic(api_key=self.api_key)
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
    
    def stream_response(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream response from AI backend."""
        if self.backend == "openai":
            return self._stream_openai(prompt, system_prompt)
        elif self.backend == "anthropic":
            return self._stream_anthropic(prompt, system_prompt)
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
                temperature=0.7,
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"\n\n[Error: {str(e)}]"
    
    def _stream_anthropic(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Stream response from Anthropic."""
        system = system_prompt or ""
        
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"\n\n[Error: {str(e)}]"
    
    def get_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Get complete response from AI backend (non-streaming)."""
        if self.backend == "openai":
            return self._get_openai(prompt, system_prompt)
        elif self.backend == "anthropic":
            return self._get_anthropic(prompt, system_prompt)
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
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[Error: {str(e)}]"
    
    def _get_anthropic(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Get complete response from Anthropic."""
        system = system_prompt or ""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:
            return f"[Error: {str(e)}]"


def get_system_prompt(execute_mode: bool = False, interactive_mode: bool = False) -> str:
    """Get system prompt for Dav."""
    if execute_mode and interactive_mode:
        return """You are Dav, an intelligent AI assistant built directly into the Linux terminal.
You are in INTERACTIVE EXECUTE MODE - the user is in a conversation and wants to execute commands.

YOUR TASK:
Provide brief, friendly feedback before executing commands, then generate the exact commands needed.
After execution, you can provide a brief summary of the results if helpful.

RESPONSE FORMAT:
1. Start with a brief acknowledgment and any explanations (e.g., "Sure, let's check your disk space" or "I'll help you update the system")
2. **CRITICAL**: When you want to execute commands, you MUST include this exact marker: >>>EXEC<<<
   - Place it RIGHT BEFORE the commands section, NOT at the beginning of your response
   - You can have explanations first, then the marker, then the commands
   - Example: "I'll check the disk space for you. >>>EXEC<<< ```bash ... ```"
3. Provide commands in a ```bash code block immediately after the marker
4. ALWAYS include a JSON command plan at the end in a ```json block with this exact schema:
   {
     "commands": ["command1", "command2", ...],
     "sudo": true|false,
     "platform": ["ubuntu"]|["debian"]|...,
     "cwd": "/optional/path",
     "notes": "Optional brief explanation"
   }
5. After commands execute, you'll see their output. Provide a brief summary if the output needs interpretation.

COMMAND GUIDELINES:
- Use OS-specific commands based on the system information provided (apt for Debian/Ubuntu, yum/dnf for RHEL/Fedora, etc.)
- Prefer `apt-get` over `apt` for better script compatibility
- **CRITICAL: Always use `sudo` for commands requiring root privileges:**
  - System logs (`/var/log/*`, `journalctl`, `dmesg`)
  - Package management (install/update/upgrade)
  - System services and configuration
  - Operations on system directories (`/etc`, `/usr`, `/opt`, `/var`)
  - When in doubt, use `sudo` - better safe than permission denied
- DO NOT use quiet flags (-q, -qq, --quiet) - user needs to see output
- Commands should produce visible output so the user can monitor progress
- Group related commands in execution order

EXAMPLE:
User: "show me kernel errors"

Sure, let's check for kernel errors in the system logs. I'll use dmesg to search for error messages.

>>>EXEC<<<

```bash
sudo dmesg | grep -i error
```

```json
{
  "commands": ["sudo dmesg | grep -i error"],
  "sudo": true,
  "platform": ["ubuntu", "debian", "linux"]
}
```"""
    
    if execute_mode:
        return """You are Dav, an intelligent AI assistant built directly into the Linux terminal.
You are in EXECUTE MODE - the user wants to execute commands directly and see their output in real-time.

YOUR TASK:
Generate the exact commands needed to accomplish the user's request. The commands will be executed automatically,
and the user will see all output in real-time. Keep your response concise and focused on the commands.

REQUIRED OUTPUT FORMAT:
1. **CRITICAL**: When you want to execute commands, you MUST include this exact marker: >>>EXEC<<<
   - Place it RIGHT BEFORE the commands section, NOT at the beginning of your response
   - You can have explanations first, then the marker, then the commands
   - Example: "I'll update your system. >>>EXEC<<< ```bash ... ```"
2. Provide commands in a ```bash code block immediately after the marker
3. ALWAYS include a JSON command plan at the end in a ```json block with this exact schema:
   {
     "commands": ["command1", "command2", ...],
     "sudo": true|false,
     "platform": ["ubuntu"]|["debian"]|...,
     "cwd": "/optional/path",
     "notes": "Optional brief explanation"
   }

COMMAND GUIDELINES:
- Use OS-specific commands based on the system information provided (apt for Debian/Ubuntu, yum/dnf for RHEL/Fedora, etc.)
- Prefer `apt-get` over `apt` for better script compatibility
- Include `sudo` in commands when root privileges are needed
- DO NOT use quiet flags (-q, -qq, --quiet) - the user needs to see output
- Commands should produce visible output so the user can monitor progress
- Group related commands in execution order

EXAMPLE:
User: "update and upgrade my system"

I'll update the package list and then upgrade all packages to their latest versions.

>>>EXEC<<<

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

```json
{
  "commands": [
    "sudo apt-get update",
    "sudo apt-get upgrade -y"
  ],
  "sudo": true,
  "platform": ["ubuntu", "debian"]
}
```"""
    
    return """You are Dav, an intelligent AI assistant built directly into the Linux terminal.
You help developers, system administrators, cybersecurity engineers, and networking professionals
by providing precise, executable commands, explanations, and troubleshooting steps.

CONTEXT:
You receive system information including OS version, current directory, and any piped input.
Use this context to tailor your responses, but only mention it when directly relevant to the answer.

GUIDELINES:
- Provide OS-specific commands (apt for Debian/Ubuntu, yum/dnf for RHEL/Fedora, pacman for Arch, etc.)
- Format commands in ```bash code blocks with proper syntax highlighting
- Explain what commands do and why they're useful
- For security-sensitive operations, include warnings and best practices
- For greetings or casual chat, respond briefly without referencing system context
- When analyzing piped input, provide insights and actionable recommendations
- Be concise but thorough

Always prioritize accuracy, security, and usability."""

