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
    stdout_preview: str = ""
    stderr_preview: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class AutomationLogger:
    """Summary report logger for automation tasks."""
    
    def __init__(self):
        """Initialize logger and prepare for summary collection."""
        self.log_dir = get_automation_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.cleanup_old_logs()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_file = self.log_dir / f"dav_{timestamp}.log"
        
        self.start_time = datetime.now()
        self.task_query: Optional[str] = None
        self.commands: List[CommandExecution] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.ai_responses: List[str] = []
    
    def log_info(self, message: str) -> None:
        """Record informational message (stored for summary, not logged immediately)."""
        pass
    
    def log_command(self, command: str) -> None:
        """Record command for summary (not logged immediately)."""
        pass
    
    def log_output(self, stdout: str, stderr: str, return_code: int) -> None:
        """Record command output for summary."""
        pass
    
    def record_command_execution(self, command: str, success: bool, return_code: int, 
                                 stdout: str = "", stderr: str = "") -> None:
        """Record a complete command execution for the summary."""
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
        
        if self.errors:
            report_lines.append("-" * 80)
            report_lines.append("ERRORS")
            report_lines.append("-" * 80)
            for error in self.errors:
                report_lines.append(f"  • {error}")
            report_lines.append("")
        
        if self.warnings:
            report_lines.append("-" * 80)
            report_lines.append("WARNINGS")
            report_lines.append("-" * 80)
            for warning in self.warnings:
                report_lines.append(f"  • {warning}")
            report_lines.append("")
        
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
    
    def generate_ai_summary(self, task_query: str, execution_results: Optional[List] = None) -> str:
        """Generate AI-powered summary of the automation task."""
        try:
            from dav.ai_backend import AIBackend
            
            summary_data = []
            summary_data.append(f"Task: {task_query}")
            summary_data.append(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            summary_data.append("")
            
            if execution_results:
                successful = sum(1 for r in execution_results if getattr(r, "success", False))
                failed = len(execution_results) - successful
                summary_data.append(f"Total commands executed: {len(execution_results)}")
                summary_data.append(f"Successful: {successful}, Failed: {failed}")
                summary_data.append("")
                summary_data.append("Command Execution Details:")
                for i, result in enumerate(execution_results, 1):
                    status = "SUCCESS" if result.success else "FAILED"
                    summary_data.append(f"\n[{i}] {status} (exit code: {result.return_code})")
                    summary_data.append(f"    Command: {result.command}")
                    if result.stdout:
                        output_lines = result.stdout.strip().split("\n")
                        preview = "\n".join(output_lines[:5])
                        if len(output_lines) > 5:
                            preview += f"\n    ... ({len(output_lines) - 5} more lines)"
                        summary_data.append(f"    Output: {preview}")
                    if result.stderr:
                        error_lines = result.stderr.strip().split("\n")
                        preview = "\n".join(error_lines[:3])
                        if len(error_lines) > 3:
                            preview += f"\n    ... ({len(error_lines) - 3} more lines)"
                        summary_data.append(f"    Error: {preview}")
            elif self.commands:
                successful = sum(1 for cmd in self.commands if cmd.success)
                failed = len(self.commands) - successful
                summary_data.append(f"Total commands executed: {len(self.commands)}")
                summary_data.append(f"Successful: {successful}, Failed: {failed}")
                summary_data.append("")
                summary_data.append("Command Execution Details:")
                for i, cmd in enumerate(self.commands, 1):
                    status = "SUCCESS" if cmd.success else "FAILED"
                    summary_data.append(f"\n[{i}] {status} (exit code: {cmd.return_code})")
                    summary_data.append(f"    Command: {cmd.command}")
                    if cmd.stdout_preview:
                        summary_data.append(f"    Output: {cmd.stdout_preview}")
                    if cmd.stderr_preview:
                        summary_data.append(f"    Error: {cmd.stderr_preview}")
            
            if self.errors:
                summary_data.append("")
                summary_data.append("Errors encountered:")
                for error in self.errors:
                    summary_data.append(f"  - {error}")
            
            if self.warnings:
                summary_data.append("")
                summary_data.append("Warnings:")
                for warning in self.warnings:
                    summary_data.append(f"  - {warning}")
            
            execution_summary = "\n".join(summary_data)
            prompt = f"""Based on the following automation task execution, provide a clear, concise summary in plain English.

{execution_summary}

Please provide a summary that:
1. Explains what the task was trying to accomplish
2. Lists what commands were executed and their outcomes
3. Explains what the results mean (success, failure, what was accomplished)
4. Notes any errors or issues encountered
5. Concludes with the overall status of the task

Keep it concise but informative. Write it as a natural summary report, not a technical log."""
            
            try:
                from dav.ai_backend import FailoverAIBackend
                ai_backend = FailoverAIBackend()
                ai_summary = ai_backend.get_response(prompt, system_prompt="You are a technical writer. Generate clear, concise summaries of automation task executions.")
                return ai_summary
            except Exception as e:
                return self.generate_summary_report(execution_results)
        except Exception as e:
            return self.generate_summary_report(execution_results)
    
    def log_summary(self, task_query: str, execution_results: Optional[List] = None) -> None:
        """Generate and write AI-powered summary report."""
        if not self.task_query:
            self.task_query = task_query
        
        report = self.generate_ai_summary(task_query, execution_results)
        
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        full_report = f"""DAV AUTOMATION TASK REPORT
{'=' * 80}
Task: {self.task_query or task_query}
Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {duration}
{'=' * 80}

{report}

{'=' * 80}
Report saved: {self.report_file}
{'=' * 80}
"""
        
        with open(self.report_file, "w", encoding="utf-8") as f:
            f.write(full_report)
        
        print("\n" + "=" * 80)
        print("AUTOMATION TASK SUMMARY")
        print("=" * 80)
        print(report)
        print("=" * 80)
        print(f"Full report saved to: {self.report_file}\n")
    
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
                pass
    
    def close(self) -> None:
        """Close logger and ensure report is written."""
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

