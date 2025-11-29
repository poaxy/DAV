"""File security utilities for setting and verifying secure file permissions."""

import os
import stat
from pathlib import Path
from typing import Optional

# Secure file permissions: owner read/write only (0o600)
SECURE_FILE_PERMISSIONS = 0o600  # rw-------


def set_secure_permissions(file_path: Path) -> bool:
    """
    Set file permissions to secure mode (0o600 - owner read/write only).
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if permissions were set successfully, False otherwise
    """
    try:
        if not file_path.exists():
            return False
        
        # Set permissions to owner read/write only
        os.chmod(file_path, SECURE_FILE_PERMISSIONS)
        return True
    except (OSError, PermissionError) as e:
        # Silently fail if we can't set permissions (e.g., on some systems)
        return False


def verify_secure_permissions(file_path: Path) -> bool:
    """
    Verify that file has secure permissions (0o600 or more restrictive).
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if permissions are secure, False otherwise
    """
    try:
        if not file_path.exists():
            return False
        
        # Get current file permissions
        current_mode = file_path.stat().st_mode
        # Extract permission bits (last 3 octal digits)
        current_perms = stat.S_IMODE(current_mode)
        
        # Check if permissions are secure (0o600 or more restrictive)
        # Secure means: owner can read/write, group and others have no permissions
        # We check that group and others have no permissions (0o077 mask)
        group_other_perms = current_perms & 0o077
        
        # Permissions are secure if group and others have no access
        return group_other_perms == 0
    except (OSError, PermissionError):
        # If we can't check permissions, assume insecure to be safe
        return False


def check_and_warn_permissions(file_path: Path, file_type: str = "file") -> bool:
    """
    Check file permissions and warn if insecure.
    
    Args:
        file_path: Path to the file
        file_type: Description of file type for warning message
        
    Returns:
        True if permissions are secure, False otherwise
    """
    if not file_path.exists():
        return True  # File doesn't exist, nothing to check
    
    if not verify_secure_permissions(file_path):
        # Import here to avoid circular dependencies
        from rich.console import Console
        console = Console()
        console.print(
            f"[yellow]⚠ Warning:[/yellow] {file_type} at {file_path} has insecure permissions. "
            f"Consider setting it to 0o600 (owner read/write only)."
        )
        return False
    
    return True

