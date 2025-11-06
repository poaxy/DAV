"""Uninstall and cleanup utilities for Dav."""

import shutil
from pathlib import Path
from typing import List, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dav.config import get_history_db_path, get_session_dir

console = Console()


def get_dav_data_paths() -> List[Tuple[Path, str]]:
    """Get all paths where Dav stores data."""
    paths = []
    
    # History database
    history_db = get_history_db_path()
    if history_db.exists():
        paths.append((history_db, "History database"))
    
    # Session directory
    session_dir = get_session_dir()
    if session_dir.exists():
        paths.append((session_dir, "Session directory"))
    
    # Config directory and .env file
    dav_dir = Path.home() / ".dav"
    env_file = dav_dir / ".env"
    if env_file.exists():
        paths.append((env_file, "Configuration file"))
    
    # Check if .dav directory exists and has other files
    if dav_dir.exists():
        # Count files in .dav directory
        files_in_dav = list(dav_dir.rglob("*"))
        if files_in_dav:
            paths.append((dav_dir, "Dav data directory"))
    
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


def show_uninstall_info() -> None:
    """Show uninstall information."""
    console.print(Panel.fit(
        "[bold]Dav Uninstall Information[/bold]",
        border_style="cyan"
    ))
    
    console.print("\n[bold]To completely uninstall Dav:[/bold]\n")
    console.print("[yellow]⚠ Important:[/yellow] Run data removal [bold]before[/bold] uninstalling the package!\n")
    console.print("1. Remove data files (while package is still installed):")
    console.print("   [cyan]dav --uninstall-data[/cyan]\n")
    console.print("2. Uninstall the package:")
    console.print("   [cyan]pip uninstall dav-ai[/cyan]\n")
    console.print("[bold]Other useful commands:[/bold]\n")
    console.print("  • List data files: [cyan]dav --list-data[/cyan]")
    console.print("  • Show this info: [cyan]dav --uninstall-info[/cyan]\n")
    
    console.print("[bold]Dav data locations:[/bold]\n")
    list_dav_files()

