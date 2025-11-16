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
    
    def configure_sudoers(self, specific_commands: bool = True) -> Tuple[bool, str]:
        """
        Automatically configure sudoers NOPASSWD for Dav automation.
        
        Args:
            specific_commands: If True, only allow specific commands (more secure).
                             If False, allow all commands (less secure but simpler).
        
        Returns:
            Tuple of (success, message)
        """
        import os
        import tempfile
        
        username = self._get_current_username()
        dav_path = self._detect_dav_path()
        
        # Check if already configured
        if self.can_run_sudo():
            return True, "Password-less sudo is already configured"
        
        # Check if we can use sudo (need password for initial setup)
        try:
            result = subprocess.run(
                ["sudo", "-v"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, "Cannot configure sudoers: sudo authentication failed. Please run with sudo or enter your password."
        except Exception as e:
            return False, f"Cannot configure sudoers: {str(e)}"
        
        # Create sudoers content
        sudoers_file = "/etc/sudoers.d/dav-automation"
        
        # Check if file already exists
        check_existing = subprocess.run(
            ["sudo", "test", "-f", sudoers_file],
            capture_output=True,
            timeout=5,
        )
        if check_existing.returncode == 0:
            # File exists - ask if we should overwrite or just return success
            # For now, we'll update it (user already confirmed they want to configure)
            pass
        
        if specific_commands:
            # More secure: specific commands only
            sudoers_content = f"""# Dav automation - password-less sudo for specific commands
# Generated by: dav --cron-setup
# This allows Dav to run common system commands without password prompts

{username} ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/bin/systemctl, /usr/bin/journalctl, /usr/bin/dmesg, /usr/bin/log, /usr/bin/ufw, /usr/bin/dpkg, /usr/bin/snap, /usr/bin/flatpak, {dav_path}
"""
        else:
            # Less secure: all commands
            sudoers_content = f"""# Dav automation - password-less sudo for all commands
# Generated by: dav --cron-setup
# WARNING: This allows all commands without password. Use with caution.

{username} ALL=(ALL) NOPASSWD: ALL
"""
        
        # Write to temporary file first
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sudoers') as tmp_file:
                tmp_file.write(sudoers_content)
                tmp_file_path = tmp_file.name
            
            # Use visudo to validate and install (safest method)
            # visudo -c checks syntax, then we copy if valid
            check_result = subprocess.run(
                ["sudo", "visudo", "-c", "-f", tmp_file_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if check_result.returncode != 0:
                os.unlink(tmp_file_path)
                return False, f"Sudoers syntax error: {check_result.stderr}"
            
            # Copy to final location with proper permissions
            install_result = subprocess.run(
                ["sudo", "cp", tmp_file_path, sudoers_file],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if install_result.returncode != 0:
                os.unlink(tmp_file_path)
                return False, f"Failed to install sudoers file: {install_result.stderr}"
            
            # Set correct permissions (0440)
            chmod_result = subprocess.run(
                ["sudo", "chmod", "0440", sudoers_file],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if chmod_result.returncode != 0:
                # File installed but permissions might be wrong - warn but don't fail
                pass
            
            # Clean up temp file
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
            
            # Verify it works
            self._sudo_available = None  # Reset cache
            if self.can_run_sudo():
                return True, f"Sudoers configured successfully! Password-less sudo is now enabled for {username}."
            else:
                return False, "Sudoers file created but password-less sudo still not working. Please check manually."
                
        except Exception as e:
            return False, f"Error configuring sudoers: {str(e)}"

