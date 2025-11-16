"""Sudo handling for automation mode."""

import subprocess
import sys
from typing import Optional, Tuple


class SudoHandler:
    """Handle sudo operations for automation."""
    
    def __init__(self):
        """Initialize sudo handler."""
        self._sudo_available: Optional[bool] = None
    
    def can_run_sudo(self) -> bool:
        """
        Check if password-less sudo is available.
        
        Returns:
            True if password-less sudo works, False otherwise
        """
        if self._sudo_available is not None:
            return self._sudo_available
        
        try:
            # Use sudo -n (non-interactive) to check if password-less sudo works
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                timeout=5,
            )
            self._sudo_available = result.returncode == 0
            return self._sudo_available
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            self._sudo_available = False
            return False
    
    def execute_with_sudo(self, command: str) -> Tuple[bool, str, str, int]:
        """
        Execute command with sudo (assumes NOPASSWD configured).
        
        Args:
            command: Command to execute with sudo
        
        Returns:
            Tuple of (success, stdout, stderr, return_code)
        """
        try:
            # Prepend sudo to command
            sudo_command = f"sudo {command}"
            
            result = subprocess.run(
                sudo_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                result.returncode,
            )
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out", 124
        except Exception as e:
            return False, "", str(e), 1
    
    def check_sudoers_setup(self) -> Tuple[bool, str]:
        """
        Check if sudoers is properly configured.
        
        Returns:
            Tuple of (is_configured, message)
        """
        if self.can_run_sudo():
            return True, "Password-less sudo is configured and working"
        else:
            return False, "Password-less sudo is not available"
    
    def get_sudoers_instructions(self) -> str:
        """
        Get instructions for setting up sudoers NOPASSWD.
        
        Returns:
            Instructions string
        """
        username = self._get_current_username()
        dav_path = self._detect_dav_path()
        
        instructions = f"""
To enable password-less sudo for Dav automation:

1. Create sudoers configuration file:
   sudo visudo -f /etc/sudoers.d/dav-automation

2. Add the following (replace {username} with your username):
   {username} ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/bin/systemctl, /usr/bin/journalctl, /usr/bin/dmesg, /usr/bin/log

3. Save and exit. The configuration will be active immediately.

4. Test with:
   sudo -n true

5. If you need more commands, add them to the NOPASSWD list.

Note: Be specific with commands (not ALL) for better security.
"""
        return instructions.strip()
    
    def _get_current_username(self) -> str:
        """Get current username."""
        try:
            import os
            import pwd
            return pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            import os
            return os.getenv("USER", "user")
    
    def _detect_dav_path(self) -> str:
        """Detect where dav command is installed."""
        import shutil
        dav_path = shutil.which("dav")
        return dav_path or "/usr/local/bin/dav"

