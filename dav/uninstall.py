"""Uninstall and cleanup utilities for Dav."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from dav.config import get_history_db_path, get_session_dir, get_automation_log_dir
from dav.update import detect_installation_method

console = Console()


def get_dav_data_paths() -> List[Tuple[Path, str]]:
    """Get all paths where Dav stores data."""
    paths = []
    seen_paths = set()  # Track paths to avoid duplicates
    
    # History database
    history_db = get_history_db_path()
    if history_db.exists() and history_db not in seen_paths:
        paths.append((history_db, "History database"))
        seen_paths.add(history_db)
    
    # Session directory
    session_dir = get_session_dir()
    if session_dir.exists() and session_dir not in seen_paths:
        paths.append((session_dir, "Session directory"))
        seen_paths.add(session_dir)
    
    # Automation logs directory
    log_dir = get_automation_log_dir()
    if log_dir.exists() and log_dir not in seen_paths:
        # Check if log directory has files
        log_files = list(log_dir.glob("dav_*.log"))
        if log_files:
            paths.append((log_dir, f"Automation logs directory ({len(log_files)} log file(s))"))
            seen_paths.add(log_dir)
    
    # Config directory and .env file
    dav_dir = Path.home() / ".dav"
    env_file = dav_dir / ".env"
    if env_file.exists() and env_file not in seen_paths:
        paths.append((env_file, "Configuration file"))
        seen_paths.add(env_file)
    
    # Check if .dav directory exists and has other files
    # Only add if it's not already included and has content
    if dav_dir.exists() and dav_dir not in seen_paths:
        # Count files in .dav directory (excluding the directory itself)
        files_in_dav = [f for f in dav_dir.rglob("*") if f.is_file()]
        if files_in_dav:
            paths.append((dav_dir, "Dav data directory"))
            seen_paths.add(dav_dir)
    
    return paths


def list_dav_files() -> None:
    """List all Dav-related files and directories."""
    paths = get_dav_data_paths()
    
    if not paths:
        console.print("[green]No Dav data files found.[/green]")
        return
    
    console.print("\n[bold]Dav data files and directories:[/bold]\n")
    
    for path, description in paths:
        if path.is_file():
            size = path.stat().st_size
            console.print(f"  [cyan]{path}[/cyan]")
            console.print(f"    {description} ({size:,} bytes)")
        elif path.is_dir():
            # Count files in directory
            file_count = len(list(path.rglob("*")))
            console.print(f"  [cyan]{path}/[/cyan]")
            console.print(f"    {description} ({file_count} items)")
        console.print()


def remove_dav_files(confirm: bool = True) -> bool:
    """
    Remove all Dav data files and directories.
    
    Args:
        confirm: Whether to ask for confirmation before deletion
    
    Returns:
        True if files were removed, False if cancelled
    """
    paths = get_dav_data_paths()
    
    if not paths:
        console.print("[green]No Dav data files found to remove.[/green]")
        return True
    
    # Show what will be removed
    console.print("\n[bold yellow]The following files/directories will be removed:[/bold yellow]\n")
    for path, description in paths:
        console.print(f"  [red]✗[/red] {path}")
        console.print(f"    {description}")
    
    if confirm:
        console.print("\n[bold red]Warning:[/bold red] This will permanently delete all Dav data!")
        response = input("\nContinue? (yes/no): ").strip().lower()
        if response not in ("yes", "y"):
            console.print("[yellow]Cancelled.[/yellow]")
            return False
    
    # Remove files and directories
    removed_count = 0
    errors = []
    
    for path, description in paths:
        try:
            if path.is_file():
                path.unlink()
                removed_count += 1
            elif path.is_dir():
                shutil.rmtree(path)
                removed_count += 1
        except Exception as e:
            errors.append((path, str(e)))
    
    if removed_count > 0:
        console.print(f"\n[green]✓ Removed {removed_count} item(s)[/green]")
    
    if errors:
        console.print("\n[bold red]Errors encountered:[/bold red]")
        for path, error in errors:
            console.print(f"  [red]✗[/red] {path}: {error}")
        return False
    
    return True


def uninstall_dav(remove_data: bool = True, confirm: bool = True) -> None:
    """
    Uninstall Dav package and optionally remove data files.
    
    Args:
        remove_data: Whether to remove Dav data files
        confirm: Whether to ask for confirmation
    """
    console.print(Panel.fit(
        "[bold]Dav Uninstaller[/bold]",
        border_style="yellow"
    ))
    
    console.print("\n[bold]Step 1:[/bold] Uninstall Dav package")
    console.print("Run the following command to uninstall the package:\n")
    console.print("[cyan]  pip uninstall dav-ai[/cyan]\n")
    
    if remove_data:
        console.print("[bold]Step 2:[/bold] Remove Dav data files")
        if remove_dav_files(confirm=confirm):
            console.print("\n[green]✓ Uninstall complete![/green]")
        else:
            console.print("\n[yellow]Package uninstall pending. Data files removed.[/yellow]")
    else:
        console.print("\n[yellow]Note:[/yellow] Data files were not removed.")
        console.print("To remove them later, run: [cyan]dav --uninstall-data[/cyan]")


def uninstall_with_pipx() -> bool:
    """Uninstall Dav using pipx."""
    try:
        console.print("[cyan]Uninstalling Dav using pipx...[/cyan]")
        result = subprocess.run(
            ['pipx', 'uninstall', 'dav-ai'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            console.print("[green]✓ Dav package uninstalled successfully![/green]")
            return True
        
        console.print(f"[red]✗ Uninstall failed:[/red] {result.stderr}")
        if result.stdout:
            console.print(f"[yellow]Output:[/yellow] {result.stdout}")
        return False
    
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Uninstall timed out[/red]")
        return False
    except FileNotFoundError:
        console.print("[red]✗ pipx not found. Please uninstall manually: pipx uninstall dav-ai[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error uninstalling: {str(e)}[/red]")
        return False


def uninstall_with_pip_user() -> bool:
    """Uninstall Dav using pip --user."""
    try:
        console.print("[cyan]Uninstalling Dav using pip...[/cyan]")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'uninstall', '-y', 'dav-ai'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            console.print("[green]✓ Dav package uninstalled successfully![/green]")
            return True
        else:
            console.print(f"[red]✗ Uninstall failed:[/red] {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Uninstall timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error uninstalling: {str(e)}[/red]")
        return False


def uninstall_with_venv() -> bool:
    """Uninstall Dav from current virtual environment."""
    try:
        console.print("[cyan]Uninstalling Dav from current virtual environment...[/cyan]")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'uninstall', '-y', 'dav-ai'],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            console.print("[green]✓ Dav package uninstalled successfully![/green]")
            return True
        else:
            console.print(f"[red]✗ Uninstall failed:[/red] {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Uninstall timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error uninstalling: {str(e)}[/red]")
        return False


def run_uninstall(confirm: bool = True) -> None:
    """
    Complete uninstall: remove all data files and uninstall the package.
    
    Args:
        confirm: Whether to ask for confirmation before uninstalling
    """
    console.print(Panel.fit(
        "[bold red]Dav Complete Uninstall[/bold red]",
        border_style="red"
    ))
    
    # Step 1: Detect installation method
    console.print("\n[bold]Step 1:[/bold] Detecting installation method...")
    method = detect_installation_method()
    console.print(f"[cyan]Detected:[/cyan] {method}\n")
    
    if method == 'unknown':
        console.print("[yellow]⚠ Could not detect installation method.[/yellow]")
        console.print("Will attempt to remove data files only.\n")
        console.print("To uninstall the package manually:")
        console.print("  • If using pipx: [cyan]pipx uninstall dav-ai[/cyan]")
        console.print("  • If using pip: [cyan]pip uninstall dav-ai[/cyan]")
        console.print("  • If in venv: [cyan]pip uninstall dav-ai[/cyan]\n")
        
        # Still try to remove data files
        if remove_dav_files(confirm=confirm):
            console.print("\n[green]✓ Data files removed![/green]")
            console.print("[yellow]Please uninstall the package manually using one of the commands above.[/yellow]\n")
        return
    
    # Step 2: Show what will be removed
    paths = get_dav_data_paths()
    console.print("[bold]Step 2:[/bold] Files and data to be removed:\n")
    
    if paths:
        for path, description in paths:
            console.print(f"  [red]✗[/red] {path}")
            console.print(f"    {description}")
    else:
        console.print("  [yellow]No data files found[/yellow]")
    
    console.print(f"\n  [red]✗[/red] dav-ai package (via {method})")
    
    # Check for root installation (handle permission errors gracefully)
    root_dav_dir = Path("/root/.dav")
    has_root_installation = False
    try:
        has_root_installation = root_dav_dir.exists()
    except (PermissionError, OSError):
        # Can't check /root/.dav due to permissions - assume no root installation
        pass
    
    # Check for cron jobs
    has_cron_jobs = False
    try:
        crontab_result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if crontab_result.returncode == 0:
            # Check if any cron jobs contain "dav"
            if "dav" in crontab_result.stdout.lower():
                has_cron_jobs = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Step 3: Confirm
    if confirm:
        console.print("\n[bold red]Warning:[/bold red] This will permanently:")
        console.print("  • Delete all Dav data files and configuration")
        console.print("  • Delete automation logs")
        console.print("  • Uninstall the dav-ai package")
        console.print("  • Remove the 'dav' command from your system\n")
        
        if has_root_installation:
            console.print("[yellow]⚠ Note:[/yellow] Root installation detected at [cyan]/root/.dav[/cyan]")
            console.print("  Root's configuration will NOT be removed automatically.")
            console.print("  To remove it manually: [cyan]sudo rm -rf /root/.dav[/cyan]\n")
        
        if has_cron_jobs:
            console.print("[yellow]⚠ Note:[/yellow] Cron jobs containing 'dav' were detected.")
            console.print("  Cron jobs will NOT be removed automatically.")
            console.print("  To remove them: [cyan]crontab -e[/cyan] (then delete the lines)\n")
        
        if not Confirm.ask("Continue with complete uninstall?", default=False):
            console.print("[yellow]Uninstall cancelled.[/yellow]")
            return
    
    # Step 4: Remove data files first (while package is still installed)
    console.print("\n[bold]Step 3:[/bold] Removing data files...")
    data_removed = remove_dav_files(confirm=False)  # Already confirmed above
    
    if not data_removed:
        console.print("[yellow]⚠ Some data files could not be removed, but continuing with package uninstall...[/yellow]")
    
    # Step 5: Uninstall package
    console.print(f"\n[bold]Step 4:[/bold] Uninstalling dav-ai package (method: {method})...")
    
    success = False
    if method == 'pipx':
        success = uninstall_with_pipx()
    elif method == 'pip-user':
        success = uninstall_with_pip_user()
    elif method == 'venv':
        success = uninstall_with_venv()
    
    # Final summary
    console.print("\n" + "="*50)
    if success and data_removed:
        console.print("[bold green]✓ Complete uninstall successful![/bold green]")
        console.print("[green]All Dav files, data, and the package have been removed.[/green]\n")
    elif success:
        console.print("[bold yellow]⚠ Package uninstalled, but some data files may remain.[/bold yellow]")
        console.print("[yellow]You may need to manually remove files from ~/.dav[/yellow]\n")
    elif data_removed:
        console.print("[bold yellow]⚠ Data files removed, but package uninstall failed.[/bold yellow]")
        console.print("[yellow]Please uninstall manually:[/yellow]")
        if method == 'pipx':
            console.print("  [cyan]pipx uninstall dav-ai[/cyan]")
        else:
            console.print("  [cyan]pip uninstall dav-ai[/cyan]")
        console.print()
    else:
        console.print("[bold red]✗ Uninstall incomplete[/bold red]")
        console.print("[red]Some steps failed. Please check the error messages above.[/red]\n")


def show_uninstall_info() -> None:
    """Show uninstall information."""
    console.print(Panel.fit(
        "[bold]Dav Uninstall Information[/bold]",
        border_style="cyan"
    ))
    
    console.print("\n[bold]Complete Uninstall:[/bold]\n")
    console.print("To completely remove Dav (data + package) in one command:")
    console.print("   [cyan]dav --uninstall[/cyan]\n")
    
    console.print("[bold]Partial Uninstall:[/bold]\n")
    console.print("To remove only data files:")
    console.print("   [cyan]dav --uninstall-data[/cyan]\n")
    
    console.print("[bold]Other useful commands:[/bold]\n")
    console.print("  • List data files: [cyan]dav --list-data[/cyan]")
    console.print("  • Show this info: [cyan]dav --uninstall-info[/cyan]\n")
    
    console.print("[bold]Dav data locations:[/bold]\n")
    list_dav_files()

