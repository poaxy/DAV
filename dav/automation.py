"""Automation logging for Dav."""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dav.config import get_automation_log_dir, get_automation_log_retention_days


@dataclass
class CommandExecution:
    """Record of a command execution."""
    command: str
    success: bool
    return_code: int
    stdout_preview: str = ""  # First few lines of output
    stderr_preview: str = ""  # First few lines of error
    timestamp: datetime = field(default_factory=datetime.now)


class AutomationLogger:
    """Summary report logger for automation tasks."""
    
    def __init__(self):
        """Initialize logger and prepare for summary collection."""
        self.log_dir = get_automation_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up old logs on initialization
        self.cleanup_old_logs()
        
        # Create timestamped report file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_file = self.log_dir / f"dav_{timestamp}.log"
        
        # Data collection for summary
        self.start_time = datetime.now()
        self.task_query: Optional[str] = None
        self.commands: List[CommandExecution] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.ai_responses: List[str] = []
    
    def log_info(self, message: str) -> None:
        """Record informational message (stored for summary, not logged immediately)."""
        # Only store important info, not verbose logging
        pass
    
    def log_command(self, command: str) -> None:
        """Record command for summary (not logged immediately)."""
        # Commands are recorded when we log their output
        pass
    
    def log_output(self, stdout: str, stderr: str, return_code: int) -> None:
        """Record command output for summary."""
        # Extract command from context if available
        # This will be called after command execution, so we need to track the last command
        # For now, we'll record it when we have the full execution result
        pass
    
    def record_command_execution(self, command: str, success: bool, return_code: int, 
                                 stdout: str = "", stderr: str = "") -> None:
        """Record a complete command execution for the summary."""
        # Get preview of output (first 3 lines or first 200 chars)
        stdout_preview = ""
        if stdout:
            lines = stdout.strip().split("\n")
            if len(lines) <= 3:
                stdout_preview = stdout.strip()
            else:
                stdout_preview = "\n".join(lines[:3]) + f"\n... ({len(lines) - 3} more lines)"
            if len(stdout_preview) > 200:
                stdout_preview = stdout_preview[:200] + "..."
        
        stderr_preview = ""
        if stderr:
            lines = stderr.strip().split("\n")
            if len(lines) <= 3:
                stderr_preview = stderr.strip()
            else:
                stderr_preview = "\n".join(lines[:3]) + f"\n... ({len(lines) - 3} more lines)"
            if len(stderr_preview) > 200:
                stderr_preview = stderr_preview[:200] + "..."
        
        self.commands.append(CommandExecution(
            command=command,
            success=success,
            return_code=return_code,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview
        ))
    
    def log_error(self, error_message: str) -> None:
        """Record error for summary."""
        self.errors.append(error_message)
    
    def log_warning(self, warning_message: str) -> None:
        """Record warning for summary."""
        self.warnings.append(warning_message)
    
    def record_ai_response(self, response: str) -> None:
        """Record AI response preview."""
        preview = response[:300] + "..." if len(response) > 300 else response
        self.ai_responses.append(preview)
    
    def set_task(self, task_query: str) -> None:
        """Set the task query for this automation run."""
        self.task_query = task_query
    
    def get_log_path(self) -> Path:
        """Return current report file path."""
        return self.report_file
    
    def generate_summary_report(self, execution_results: Optional[List] = None) -> str:
        """Generate a summary report of the automation task."""
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        # Use execution results if provided, otherwise use collected commands
        if execution_results:
            successful_commands = sum(1 for r in execution_results if getattr(r, "success", False))
            failed_commands = len(execution_results) - successful_commands
            total_commands = len(execution_results)
        else:
            successful_commands = sum(1 for cmd in self.commands if cmd.success)
            failed_commands = len(self.commands) - successful_commands
            total_commands = len(self.commands)
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DAV AUTOMATION TASK REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        report_lines.append(f"Task: {self.task_query or 'N/A'}")
        report_lines.append(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Duration: {duration}")
        report_lines.append("")
        report_lines.append("-" * 80)
        report_lines.append("EXECUTION SUMMARY")
        report_lines.append("-" * 80)
        report_lines.append(f"Total commands executed: {total_commands}")
        report_lines.append(f"Successful: {successful_commands}")
        report_lines.append(f"Failed: {failed_commands}")
        report_lines.append("")
        
        # Command details
        if self.commands:
            report_lines.append("-" * 80)
            report_lines.append("COMMAND EXECUTIONS")
            report_lines.append("-" * 80)
            for i, cmd in enumerate(self.commands, 1):
                status = "✓ SUCCESS" if cmd.success else "✗ FAILED"
                report_lines.append(f"\n[{i}] {status} (exit code: {cmd.return_code})")
                report_lines.append(f"    Command: {cmd.command}")
                if cmd.stdout_preview:
                    report_lines.append(f"    Output preview:")
                    for line in cmd.stdout_preview.split("\n"):
                        report_lines.append(f"      {line}")
                if cmd.stderr_preview:
                    report_lines.append(f"    Error preview:")
                    for line in cmd.stderr_preview.split("\n"):
                        report_lines.append(f"      {line}")
            report_lines.append("")
        
        # Errors
        if self.errors:
            report_lines.append("-" * 80)
            report_lines.append("ERRORS")
            report_lines.append("-" * 80)
            for error in self.errors:
                report_lines.append(f"  • {error}")
            report_lines.append("")
        
        # Warnings
        if self.warnings:
            report_lines.append("-" * 80)
            report_lines.append("WARNINGS")
            report_lines.append("-" * 80)
            for warning in self.warnings:
                report_lines.append(f"  • {warning}")
            report_lines.append("")
        
        # AI Responses (brief)
        if self.ai_responses:
            report_lines.append("-" * 80)
            report_lines.append("AI RESPONSES")
            report_lines.append("-" * 80)
            for i, response in enumerate(self.ai_responses, 1):
                report_lines.append(f"\nResponse {i}:")
                report_lines.append(f"  {response}")
            report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def log_summary(self, task_query: str, execution_results: Optional[List] = None) -> None:
        """Generate and write summary report."""
        if not self.task_query:
            self.task_query = task_query
        
        report = self.generate_summary_report(execution_results)
        
        # Write report to file
        with open(self.report_file, "w", encoding="utf-8") as f:
            f.write(report)
        
        # Also print summary to console
        print("\n" + "=" * 80)
        print("AUTOMATION TASK SUMMARY")
        print("=" * 80)
        if execution_results:
            successful = sum(1 for r in execution_results if getattr(r, "success", False))
            failed = len(execution_results) - successful
            print(f"Commands executed: {len(execution_results)}")
            print(f"Successful: {successful}, Failed: {failed}")
        print(f"Report saved to: {self.report_file}")
        print("=" * 80 + "\n")
    
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
    
    def close(self) -> None:
        """Close logger and ensure report is written."""
        # Report is written in log_summary, so nothing to close here
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

