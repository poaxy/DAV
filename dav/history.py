"""Query history management with SQLite."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dav.config import get_history_db_path, get_history_enabled


class HistoryManager:
    """Manage query history in SQLite database."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.enabled = get_history_enabled()
        if not self.enabled:
            return
        
        self.db_path = db_path or get_history_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        if not self.enabled:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                response TEXT,
                session_id TEXT,
                executed INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON queries(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session ON queries(session_id)
        """)
        conn.commit()
        conn.close()
    
    def add_query(self, query: str, response: Optional[str] = None, 
                  session_id: Optional[str] = None, executed: bool = False) -> int:
        """Add a query to history."""
        if not self.enabled:
            return -1
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO queries (timestamp, query, response, session_id, executed)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), query, response, session_id, 1 if executed else 0))
        query_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return query_id
    
    def get_recent_queries(self, limit: int = 10) -> List[Dict]:
        """Get recent queries."""
        if not self.enabled:
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, query, response, session_id, executed
            FROM queries
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_session_queries(self, session_id: str) -> List[Dict]:
        """Get all queries for a session."""
        if not self.enabled:
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, query, response, session_id, executed
            FROM queries
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def clear_history(self) -> None:
        """Clear all history."""
        if not self.enabled:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queries")
        conn.commit()
        conn.close()

