"""Session management for maintaining context across queries."""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dav.config import get_session_dir


class SessionManager:
    """Manage conversation sessions."""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_dir = get_session_dir()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_file = self.session_dir / f"{self.session_id}.json"
        self.messages: List[Dict] = []
        self._load_session()
    
    def _load_session(self) -> None:
        """Load session from file if it exists."""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    self.messages = data.get("messages", [])
            except Exception:
                self.messages = []
        else:
            self.messages = []
    
    def _save_session(self) -> None:
        """Save session to file."""
        try:
            data = {
                "session_id": self.session_id,
                "created_at": datetime.now().isoformat(),
                "messages": self.messages,
            }
            with open(self.session_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            # Silently fail if we can't save
            pass
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_session()
    
    def get_messages(self) -> List[Dict]:
        """Get all messages in the session."""
        return self.messages.copy()
    
    def clear_session(self) -> None:
        """Clear the session."""
        self.messages = []
        if self.session_file.exists():
            self.session_file.unlink()
    
    def get_conversation_context(self) -> str:
        """Get conversation context as a formatted string."""
        if not self.messages:
            return ""
        
        lines = ["## Previous Conversation"]
        for msg in self.messages[-5:]:  # Last 5 messages for context
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"**{role.title()}:** {content[:200]}...")
        lines.append("")
        return "\n".join(lines)

