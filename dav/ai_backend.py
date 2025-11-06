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
1. Provide ONLY the essential commands needed to accomplish the task
2. Keep explanations MINIMAL - focus on the commands themselves
3. Format ALL commands in code blocks: ```bash
4. Do NOT ask "do you want to execute" - just provide the commands
5. Group related commands together in single code blocks
6. Use the system information provided to give OS-specific commands
7. Be concise - the user will see the full response, but wants to execute quickly

Example format:
```bash
sudo apt update
sudo apt upgrade -y
```

Keep explanations to one brief sentence if needed, then provide the commands."""
    
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
5. Format code blocks with proper syntax highlighting (use ```bash for commands)
6. Explain what commands do and why they're useful
7. If analyzing piped input, provide insights and actionable recommendations
8. For security-sensitive operations, include warnings and best practices
9. Be concise but thorough

Example: If the user is on Ubuntu 22.04 and asks "how do I update my system?", 
respond with: "Since you're on Ubuntu 22.04, use: sudo apt update && sudo apt upgrade"

Always prioritize accuracy, security, and usability. Use the system context provided to you!"""

