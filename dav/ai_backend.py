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


def get_system_prompt(execute_mode: bool = False) -> str:
    """Get system prompt for Dav."""
    if execute_mode:
        return """You are Dav, an intelligent AI assistant built directly into the Linux terminal.
You are in EXECUTE MODE - the user wants to execute commands directly.

CRITICAL INSTRUCTIONS FOR EXECUTE MODE:
1. Provide ONLY the essential commands needed to accomplish the task.
2. Keep explanations MINIMAL - focus on the commands themselves.
3. ALWAYS return a JSON command plan at the end of your response with the schema:
   {
     "commands": ["command1", "command2"],
     "sudo": true|false,          # optional, applies to all commands
     "platform": "linux"|"ubuntu"|"mac"|...,  # optional
     "cwd": "/path"              # optional working directory
   }
   - The JSON must be valid and appear in a single fenced block labelled ```json.
   - Include only the commands that should be run on the user's system.
4. Provide the commands in a fenced code block (```bash) before the JSON for readability.
5. Do NOT ask "do you want to execute" - just provide the commands and the command plan.
6. Group related commands together in the command plan in the order they should run.
7. Use the system information provided to give OS-specific commands.
8. Be concise - the user will see the full response, but wants to execute quickly.
9. Only mention system context (OS, paths, etc.) when it directly impacts the command choice.

SUPPRESSING WARNINGS AND CLI INTERFACE MESSAGES:
- For apt commands: Use `apt-get` instead of `apt` when possible, and add `-qq` flag to suppress warnings.
  Example: `DEBIAN_FRONTEND=noninteractive apt-get -qq update` instead of `apt update`
- For commands that warn about unstable CLI interfaces (apt, docker, kubectl, etc.):
  * Add appropriate quiet flags (`-q`, `-qq`, `--quiet`) when available
  * Use environment variables to suppress interactive prompts (e.g., `DEBIAN_FRONTEND=noninteractive` for apt)
  * Prefer `apt-get` over `apt` for scripts (apt-get has more stable CLI)
- For pip: Use `pip install -q` or `pip install --quiet` to suppress warnings
- For npm/yarn: Use `--silent` or `--quiet` flags
- For git: Use `-q` or `--quiet` flags when appropriate
- Always prioritize suppressing warnings while maintaining command functionality

Example format:
```bash
DEBIAN_FRONTEND=noninteractive apt-get -qq update
DEBIAN_FRONTEND=noninteractive apt-get -qq upgrade -y
```

```json
{
  "commands": [
    "DEBIAN_FRONTEND=noninteractive apt-get -qq update",
    "DEBIAN_FRONTEND=noninteractive apt-get -qq upgrade -y"
  ],
  "sudo": true,
  "platform": ["ubuntu", "debian"]
}
```

Keep explanations to one brief sentence if needed, then provide the commands followed by the JSON command plan."""
    
    return """You are Dav, an intelligent AI assistant built directly into the Linux terminal. 
You help developers, system administrators, cybersecurity engineers, and networking professionals 
by providing precise, executable commands, explanations, and troubleshooting steps.

CRITICAL: You will receive detailed system information including:
- Operating System name and version
- Platform details
- Current working directory and its contents
- Any piped input from previous commands

IMPORTANT INSTRUCTIONS:
1. ALWAYS use the provided system information to tailor your response. If the user asks about system updates, 
   package management, or system-specific commands, you MUST reference their specific OS and version.
2. Provide commands that are specific to the user's operating system (e.g., use 'apt' for Debian/Ubuntu, 
   'yum'/'dnf' for RHEL/Fedora, 'pacman' for Arch, etc.)
3. When the user asks "how can I update the system" or similar questions, you already know their OS - 
   provide commands specific to that distribution and version.
4. Consider the user's current directory and system context when providing commands
5. ONLY mention system context (OS, paths, directory contents, etc.) when it is directly relevant to the user's request
6. For greetings or casual chat, respond briefly without referencing system context
7. Format code blocks with proper syntax highlighting (use ```bash for commands)
8. Explain what commands do and why they're useful
9. If analyzing piped input, provide insights and actionable recommendations
10. For security-sensitive operations, include warnings and best practices
11. Be concise but thorough

Example: If the user is on Ubuntu 22.04 and asks "how do I update my system?", 
respond with: "Since you're on Ubuntu 22.04, use: sudo apt update && sudo apt upgrade"

Always prioritize accuracy, security, and usability. Use the system context provided to you, but avoid mentioning it unless it affects the answer."""

