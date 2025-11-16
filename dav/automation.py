"""Automation logging for Dav."""

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dav.config import get_automation_log_dir, get_automation_log_retention_days


class AutomationLogger:
    """Simple text logger for automation tasks."""
    
    LOG_LEVELS = {
        "INFO": "INFO",
        "COMMAND": "COMMAND",
        "OUTPUT": "OUTPUT",
        "ERROR": "ERROR",
        "SUMMARY": "SUMMARY",
    }
    
    def __init__(self):
        """Initialize logger and create log file."""
        self.log_dir = get_automation_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up old logs on initialization
        self.cleanup_old_logs()
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"dav_{timestamp}.log"
        
        # Open log file for writing
        self.log_handle = open(self.log_file, "w", encoding="utf-8")
        
        # Log initialization
        self.log_info("Automation logger initialized")
        self.log_info(f"Log file: {self.log_file}")
    
    def _write_log(self, level: str, message: str) -> None:
        """Write log entry to file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        self.log_handle.write(log_entry)
        self.log_handle.flush()
        
        # Also print to console for manual runs
        print(log_entry.rstrip(), file=sys.stdout)
        sys.stdout.flush()
    
    def log_info(self, message: str) -> None:
        """Log informational message."""
        self._write_log(self.LOG_LEVELS["INFO"], message)
    
    def log_command(self, command: str) -> None:
        """Log command being executed."""
        self._write_log(self.LOG_LEVELS["COMMAND"], command)
    
    def log_output(self, stdout: str, stderr: str, return_code: int) -> None:
        """Log command output."""
        if stdout:
            # Log stdout line by line
            for line in stdout.split("\n"):
                if line.strip():
                    self._write_log(self.LOG_LEVELS["OUTPUT"], f"STDOUT: {line}")
        
        if stderr:
            # Log stderr line by line
            for line in stderr.split("\n"):
                if line.strip():
                    self._write_log(self.LOG_LEVELS["OUTPUT"], f"STDERR: {line}")
        
        self._write_log(self.LOG_LEVELS["OUTPUT"], f"Return code: {return_code}")
    
    def log_error(self, error_message: str) -> None:
        """Log error message."""
        self._write_log(self.LOG_LEVELS["ERROR"], error_message)
    
    def log_summary(self, task_query: str, results: Optional[List] = None) -> None:
        """Log task summary."""
        self._write_log(self.LOG_LEVELS["SUMMARY"], f"Task: {task_query}")
        
        if results:
            successful = sum(1 for r in results if getattr(r, "success", False))
            failed = len(results) - successful
            self._write_log(self.LOG_LEVELS["SUMMARY"], f"Commands executed: {len(results)}")
            self._write_log(self.LOG_LEVELS["SUMMARY"], f"Successful: {successful}, Failed: {failed}")
        else:
            self._write_log(self.LOG_LEVELS["SUMMARY"], "Task completed")
    
    def get_log_path(self) -> Path:
        """Return current log file path."""
        return self.log_file
    
    def cleanup_old_logs(self, retention_days: Optional[int] = None) -> None:
        """Remove logs older than retention period."""
        if retention_days is None:
            retention_days = get_automation_log_retention_days()
        
        if not self.log_dir.exists():
            return
        
        cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
        removed_count = 0
        
        for log_file in self.log_dir.glob("dav_*.log"):
            try:
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    removed_count += 1
            except Exception:
                # Ignore errors when cleaning up
                pass
        
        if removed_count > 0:
            self.log_info(f"Cleaned up {removed_count} old log file(s)")
    
    def close(self) -> None:
        """Close log file handle."""
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

