"""Plan management for generating and executing step-by-step plans."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dav.ai_backend import AIBackend
    from dav.executor import ExecutionResult
    from dav.session import SessionManager


@dataclass
class PlanStep:
    """A single step in a plan."""
    step_number: int
    description: str
    commands: List[str]  # Main commands to execute
    alternatives: Optional[List[str]] = None  # Fallback commands
    expected_outcome: Optional[str] = None  # What should happen
    status: str = "pending"  # pending, completed, failed, skipped


@dataclass
class Plan:
    """A complete plan with multiple steps."""
    plan_id: int
    title: str
    description: str
    steps: List[PlanStep]
    created_at: datetime
    status: str = "pending"  # pending, executing, completed, failed, partial


class PlanManager:
    """Manages plan creation, storage, and execution."""
    
    def __init__(self):
        """Initialize plan manager with empty storage."""
        self.plans: Dict[int, Plan] = {}
        self._next_id: int = 1
    
    def create_plan(self, query: str, ai_backend: "AIBackend") -> Plan:
        """
        Generate a plan from a user query using AI.
        
        Args:
            query: User's query/question
            ai_backend: AI backend instance
            
        Returns:
            Created Plan object
        """
        # Get plan generation prompt
        from dav.ai_backend import get_plan_generation_prompt
        
        system_prompt = get_plan_generation_prompt()
        user_prompt = f"""Create a comprehensive, step-by-step plan for: {query}

Break down the task into logical, numbered steps. For each step:
1. Provide a clear description of what needs to be done
2. Include the exact commands needed (as a list)
3. For critical steps, provide alternative commands if the first fails
4. Describe the expected outcome

