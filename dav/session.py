"""Session management for maintaining context across queries."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dav.config import get_max_context_messages, get_max_context_tokens, get_session_dir
from dav.executor import ExecutionResult


class SessionManager:
    """Manage conversation sessions."""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_dir = get_session_dir()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_file = self.session_dir / f"{self.session_id}.json"
        self.messages: List[Dict] = []
        # Track last save time to avoid excessive writes when many messages
        # are added in quick succession (e.g., automation feedback loop).
        self._last_save_time: float = 0.0
        self.active_provider: Optional[str] = None  # Track active provider for failover persistence
        self._load_session()
    
    def _load_session(self) -> None:
        """Load session from file if it exists."""
        if self.session_file.exists():
            # Verify permissions before loading sensitive session data
            from dav.file_security import verify_secure_permissions, check_and_warn_permissions
            check_and_warn_permissions(self.session_file, "Session file")
            
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    self.messages = data.get("messages", [])
                    self.active_provider = data.get("active_provider")
            except Exception:
                self.messages = []
                self.active_provider = None
        else:
            self.messages = []
            self.active_provider = None
    
    def _save_session(self, force: bool = False) -> None:
        """Save session to file, with simple debouncing.

        To reduce filesystem pressure during automation or tight loops, we
        avoid writing more often than once every ~0.1s unless forced.
        """
        now = time.time()
        if not force and (now - self._last_save_time) < 0.1:
            return

        try:
            data = {
                "session_id": self.session_id,
                "created_at": datetime.now().isoformat(),
                "messages": self.messages,
                "active_provider": self.active_provider,
            }
            with open(self.session_file, "w") as f:
                # Indent for readability; cost is small relative to I/O.
                json.dump(data, f, indent=2)
            
            # Set secure permissions after saving
            from dav.file_security import set_secure_permissions
            set_secure_permissions(self.session_file)
            self._last_save_time = now
        except Exception:
            # Silently fail if we can't save
            pass
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({
            "type": "message",
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        # Normal message additions can be debounced
        self._save_session()
    
    def add_execution_results(self, results: List[ExecutionResult]) -> None:
        """Add execution results to the session."""
        if not results:
            return
        
        # Format execution results
        execution_content = "## Command Execution Results\n\n"
        for result in results:
            status = "✓ Success" if result.success else "✗ Failed"
            execution_content += f"**Command:** `{result.command}`\n"
            execution_content += f"**Status:** {status} (exit code: {result.return_code})\n"
            
            if result.stderr:
                execution_content += f"**Error Output:**\n```\n{result.stderr}\n```\n"
            if result.stdout:
                # Truncate very long stdout (keep first 1000 chars and last 500 chars)
                stdout = result.stdout
                if len(stdout) > 2000:
                    stdout = stdout[:1000] + "\n[... truncated ...]\n" + stdout[-500:]
                execution_content += f"**Output:**\n```\n{stdout}\n```\n"
            execution_content += "\n"
        
        self.messages.append({
            "type": "execution",
            "role": "system",
            "content": execution_content,
            "timestamp": datetime.now().isoformat(),
            "execution_results": [
                {
                    "command": r.command,
                    "success": r.success,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                    "return_code": r.return_code,
                }
                for r in results
            ],
        })
        # Execution results are relatively infrequent but can still arrive
        # in bursts; allow debouncing as well.
        self._save_session()
    
    def get_messages(self) -> List[Dict]:
        """Get all messages in the session."""
        return self.messages.copy()
    
    def clear_session(self) -> None:
        """Clear the session."""
        self.messages = []
        self.active_provider = None
        if self.session_file.exists():
            self.session_file.unlink()
    
    def set_active_provider(self, provider: str) -> None:
        """Set the active provider for this session."""
        self.active_provider = provider
        self._save_session(force=True)
    
    def get_active_provider(self) -> Optional[str]:
        """Get the active provider for this session."""
        return self.active_provider
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation: ~4 chars per token)."""
        return len(text) // 4
    
    def _summarize_execution_result(self, msg: Dict) -> str:
        """Summarize an execution result to save tokens."""
        execution_results = msg.get("execution_results", [])
        if not execution_results:
            # Fallback to content if execution_results not available
            content = msg.get("content", "")
            return content[:1000]  # Truncate to ~250 tokens
        
        summary_lines = ["## Command Execution Results"]
        for result in execution_results:
            command = result.get("command", "")
            success = result.get("success", False)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            return_code = result.get("return_code", 1)
            
            status = "✓ Success" if success else "✗ Failed"
            summary_lines.append(f"**Command:** `{command}`")
            summary_lines.append(f"**Status:** {status} (exit code: {return_code})")
            
            # For failed commands, keep error output (important for troubleshooting)
            if not success:
                if stderr:
                    # Keep first 500 chars of stderr
                    stderr_preview = stderr[:500]
                    if len(stderr) > 500:
                        stderr_preview += "\n[... truncated ...]"
                    summary_lines.append(f"**Error:**\n```\n{stderr_preview}\n```")
                elif stdout:
                    # If no stderr, show stdout (might contain error info)
                    stdout_preview = stdout[:500]
                    if len(stdout) > 500:
                        stdout_preview += "\n[... truncated ...]"
                    summary_lines.append(f"**Output:**\n```\n{stdout_preview}\n```")
            elif success and stdout:
                # For successful commands, keep last 10 lines of output
                lines = stdout.split('\n')
                if len(lines) > 10:
                    summary_lines.append(f"**Output (last 10 lines):**\n```\n" + '\n'.join(lines[-10:]) + "\n```")
                else:
                    stdout_preview = stdout[:500]
                    if len(stdout) > 500:
                        stdout_preview += "\n[... truncated ...]"
                    summary_lines.append(f"**Output:**\n```\n{stdout_preview}\n```")
            summary_lines.append("")
        
        return "\n".join(summary_lines)
    
    def get_conversation_context(self, max_tokens: Optional[int] = None, max_messages: Optional[int] = None) -> str:
        """
        Get conversation context with intelligent truncation.
        
        Args:
            max_tokens: Maximum tokens for context (defaults to config value)
            max_messages: Maximum messages to include (defaults to config value)
        
        Returns:
            Formatted conversation context string
        """
        if not self.messages:
            return ""
        
        # Get limits from config if not provided
        if max_tokens is None:
            max_tokens = get_max_context_tokens()
        if max_messages is None:
            max_messages = get_max_context_messages()
        
        # Start with most recent messages
        recent_messages = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        
        # Build context, tracking token count
        lines = ["## Previous Conversation"]
        total_tokens = self._estimate_tokens(lines[0])
        
        # Process messages in reverse (newest first) to prioritize recent content
        included_messages = []
        for msg in reversed(recent_messages):
            msg_type = msg.get("type", "message")  # "message" or "execution"
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            # Estimate tokens for this message
            msg_tokens = self._estimate_tokens(content)
            
            # If adding this message would exceed limit, try to summarize/truncate
            if total_tokens + msg_tokens > max_tokens:
                # For execution results, try to summarize
                if msg_type == "execution":
                    content = self._summarize_execution_result(msg)
                    msg_tokens = self._estimate_tokens(content)
                
                # If still too large, truncate content
                if total_tokens + msg_tokens > max_tokens:
                    # Keep first part and indicate truncation
                    remaining_tokens = max_tokens - total_tokens - 100  # Reserve 100 for truncation notice
                    max_chars = remaining_tokens * 4
                    if len(content) > max_chars:
                        content = content[:max_chars] + "\n[... truncated ...]"
                        msg_tokens = self._estimate_tokens(content)
                
                # If we've hit the limit, stop adding older messages
                if total_tokens + msg_tokens > max_tokens:
                    break
            
            included_messages.append((role, content, msg_type))
            total_tokens += msg_tokens
        
        # Format messages (oldest to newest for readability)
        for role, content, msg_type in reversed(included_messages):
            if msg_type == "execution":
                lines.append(content)  # Execution results already formatted
            else:
                lines.append(f"**{role.title()}:** {content}")
        
        lines.append("")
        return "\n".join(lines)

