"""Update functionality for Dav."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()


def detect_installation_method() -> str:
    """
    Detect how Dav was installed.
    
    Returns:
        'pipx', 'pip-user', 'venv', or 'unknown'
    """
    # Method 1: Check if we're in a pipx environment
    # pipx installs packages in ~/.local/pipx/venvs/
    try:
        # Check sys.prefix for pipx venv
        if 'pipx' in str(sys.prefix).lower() or '.local/pipx' in str(sys.prefix):
            return 'pipx'
        
        # Check if pipx list shows dav-ai
        result = subprocess.run(
            ['pipx', 'list'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and 'dav-ai' in result.stdout:
            return 'pipx'
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    # Method 2: Check if we're in a virtual environment
    try:
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            # We're in a venv
            return 'venv'
    except Exception:
        pass
    
    # Method 3: Check if dav command is in ~/.local/bin (pip --user)
    dav_path = shutil.which('dav')
    if dav_path:
        try:
            dav_path_obj = Path(dav_path).resolve()
            if '.local/bin' in str(dav_path_obj) or str(dav_path_obj).startswith(str(Path.home() / '.local')):
                return 'pip-user'
        except Exception:
            pass
    
    # Method 4: Check pip show to see where it's installed
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'dav-ai'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Check location field
            for line in result.stdout.split('\n'):
                if line.startswith('Location:'):
                    location = line.split(':', 1)[1].strip()
                    if 'pipx' in location.lower():
                        return 'pipx'
                    elif '.local' in location:
                        return 'pip-user'
                    elif 'site-packages' in location:
                        # Could be venv or system
                        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
                            return 'venv'
    except Exception:
        pass
    
    return 'unknown'


def _clear_python_cache(install_location: str = None) -> None:
    """Clear Python bytecode cache to ensure fresh imports after update."""
    # If we know the install location, clear cache there
    if install_location:
        cache_dirs = [
            Path(install_location) / "__pycache__",
            Path(install_location) / "dav" / "__pycache__",
        ]
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(cache_dir)
                except Exception:
                    pass
    
    # Also try to find and clear cache in common locations
    try:
        import site
        for site_dir in site.getsitepackages():
            dav_cache = Path(site_dir) / "dav" / "__pycache__"
            if dav_cache.exists():
                try:
                    import shutil
                    shutil.rmtree(dav_cache)
                except Exception:
                    pass
    except Exception:
        pass


def update_with_pipx() -> bool:
    """Update Dav using pipx."""
    try:
        console.print("[cyan]Updating Dav using pipx...[/cyan]")
        env = {**os.environ, "PIP_NO_CACHE_DIR": "1"}

        # First, try to get the pipx venv location to clear cache
        try:
            result = subprocess.run(
                ['pipx', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                import json
                pipx_data = json.loads(result.stdout)
                if 'venvs' in pipx_data and 'dav-ai' in pipx_data['venvs']:
                    venv_path = pipx_data['venvs']['dav-ai']['metadata']['venv']
                    # Clear cache before update
                    _clear_python_cache(venv_path)
        except Exception:
            pass  # Continue even if cache clearing fails

        # Use pipx reinstall to ensure a completely fresh installation
        # This is more reliable than upgrade for ensuring all files are updated
        result = subprocess.run(
            ['pipx', 'reinstall', '--force', 'dav-ai'],
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )

        if result.returncode == 0:
            console.print("[green]✓ Dav updated successfully![/green]")
            return True

        # If reinstall fails, try upgrade
        console.print("[yellow]Reinstall failed, trying upgrade...[/yellow]")
        result = subprocess.run(
            ['pipx', 'upgrade', '--force', 'dav-ai'],
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )

        if result.returncode == 0:
            console.print("[green]✓ Dav updated successfully![/green]")
            return True

        # If upgrade fails (package might not be installed), try install
        console.print("[yellow]Upgrade failed, trying fresh install...[/yellow]")
        result = subprocess.run(
            ['pipx', 'install', '--force', 'git+https://github.com/poaxy/DAV.git'],
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )

        if result.returncode == 0:
            console.print("[green]✓ Dav updated successfully![/green]")
            return True

        console.print(f"[red]✗ Update failed:[/red] {result.stderr}")
        if result.stdout:
            console.print(f"[yellow]Output:[/yellow] {result.stdout}")
        return False

    except subprocess.TimeoutExpired:
        console.print("[red]✗ Update timed out[/red]")
        return False
    except FileNotFoundError:
        console.print("[red]✗ pipx not found. Please install pipx first.[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error updating: {str(e)}[/red]")
        return False


def update_with_pip_user() -> bool:
    """Update Dav using pip --user."""
    try:
        console.print("[cyan]Updating Dav using pip...[/cyan]")
        
        # Get install location to clear cache
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'show', 'dav-ai'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Location:'):
                        install_location = line.split(':', 1)[1].strip()
                        _clear_python_cache(install_location)
                        break
        except Exception:
            pass  # Continue even if cache clearing fails
        
        # Use --no-cache-dir to force fresh download from git
        # Remove --no-deps to ensure dependencies are also updated
        # Use --upgrade --force-reinstall to ensure latest code is pulled
        env = {**os.environ, "PIP_NO_CACHE_DIR": "1"}
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', '--force-reinstall', '--no-cache-dir', '--user',
             'git+https://github.com/poaxy/DAV.git'],
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )
        
        if result.returncode == 0:
            console.print("[green]✓ Dav updated successfully![/green]")
            return True
        else:
            console.print(f"[red]✗ Update failed:[/red] {result.stderr}")
            if result.stdout:
                console.print(f"[yellow]Output:[/yellow] {result.stdout}")
            return False
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Update timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error updating: {str(e)}[/red]")
        return False


def update_with_venv() -> bool:
    """Update Dav in current virtual environment."""
    try:
        console.print("[cyan]Updating Dav in current virtual environment...[/cyan]")
        
        # Clear cache in current venv
        try:
            import site
            for site_dir in site.getsitepackages():
                dav_cache = Path(site_dir) / "dav" / "__pycache__"
                if dav_cache.exists():
                    _clear_python_cache(str(site_dir))
                    break
        except Exception:
            pass  # Continue even if cache clearing fails
        
        # Use --no-cache-dir to force fresh download from git
        # Remove --no-deps to ensure dependencies are also updated
        # Use --upgrade --force-reinstall to ensure latest code is pulled
        env = {**os.environ, "PIP_NO_CACHE_DIR": "1"}
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', '--force-reinstall', '--no-cache-dir',
             'git+https://github.com/poaxy/DAV.git'],
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )
        
        if result.returncode == 0:
            console.print("[green]✓ Dav updated successfully![/green]")
            return True
        else:
            console.print(f"[red]✗ Update failed:[/red] {result.stderr}")
            if result.stdout:
                console.print(f"[yellow]Output:[/yellow] {result.stdout}")
            return False
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Update timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error updating: {str(e)}[/red]")
        return False


def run_update(confirm: bool = True) -> None:
    """Run update process for Dav."""
    from pathlib import Path
    
    console.print(Panel.fit(
        "[bold green]Dav Updater[/bold green]",
        border_style="green"
    ))
    
    # Detect installation method
    method = detect_installation_method()
    
    console.print(f"\n[bold]Detected installation method:[/bold] {method}\n")
    
    # Check for root installation
    root_dav_dir = Path("/root/.dav")
    has_root_installation = root_dav_dir.exists()
    if has_root_installation:
        console.print("[yellow]⚠ Note:[/yellow] Root installation detected at [cyan]/root/.dav[/cyan]")
        console.print("  Root's installation will need to be updated separately if needed.")
        console.print("  To update root's installation: [cyan]sudo dav --update[/cyan] (as root)\n")
    
    if method == 'unknown':
        console.print("[yellow]⚠ Could not detect installation method.[/yellow]")
        console.print("Please update manually:")
        console.print("  • If using pipx: [cyan]pipx upgrade dav-ai[/cyan]")
        console.print("  • If using pip: [cyan]pip install --upgrade --user git+https://github.com/poaxy/DAV.git[/cyan]")
        return
    
    if confirm:
        if not Confirm.ask("Update Dav to the latest version?", default=True):
            console.print("[yellow]Update cancelled.[/yellow]")
            return
    
    # Update based on installation method
    success = False
    if method == 'pipx':
        success = update_with_pipx()
    elif method == 'pip-user':
        success = update_with_pip_user()
    elif method == 'venv':
        success = update_with_venv()
    
    if success:
        console.print("\n[bold green]✓ Update complete![/bold green]")
        console.print("[green]Your configuration, data, and automation logs have been preserved.[/green]\n")
        console.print("[bold yellow]⚠ Important:[/bold yellow] Please restart your terminal or run [cyan]hash -r[/cyan] to refresh command cache.")
        console.print("The new version will be available in new terminal sessions.\n")
    else:
        console.print("\n[bold red]✗ Update failed[/bold red]")
        console.print("Please try updating manually or check the error messages above.\n")