Return ONLY valid JSON in this exact format:
{{
  "title": "Brief plan title",
  "description": "Overall description of the plan",
  "steps": [
    {{
      "step_number": 1,
      "description": "What this step does",
      "commands": ["command1", "command2"],
      "alternatives": ["alternative_command1"],
      "expected_outcome": "What should happen"
    }},
    ...
  ]
}}"""
        
        # Get AI response
        response = ai_backend.get_response(user_prompt, system_prompt=system_prompt)
        
        # Extract JSON from response
        json_str = self._extract_json_from_response(response)
        
        if not json_str:
            raise ValueError("Could not extract plan JSON from AI response")
        
        # Parse JSON
        try:
            plan_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in plan response: {e}")
        
        # Validate structure
        if not isinstance(plan_data, dict):
            raise ValueError("Plan data must be a JSON object")
        
        if "steps" not in plan_data or not isinstance(plan_data["steps"], list):
            raise ValueError("Plan must contain a 'steps' array")
        
        # Create PlanStep objects
        steps = []
        for step_data in plan_data["steps"]:
            if not isinstance(step_data, dict):
                continue
            
            step = PlanStep(
                step_number=step_data.get("step_number", len(steps) + 1),
                description=step_data.get("description", ""),
                commands=step_data.get("commands", []),
                alternatives=step_data.get("alternatives"),
                expected_outcome=step_data.get("expected_outcome"),
                status="pending"
            )
            steps.append(step)
        
        if not steps:
            raise ValueError("Plan must contain at least one step")
        
        # Create Plan object
        plan = Plan(
            plan_id=self._next_id,
            title=plan_data.get("title", "Untitled Plan"),
            description=plan_data.get("description", ""),
            steps=steps,
            created_at=datetime.now(),
            status="pending"
        )
        
        # Store and increment ID
        self.plans[plan.plan_id] = plan
        self._next_id += 1
        
        return plan
    
    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """Extract JSON from AI response."""
        # Try to find JSON in code blocks first
        json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL | re.MULTILINE)
        if json_block_match:
            return json_block_match.group(1)
        
        # Try to find inline JSON object (match balanced braces)
        brace_count = 0
        start_pos = response.find('{')
        if start_pos != -1:
            for i in range(start_pos, len(response)):
                if response[i] == '{':
                    brace_count += 1
                elif response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return response[start_pos:i+1]
        
        return None
    
    def get_plan(self, plan_id: int) -> Optional[Plan]:
        """Get plan by ID."""
        return self.plans.get(plan_id)
    
    def get_latest_plan(self) -> Optional[Plan]:
        """Get the most recently created plan."""
        if not self.plans:
            return None
        return max(self.plans.values(), key=lambda p: p.created_at)
    
    def list_plans(self) -> List[Plan]:
        """Get all plans sorted by creation time (newest first)."""
        return sorted(self.plans.values(), key=lambda p: p.created_at, reverse=True)
    
    def execute_plan(
        self,
        plan_id: int,
        ai_backend: "AIBackend",
        session_manager: "SessionManager",
        execute: bool = True,
        auto_confirm: bool = False,
        context_data: Optional[Dict] = None,
    ) -> List["ExecutionResult"]:
        """
        Execute a plan step-by-step with error handling.
        
        Args:
            plan_id: Plan ID to execute
            ai_backend: AI backend instance
            session_manager: Session manager instance
            execute: Whether to actually execute commands
            auto_confirm: Whether to auto-confirm execution
            context_data: Context data dictionary
            
        Returns:
            List of ExecutionResult objects
        """
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        
        plan.status = "executing"
        execution_results: List["ExecutionResult"] = []
        
        from dav.executor import execute_command
        from dav.executor import ExecutionResult
        from dav.terminal import render_info, render_error, render_warning
        
        total_steps = len(plan.steps)
        completed_steps = 0
        failed_steps = 0
        skipped_steps = 0
        
        for step in plan.steps:
            # Display current step
            render_info(f"\n[bold cyan]Step {step.step_number}/{total_steps}:[/bold cyan] {step.description}")
            
            if step.expected_outcome:
                render_info(f"[dim]Expected: {step.expected_outcome}[/dim]")
            
            # Execute commands in this step
            step_success = False
            step_results: List["ExecutionResult"] = []
            
            # Try main commands first
            for cmd in step.commands:
                if not execute:
                    render_info(f"[dim]Would execute: {cmd}[/dim]")
                    continue
                
                success, stdout, stderr, return_code = execute_command(
                    cmd,
                    confirm=not auto_confirm,
                    stream_output=True,
                    automation_mode=False,
                )
                
                result = ExecutionResult(
                    command=cmd,
                    success=success,
                    stdout=stdout,
                    stderr=stderr,
                    return_code=return_code
                )
                step_results.append(result)
                execution_results.append(result)
                
                if success:
                    step_success = True
                    step.status = "completed"
                    break  # Success, move to next step
                else:
                    render_warning(f"Command failed: {cmd}")
                    if stderr:
                        render_error(f"Error: {stderr}")
            
            # If main commands failed, try alternatives
            if not step_success and step.alternatives:
                render_info("[yellow]Trying alternative commands...[/yellow]")
                for alt_cmd in step.alternatives:
                    if not execute:
                        render_info(f"[dim]Would execute: {alt_cmd}[/dim]")
                        continue
                    
                    success, stdout, stderr, return_code = execute_command(
                        alt_cmd,
                        confirm=not auto_confirm,
                        stream_output=True,
                        automation_mode=False,
                    )
                    
                    result = ExecutionResult(
                        command=alt_cmd,
                        success=success,
                        stdout=stdout,
                        stderr=stderr,
                        return_code=return_code
                    )
                    step_results.append(result)
                    execution_results.append(result)
                    
                    if success:
                        step_success = True
                        step.status = "completed"
                        render_info("[green]Alternative command succeeded![/green]")
                        break
            
            # If all commands failed, prompt user
            if not step_success:
                step.status = "failed"
                failed_steps += 1
                
                if execute:
                    render_error(f"Step {step.step_number} failed: All commands failed")
                    
                    # Prompt user for action
                    render_info("\n[bold]What would you like to do?[/bold]")
                    render_info("1. Skip this step and continue")
                    render_info("2. Retry this step")
                    render_info("3. Provide a fix command")
                    render_info("4. Abort plan execution")
                    
                    choice = input("\nEnter choice (1-4): ").strip()
                    
                    if choice == "1":
                        step.status = "skipped"
                        skipped_steps += 1
                        render_info("[yellow]Step skipped. Continuing...[/yellow]")
                        continue
                    elif choice == "2":
                        # Retry: reset step status and restart loop
                        step.status = "pending"
                        # Re-execute this step (simplified - just retry first command)
                        if step.commands:
                            success, stdout, stderr, return_code = execute_command(
                                step.commands[0],
                                confirm=not auto_confirm,
                                stream_output=True,
                                automation_mode=False,
                            )
                            if success:
                                step.status = "completed"
                                step_success = True
                                completed_steps += 1
                                continue
                    elif choice == "3":
                        # User provides fix
                        fix_cmd = input("Enter fix command: ").strip()
                        if fix_cmd:
                            success, stdout, stderr, return_code = execute_command(
                                fix_cmd,
                                confirm=not auto_confirm,
                                stream_output=True,
                                automation_mode=False,
                            )
                            result = ExecutionResult(
                                command=fix_cmd,
                                success=success,
                                stdout=stdout,
                                stderr=stderr,
                                return_code=return_code
                            )
                            execution_results.append(result)
                            if success:
                                step.status = "completed"
                                step_success = True
                                completed_steps += 1
                                continue
                    elif choice == "4":
                        # Abort
                        plan.status = "partial"
                        render_error("Plan execution aborted by user")
                        break
                    else:
                        render_warning("Invalid choice. Skipping step.")
                        step.status = "skipped"
                        skipped_steps += 1
                        continue
            else:
                completed_steps += 1
            
            # Store step results in session
            if step_results:
                session_manager.add_execution_results(step_results)
        
        # Update plan status
        if failed_steps == 0 and skipped_steps == 0:
            plan.status = "completed"
        elif completed_steps > 0:
            plan.status = "partial"
        else:
            plan.status = "failed"
        
        # Display summary
        render_info(f"\n[bold]Plan execution summary:[/bold]")
        render_info(f"  Completed: {completed_steps}/{total_steps}")
        render_info(f"  Failed: {failed_steps}")
        render_info(f"  Skipped: {skipped_steps}")
        render_info(f"  Status: {plan.status}")
        
        return execution_results

