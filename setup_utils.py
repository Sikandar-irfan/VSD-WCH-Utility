import os
import sys
import platform
import subprocess
from rich.console import Console
import questionary

console = Console()

class SetupError(Exception):
    """Custom exception for setup errors"""
    pass

def should_run_setup():
    """Ask user if they want to run setup"""
    return questionary.confirm(
        "Would you like to run the setup/update process?",
        default=False,
        style=questionary.Style([
            ('question', 'bold cyan'),
            ('answer', 'bold green'),
        ])
    ).ask()

def check_dependencies():
    """Check if all required dependencies are installed"""
    try:
        # Check Git
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        
        # Check Rust/Cargo
        subprocess.run(["cargo", "--version"], capture_output=True, check=True)
        
        # Check wlink
        subprocess.run(["wlink", "--version"], capture_output=True, check=True)
        
        # Check Python packages
        import questionary
        import rich
        import requests
        
        # Check Linux packages
        subprocess.run(["pkg-config", "--version"], capture_output=True, check=True)
        
        return True
    except:
        return False

def is_linux():
    return platform.system().lower() == "linux"

def check_system():
    """Check if running on Linux"""
    if not is_linux():
        raise SetupError("This tool only supports Linux operating systems")
    return True

def check_git():
    """Check if git is installed"""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def install_git():
    """Install git on Linux"""
    console.print("[yellow]Installing Git...[/yellow]")
    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", "git"], check=True)

def check_rust():
    """Check if Rust is installed"""
    try:
        subprocess.run(["cargo", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def install_rust():
    """Install Rust on Linux"""
    console.print("[yellow]Installing Rust...[/yellow]")
    subprocess.run(["curl", "--proto", "=https", "--tlsv1.2", "-sSf", 
                   "https://sh.rustup.rs", "-o", "rustup-init.sh"], check=True)
    subprocess.run(["chmod", "+x", "rustup-init.sh"], check=True)
    subprocess.run(["./rustup-init.sh", "-y"], check=True)
    os.remove("rustup-init.sh")

def setup_linux():
    """Linux-specific setup"""
    # Install required packages
    console.print("[yellow]Installing required packages...[/yellow]")
    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", 
                   "libusb-1.0-0", "pkg-config"], check=True)
    
    # Setup udev rules
    console.print("[yellow]Setting up udev rules...[/yellow]")
    udev_rule = 'SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", ATTR{idProduct}=="8010", MODE="0666"'
    with open("/tmp/99-wch.rules", "w") as f:
        f.write(udev_rule)
    subprocess.run(["sudo", "mv", "/tmp/99-wch.rules", 
                   "/etc/udev/rules.d/"], check=True)
    subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["sudo", "udevadm", "trigger"], check=True)

def check_python_packages():
    """Check if required Python packages are already installed"""
    try:
        import questionary
        import rich
        import requests
        return True
    except ImportError:
        return False

def setup_environment():
    """Setup the Linux environment"""
    try:
        # First check if running on Linux
        check_system()

        # Check if dependencies are already installed
        if check_dependencies():
            console.print("[green]✓ All dependencies are already installed[/green]")
            if not should_run_setup():
                console.print("[yellow]Skipping setup process...[/yellow]")
                return True
            console.print("[cyan]Running setup for updates...[/cyan]")

        # Check and install Git if needed
        if not check_git():
            console.print("[yellow]Git not found. Installing...[/yellow]")
            install_git()
            console.print("[green]✓ Git installed successfully[/green]")
        else:
            console.print("[green]✓ Git already installed[/green]")

        # Check and install Rust if needed
        if not check_rust():
            console.print("[yellow]Rust not found. Installing...[/yellow]")
            install_rust()
            # Update PATH to include cargo
            os.environ["PATH"] = f"{str(os.path.expanduser('~'))}/.cargo/bin:{os.environ['PATH']}"
            console.print("[green]✓ Rust installed successfully[/green]")
        else:
            console.print("[green]✓ Rust already installed[/green]")

        # Setup Linux environment
        setup_linux()

        # Only install Python dependencies if they're not already installed
        if not check_python_packages():
            console.print("[yellow]Installing Python dependencies...[/yellow]")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
            except subprocess.CalledProcessError:
                # If the first attempt fails, try with --break-system-packages
                console.print("[yellow]Retrying with --break-system-packages flag...[/yellow]")
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--break-system-packages"], check=True)
            console.print("[green]✓ Python dependencies installed successfully[/green]")
        else:
            console.print("[green]✓ Python dependencies already installed[/green]")

        # Check if wlink is installed
        try:
            subprocess.run(["wlink", "--version"], capture_output=True, check=True)
            console.print("[green]✓ wlink already installed[/green]")
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Install wlink using cargo
            console.print("[yellow]Installing wlink...[/yellow]")
            subprocess.run(["cargo", "install", "wlink"], check=True)
            console.print("[green]✓ wlink installed successfully[/green]")

        console.print("\n[bold green]✨ Setup completed successfully! ✨[/bold green]")
        return True

    except SetupError as e:
        console.print(f"[bold red]Setup Error: {str(e)}[/bold red]")
        return False
    except Exception as e:
        console.print(f"[bold red]Unexpected Error: {str(e)}[/bold red]")
        return False 
