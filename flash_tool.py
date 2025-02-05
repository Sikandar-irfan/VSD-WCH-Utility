#!/usr/bin/env python3

import questionary
import subprocess
import time
import os
import sys
import platform
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.panel import Panel
from rich import print as rprint
import json
import pathlib
import requests
import shutil
from setup_utils import setup_environment, is_linux, check_dependencies, should_run_setup

# Add argument parsing
if len(sys.argv) > 1 and sys.argv[1] == '--setup':
    if setup_environment():
        sys.exit(0)
    else:
        sys.exit(1)

console = Console()

class FirmwareUpdateError(Exception):
    """Custom exception for firmware update errors"""
    pass

def clear_screen():
    try:
        os.system('clear')  # Linux only
    except Exception as e:
        console.print(f"[yellow]Warning: Could not clear screen: {e}[/yellow]")

def show_loading_animation():
    try:
        with Progress() as progress:
            task = progress.add_task("[cyan]Loading...", total=100)
            while not progress.finished:
                progress.update(task, advance=2)
                time.sleep(0.02)
    except Exception as e:
        console.print(f"[yellow]Warning: Loading animation failed: {e}[/yellow]")

def show_exit_animation():
    try:
        with Progress() as progress:
            task = progress.add_task("[red]Closing...", total=100)
            while not progress.finished:
                progress.update(task, advance=4)
                time.sleep(0.02)
    except Exception as e:
        console.print(f"[yellow]Warning: Exit animation failed: {e}[/yellow]")

def show_welcome_screen():
    try:
        clear_screen()
        show_loading_animation()
        clear_screen()
        rprint(Panel.fit(
            "[bold magenta]WCH-Link Firmware Update Tool[/bold magenta]\n"
            "[blue]Version 1.0[/blue]",
            border_style="green"
        ))
        time.sleep(1)
    except Exception as e:
        console.print(f"[yellow]Warning: Welcome screen display failed: {e}[/yellow]")

def run_command(command):
    """Run a command with platform-specific adjustments"""
    try:
        # Use list format for Linux
        if isinstance(command, str):
            command = command.split()
        
        process = subprocess.run(command, shell=False, check=True, 
                               capture_output=True, text=True)
        output = process.stdout
        cleaned_lines = []
        for line in output.splitlines():
            if line.strip():
                # Remove ANSI codes and [INFO] tags
                clean_line = line.split(']')[-1].strip().replace('[0m', '')
                
                # Fix capitalization and formatting issues
                if 'Connected to' in clean_line:
                    clean_line = '► Connected to' + clean_line.split('Connected to')[1]
                elif clean_line.lower().endswith('chip by poweroff'):
                    clean_line = '► Erase chip by PowerOff'
                elif 'ChipID:' in clean_line:
                    clean_line = '► Chip ID:' + clean_line.split('ChipID:')[1]
                elif 'ESIG:' in clean_line:
                    clean_line = '► Chip ESIG:' + clean_line.split('ESIG:')[1]
                elif 'Flash protected:' in clean_line:
                    clean_line = '► Flash protected:' + clean_line.split('protected:')[1]
                elif 'Read' in clean_line and '.bin' in clean_line:
                    clean_line = '► Reading firmware file...'
                elif 'Flashing' in clean_line:
                    clean_line = '► Flashing firmware to device...'
                elif 'Read protected:' in clean_line:
                    clean_line = '► Read protected:' + clean_line.split('protected:')[1]
                elif 'Flash done' in clean_line:
                    clean_line = '► Flash completed successfully'
                elif 'Now reset' in clean_line:
                    clean_line = '► Resetting device...'
                # For lines that already have the arrow
                elif clean_line.startswith('► '):
                    pass
                # For any other lines, add the arrow
                else:
                    clean_line = '► ' + clean_line.strip()
                
                # Don't add empty lines
                if clean_line.strip() != '►':
                    cleaned_lines.append(clean_line)
        
        cleaned_output = '\n'.join(cleaned_lines)
        console.print(cleaned_output, style="green")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        if "Operation timed out" in error_msg:
            console.print("[bold red]Error: Device connection timed out. Please reconnect the device and try again.[/bold red]")
        elif "WCH-Link underlying protocol error" in error_msg:
            console.print("[bold red]Error: Communication error with WCH-Link. Please reconnect the device and try again.[/bold red]")
        elif "Input/Output Error" in error_msg:
            console.print("[bold red]Error: USB I/O Error. Please try the following:[/bold red]")
            console.print("[yellow]1. Unplug and replug the WCH-Link device[/yellow]")
            console.print("[yellow]2. Check USB cable connection[/yellow]")
            console.print("[yellow]3. Try a different USB port[/yellow]")
            console.print("[yellow]4. Ensure device is not being accessed by another program[/yellow]")
        else:
            console.print(f"[bold red]Error executing command: {error_msg}[/bold red]")
        return False
    except Exception as e:
        console.print(f"[bold red]Unexpected error: {e}[/bold red]")
        return False

def check_firmware_file(firmware_path):
    if not os.path.exists(firmware_path):
        raise FirmwareUpdateError(f"Firmware file not found: {firmware_path}")
    if not os.path.isfile(firmware_path):
        raise FirmwareUpdateError(f"Not a valid file: {firmware_path}")
    if not os.access(firmware_path, os.R_OK):
        raise FirmwareUpdateError(f"No permission to read firmware file: {firmware_path}")

def load_saved_path():
    config_file = pathlib.Path.home() / '.wch_flasher_config.json'
    try:
        if config_file.exists():
            with open(config_file) as f:
                return json.load(f).get('firmware_path')
    except Exception:
        return None
    return None

def save_firmware_path(path):
    config_file = pathlib.Path.home() / '.wch_flasher_config.json'
    try:
        with open(config_file, 'w') as f:
            json.dump({'firmware_path': path}, f)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save firmware path: {e}[/yellow]")

def get_firmware_path(device_type=None):
    """Get firmware file path based on device type"""
    if "VSD Squadran Mini" in device_type:
        # Default paths for VSD Squadran Mini firmware
        if "CH32V003" in device_type:
            default_path = "./Firmware_Link/FIRMWARE_CH32V003.bin"
        else:
            default_path = "./Firmware_Link/WCH-LinkE-APP-IAP.bin"
        
        # Show current path if exists
        if os.path.exists(default_path):
            console.print(f"[green]Current firmware path: {default_path}[/green]")
        
        # Ask for firmware path
        choices = [
            "Use default path",
            "Select new firmware path"
        ]
        
        choice = questionary.select(
            "Firmware file options:",
            choices=choices,
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('answer', 'bold green'),
                ('pointer', 'bold yellow'),
            ])
        ).ask()
        
        if choice == "Use default path":
            if os.path.exists(default_path):
                return default_path
            else:
                console.print("[yellow]Default firmware path not found. Please select a new path.[/yellow]")
        
        # Let user select firmware file
        firmware_path = questionary.path(
            "Select firmware file:",
            default=default_path if os.path.exists(default_path) else None,
            validate=lambda p: os.path.exists(p) and p.endswith('.bin'),
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('answer', 'bold green'),
            ])
        ).ask()
        
        # Save the selected path
        if firmware_path:
            save_firmware_path(firmware_path)
            return firmware_path
        else:
            raise FirmwareUpdateError("No firmware file selected")
    
    # For other devices, use the original path handling
    saved_path = load_saved_path()
    if saved_path and os.path.exists(saved_path):
        return saved_path
    
    return questionary.path(
        "Enter firmware file path:",
        validate=lambda p: os.path.exists(p) and p.endswith('.bin'),
        style=questionary.Style([
            ('question', 'bold cyan'),
            ('answer', 'bold green'),
        ])
    ).ask()

def get_device_type():
    # First try to detect the chip
    try:
        process = subprocess.run("wlink status -v", shell=True, capture_output=True, text=True)
        output = process.stdout
        
        detected_type = None
        if "CH32V003" in output:
            detected_type = "CH32V003"
        elif "CH32V30X" in output or "WCH-LinkE-CH32V305" in output:
            detected_type = "CH32V30X"
        
        if detected_type:
            console.print(f"[green]► Detected chip type: {detected_type}[/green]")
            if questionary.confirm(
                f"Would you like to use detected chip type ({detected_type})?",
                default=True
            ).ask():
                if detected_type == "CH32V003":
                    return "VSD Squadran Mini (CH32V003)"
                elif detected_type == "CH32V30X":
                    return "VSD Squadran Mini (CH32V30X)"
    except:
        console.print("[yellow]Could not auto-detect chip type[/yellow]")
    
    # If auto-detection fails or user wants to select manually
    device_type = questionary.select(
        "Select device type:",
        choices=[
            "VSD Squadran Mini (CH32V003)",
            "VSD Squadran Mini (CH32V30X)",
            "Other WCH-Link devices"
        ],
        style=questionary.Style([
            ('question', 'bold cyan'),
            ('answer', 'bold green'),
            ('pointer', 'bold yellow'),
        ])
    ).ask()
    return device_type

def get_wlink_options(device_type):
    if device_type == "VSD Squadran Mini (CH32V003)" or device_type == "VSD Squadran Mini (CH32V30X)":
        return {
            'erase_methods': ['power-off'],
            'default_options': {
                'erase_method': 'power-off'
            }
        }
    else:
        return {
            'erase_methods': ['default', 'power-off', 'pin-rst'],
            'speeds': ['low', 'medium', 'high'],
            'default_options': load_default_options()
        }

def load_default_options():
    return {
        'erase_method': 'default',
        'speed': 'high'
    }

def save_default_options(options):
    config_file = pathlib.Path.home() / '.wch_flasher_config.json'
    try:
        config = {}
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
        config['default_options'] = options
        with open(config_file, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save default options: {e}[/yellow]")

def select_wlink_options(device_type=None):
    """Select wlink options based on device type"""
    if device_type == "VSD Squadran Mini (CH32V30X)":
        # Fixed options for VSD Squadran Mini
        return {
            'erase_method': 'power-off',
            'speed': 'high'  # Add default speed for consistency
        }
    else:
        # For other devices, get user input
        console.print("\n[bold cyan]WLink Configuration Options[/bold cyan]")
        
        # Select speed
        speed = questionary.select(
            "Select connection speed:",
            choices=['high', 'medium', 'low'],
            default='high',
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('answer', 'bold green'),
                ('pointer', 'bold yellow'),
            ])
        ).ask()
        
        # Select erase method
        erase_method = questionary.select(
            "Select erase method:",
            choices=['default', 'power-off', 'pin-rst'],
            default='default',
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('answer', 'bold green'),
                ('pointer', 'bold yellow'),
            ])
        ).ask()
        
        selected_options = {
            'erase_method': erase_method,
            'speed': speed
        }
        
        if questionary.confirm(
            "Save these options as default?",
            default=True
        ).ask():
            save_default_options(selected_options)
        
        return selected_options

def detect_chip_type():
    try:
        # Run wlink status to get detailed device information
        process = subprocess.run("wlink status -v", shell=True, capture_output=True, text=True)
        output = process.stdout
        
        # Print the connection status
        for line in output.splitlines():
            if "Connected to" in line:
                console.print(f"[green]► {line.split(']')[-1].strip()}[/green]")
        
        # Define chip configurations
        chip_configs = {
            'CH32V30X': {'erase_chip': 'CH32V30X', 'flash_chip': 'CH32V30X'},
            'CH32V103': {'erase_chip': 'CH32V103', 'flash_chip': 'CH32V103'},
            'CH57X': {'erase_chip': 'CH57X', 'flash_chip': 'CH57X'},
            'CH56X': {'erase_chip': 'CH56X', 'flash_chip': 'CH56X'},
            'CH32V20X': {'erase_chip': 'CH32V20X', 'flash_chip': 'CH32V20X'},
            'CH582': {'erase_chip': 'CH582', 'flash_chip': 'CH582'},
            'CH32V003': {'erase_chip': 'CH32V003', 'flash_chip': 'CH32V003'},
            'CH8571': {'erase_chip': 'CH8571', 'flash_chip': 'CH8571'},
            'CH59X': {'erase_chip': 'CH59X', 'flash_chip': 'CH59X'},
            'CH643': {'erase_chip': 'CH643', 'flash_chip': 'CH643'},
            'CH32X035': {'erase_chip': 'CH32X035', 'flash_chip': 'CH32X035'},
            'CH32L103': {'erase_chip': 'CH32L103', 'flash_chip': 'CH32L103'},
            'CH641': {'erase_chip': 'CH641', 'flash_chip': 'CH641'},
            'CH585': {'erase_chip': 'CH585', 'flash_chip': 'CH585'},
            'CH564': {'erase_chip': 'CH564', 'flash_chip': 'CH564'},
            'CH32V007': {'erase_chip': 'CH32V007', 'flash_chip': 'CH32V007'},
            'CH645': {'erase_chip': 'CH645', 'flash_chip': 'CH645'},
            'CH32V317': {'erase_chip': 'CH32V317', 'flash_chip': 'CH32V317'}
        }
        
        # Check for specific chip types in the status output
        for chip_type in chip_configs.keys():
            if chip_type in output:
                console.print(f"[green]► Found chip: {chip_type}[/green]")
                return chip_configs[chip_type]
        
        # Special case for WCH-LinkE-CH32V305
        if "WCH-LinkE-CH32V305" in output:
            console.print("[green]► Found chip: CH32V30X[/green]")
            return chip_configs['CH32V30X']
        
        # If no chip was detected, show the full status output for debugging
        console.print("[yellow]Device detection details:[/yellow]")
        console.print(output)
        raise FirmwareUpdateError("Unable to detect chip type. Please check device connection.")
            
    except subprocess.CalledProcessError as e:
        raise FirmwareUpdateError(f"Error running wlink status: {e}")
    except Exception as e:
        raise FirmwareUpdateError(f"Error detecting chip type: {e}")

def check_device_connection():
    """Check if device is connected and responding"""
    try:
        process = subprocess.run("wlink list -v", shell=True, capture_output=True, text=True)
        return "WCH-Link" in process.stdout
    except:
        return False

def reset_device():
    """Reset the device and wait for it to stabilize"""
    console.print("\n[yellow]Resetting device...[/yellow]")
    try:
        subprocess.run(["wlink", "reset"], check=True, capture_output=True)
        with Progress() as progress:
            task = progress.add_task("[cyan]Waiting for device to stabilize...", total=100)
            while not progress.finished:
                progress.update(task, advance=2)
                time.sleep(0.1)
        return True
    except Exception as e:
        console.print(f"[yellow]Warning: Reset failed: {e}[/yellow]")
        return False

def flash_device(firmware_path=None, wlink_options=None, device_type=None):
    try:
        if not firmware_path:
            firmware_path = get_firmware_path(device_type)
        if not firmware_path or not os.path.exists(firmware_path):
            raise FirmwareUpdateError("Firmware file not found")
        
        check_firmware_file(firmware_path)
        
        # Detect actual chip type first
        chip_info = detect_chip_type()
        actual_chip = None
        for chip_type in chip_info.keys():
            if chip_type in ["CH32V003", "CH32V30X"]:
                actual_chip = chip_type
                break
        
        # Check for chip type mismatch
        expected_chip = None
        if "CH32V003" in device_type:
            expected_chip = "CH32V003"
        elif "CH32V30X" in device_type:
            expected_chip = "CH32V30X"
        
        if expected_chip and actual_chip and expected_chip != actual_chip:
            console.print(f"[yellow]Warning: Selected device type ({expected_chip}) does not match detected chip ({actual_chip})[/yellow]")
            if not questionary.confirm(
                "Would you like to continue with the detected chip type?",
                default=True
            ).ask():
                raise FirmwareUpdateError(f"Chip type mismatch: expected {expected_chip}, got {actual_chip}")
            # Update device type to match actual chip
            if actual_chip == "CH32V003":
                device_type = "VSD Squadran Mini (CH32V003)"
            elif actual_chip == "CH32V30X":
                device_type = "VSD Squadran Mini (CH32V30X)"
        
        # Set chip configuration based on device type
        if "VSD Squadran Mini" in device_type:
            console.print(f"[green]► VSD Squadran mini detected[/green]")
            
            console.print("\n[bold blue]╭" + "─"*50 + "╮[/bold blue]")
            console.print("[bold blue]│[/bold blue]" + " "*15 + "[bold yellow]Starting Firmware Update[/bold yellow]" + " "*15 + "[bold blue]│[/bold blue]")
            console.print("[bold blue]╰" + "─"*50 + "╯[/bold blue]\n")
            
            # Use detected chip type for commands
            chip_type = actual_chip if actual_chip else "CH32V003"  # Default to CH32V003 if detection fails
            
            # First command - Erase with specific command
            max_retries = 3
            for attempt in range(max_retries):
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True
                ) as progress:
                    task = progress.add_task("[bold cyan]Erasing chip...", total=1)
                    console.print("\n[bold yellow]► Executing erase command...[/bold yellow]")
                    if run_command(f"wlink erase --method power-off --chip {chip_type} -v"):
                        progress.update(task, advance=1)
                        break
                    if attempt < max_retries - 1:
                        console.print("[yellow]Retrying erase command...[/yellow]")
                        time.sleep(2)
                    else:
                        raise FirmwareUpdateError("Chip erase failed after multiple attempts")
            
            # Reset device after erase
            if not reset_device():
                raise FirmwareUpdateError("Failed to reset device after erase")
            
            # Second command - Flash with specific command
            speeds = ['low', 'medium', 'high']
            current_speed_index = 0  # Start with low speed for CH32V003
            
            for speed in speeds[current_speed_index:]:
                for attempt in range(max_retries):
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TimeElapsedColumn(),
                        console=console,
                        transient=True
                    ) as progress:
                        task = progress.add_task("[bold cyan]Flashing firmware...", total=1)
                        console.print(f"\n[bold yellow]► Executing flash command (Speed: {speed})...[/bold yellow]")
                        
                        # Get the absolute path of the firmware file
                        firmware_abs_path = os.path.abspath(firmware_path)
                        if not os.path.exists(firmware_abs_path):
                            raise FirmwareUpdateError(f"Firmware file not found: {firmware_abs_path}")
                        
                        # For CH32V003, always use low speed and add verify
                        if chip_type == "CH32V003":
                            flash_cmd = f"wlink flash --chip {chip_type} --speed low --verify {firmware_abs_path}"
                        else:
                            flash_cmd = f"wlink flash --chip {chip_type} --speed {speed} {firmware_abs_path}"
                        
                        if run_command(flash_cmd):
                            progress.update(task, advance=1)
                            console.print("\n[bold green]✨ Firmware update completed successfully! ✨[/bold green]")
                            return True, wlink_options
                        
                        if attempt < max_retries - 1:
                            console.print("[yellow]Retrying flash command with same speed...[/yellow]")
                            reset_device()  # Reset device before retry
                            time.sleep(2)
                        elif speed != speeds[-1] and chip_type != "CH32V003":
                            console.print(f"[yellow]Trying with higher speed...[/yellow]")
                            reset_device()  # Reset device before changing speed
                            time.sleep(2)
            
            raise FirmwareUpdateError("Firmware flash failed after trying all speeds")
        
        else:
            # Original code for other devices with speed options
            chip_types = detect_chip_type()
            console.print(f"[green]► Detected device configuration:[/green]")
            console.print(f"[green]  • Erase chip: {chip_types['erase_chip']}[/green]")
            console.print(f"[green]  • Flash chip: {chip_types['flash_chip']}[/green]")
            
            console.print("\n[bold blue]╭" + "─"*50 + "╮[/bold blue]")
            console.print("[bold blue]│[/bold blue]" + " "*15 + "[bold yellow]Starting Firmware Update[/bold yellow]" + " "*15 + "[bold blue]│[/bold blue]")
            console.print("[bold blue]╰" + "─"*50 + "╯[/bold blue]\n")
            
            # First command - Erase
            max_retries = 3
            for attempt in range(max_retries):
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True
                ) as progress:
                    task = progress.add_task("[bold cyan]Erasing chip...", total=1)
                    console.print("\n[bold yellow]► Executing erase command...[/bold yellow]")
                    if run_command(f"wlink erase --method default --chip {chip_types['erase_chip']}"):
                        progress.update(task, advance=1)
                        break
                    if attempt < max_retries - 1:
                        console.print("[yellow]Retrying erase command...[/yellow]")
                        time.sleep(2)
                    else:
                        raise FirmwareUpdateError("Chip erase failed after multiple attempts")
            
            # Wait for device to reset and stabilize
            console.print("\n[bold yellow]► Waiting for device to reset...[/bold yellow]")
            time.sleep(5)  # Give device time to reset and stabilize
            
            # Second command - Flash with retry and speed adjustment
            speeds = ['high', 'medium', 'low']
            current_speed_index = speeds.index(wlink_options['speed'])
            
            for speed in speeds[current_speed_index:]:
                # Reset device before trying new speed using power cycle
                console.print(f"\n[yellow]Resetting device before trying {speed} speed...[/yellow]")
                console.print("[yellow]Please manually power cycle the device:[/yellow]")
                console.print("1. Unplug the device")
                console.print("2. Wait for 5 seconds")
                console.print("3. Plug it back in")
                
                with Progress() as progress:
                    task = progress.add_task("[cyan]Waiting for power cycle...", total=100)
                    while not progress.finished:
                        progress.update(task, advance=1)
                        time.sleep(0.1)
                
                # Wait 5 seconds
                with Progress() as progress:
                    task = progress.add_task("[cyan]Waiting...", total=100)
                    while not progress.finished:
                        progress.update(task, advance=1)
                        time.sleep(0.05)
                
                console.print("\n[bold green]Now plug the device back in...[/bold green]")
                
                # Wait for reconnection
                with Progress() as progress:
                    task = progress.add_task("[cyan]Waiting for device to be ready...", total=100)
                    while not progress.finished:
                        progress.update(task, advance=1)
                        time.sleep(0.05)
                
                # Additional wait for device to stabilize
                time.sleep(5)
                
                for attempt in range(max_retries):
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                        TimeElapsedColumn(),
                        console=console,
                        transient=True
                    ) as progress:
                        task = progress.add_task("[bold cyan]Flashing firmware...", total=1)
                        console.print(f"\n[bold yellow]► Executing flash command (Speed: {speed})...[/bold yellow]")
                        
                        flash_cmd = f"wlink flash --chip {chip_types['flash_chip']} --speed {speed} {firmware_path}"
                        if run_command(flash_cmd):
                            progress.update(task, advance=1)
                            console.print("\n[bold green]✨ Firmware update completed successfully! ✨[/bold green]")
                            return True, wlink_options
                        
                        if attempt < max_retries - 1:
                            console.print(f"[yellow]Retrying flash command with same speed ({speed})...[/yellow]")
                            console.print("[yellow]Please wait while device stabilizes...[/yellow]")
                            time.sleep(10)  # Increased wait time between retries
                        elif speed != speeds[-1]:
                            console.print(f"[yellow]Trying with lower speed...[/yellow]")
                            time.sleep(5)
            
            raise FirmwareUpdateError("Firmware flash failed after trying all speeds")
        
    except FirmwareUpdateError as e:
        console.print(f"\n[bold red]Firmware Update Error: {e}[/bold red]")
        return False, wlink_options
    except Exception as e:
        console.print(f"\n[bold red]Unexpected Error: {e}[/bold red]")
        return False, wlink_options

def check_internet_connection():
    try:
        console.print("[yellow]Checking internet connection...[/yellow]")
        requests.get("http://google.com", timeout=3)
        console.print("[green]✓ Internet connection available[/green]")
        return True
    except requests.RequestException:
        console.print("[bold red]✗ No internet connection available[/bold red]")
        return False

def check_wlink_installation():
    try:
        subprocess.run(["wlink", "--version"], capture_output=True, check=True)
        console.print("[green]✓ WLink is already installed[/green]")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def install_wlink():
    try:
        console.print("[yellow]Installing WLink...[/yellow]")
        
        # Install required packages
        subprocess.run(["sudo", "apt", "update"], check=True)
        subprocess.run(["sudo", "apt", "install", "-y", "libusb-1.0-0", "pkg-config"], check=True)
        
        # Install Rust if not installed
        if shutil.which("cargo") is None:
            console.print("[yellow]Installing Rust...[/yellow]")
            subprocess.run(["curl", "--proto", "=https", "--tlsv1.2", "-sSf", 
                          "https://sh.rustup.rs", "-o", "rustup-init.sh"], check=True)
            subprocess.run(["chmod", "+x", "rustup-init.sh"], check=True)
            subprocess.run(["./rustup-init.sh", "-y"], check=True)
            os.remove("rustup-init.sh")
            
            # Update PATH to include cargo
            os.environ["PATH"] = f"{os.path.expanduser('~/.cargo/bin')}:{os.environ['PATH']}"
        
        # Install wlink using cargo
        subprocess.run(["cargo", "install", "wlink"], check=True)
        
        # Add udev rules
        udev_rule = 'SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", ATTR{idProduct}=="8010", MODE="0666"'
        with open("/tmp/99-wch.rules", "w") as f:
            f.write(udev_rule)
        subprocess.run(["sudo", "mv", "/tmp/99-wch.rules", "/etc/udev/rules.d/"], check=True)
        subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], check=True)
        subprocess.run(["sudo", "udevadm", "trigger"], check=True)
        
        console.print("[green]✓ WLink installed successfully[/green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error installing WLink: {e}[/bold red]")
        return False
    except Exception as e:
        console.print(f"[bold red]Unexpected error during installation: {e}[/bold red]")
        return False

def setup_environment():
    """Check environment and install required tools"""
    from setup_utils import setup_environment as setup
    if not setup():
        sys.exit(1)

def main():
    try:
        show_welcome_screen()
        
        # Only run setup if explicitly requested or if dependencies are missing
        if not check_dependencies():
            console.print("[yellow]Some dependencies are missing.[/yellow]")
            if not should_run_setup():
                console.print("[bold red]Cannot proceed without required dependencies.[/bold red]")
                return
            if not setup_environment():
                console.print("[bold red]Setup failed. Please run with --setup flag to try again.[/bold red]")
                return
        
        # Select device type at startup
        device_type = get_device_type()
        firmware_path = None
        
        # Initialize wlink_options based on device type
        if device_type == "VSD Squadran Mini (CH32V30X)":
            wlink_options = {
                'erase_method': 'power-off'
            }
        else:
            # For other devices, get options from user
            options = get_wlink_options(device_type)
            wlink_options = select_wlink_options(device_type)
        
        while True:
            # Get firmware path if not set
            if firmware_path is None:
                firmware_path = get_firmware_path(device_type)
            
            success, wlink_options = flash_device(
                firmware_path=firmware_path,
                wlink_options=wlink_options,
                device_type=device_type
            )
            
            if not success:
                if not questionary.confirm(
                    "Would you like to retry?",
                    default=True,
                    style=questionary.Style([
                        ('question', 'bold red'),
                        ('answer', 'bold green'),
                        ('pointer', 'bold yellow'),
                    ])
                ).ask():
                    break
                
                # Only ask for changes if explicitly requested
                if questionary.confirm(
                    "Would you like to change any settings?",
                    default=False
                ).ask():
                    if questionary.confirm(
                        "Would you like to change the firmware file location?",
                        default=False
                    ).ask():
                        firmware_path = None
                    if questionary.confirm(
                        "Would you like to change the device type?",
                        default=False
                    ).ask():
                        device_type = get_device_type()
                        # Reinitialize options for new device type
                        if device_type == "VSD Squadran Mini (CH32V30X)":
                            wlink_options = {
                                'erase_method': 'power-off'
                            }
                        else:
                            options = get_wlink_options(device_type)
                            wlink_options = select_wlink_options(device_type)
                
                continue
            
            # After successful flash, ask about flashing another device
            console.print("\n[bold cyan]╭" + "─"*50 + "╮[/bold cyan]")
            continue_flashing = questionary.confirm(
                "Would you like to flash another device with the same settings?",
                default=False,
                style=questionary.Style([
                    ('question', 'bold cyan'),
                    ('answer', 'bold green'),
                    ('pointer', 'bold yellow'),
                ])
            ).ask()
            console.print("[bold cyan]╰" + "─"*50 + "╯[/bold cyan]")
            
            if not continue_flashing:
                break
            
            # Clear screen and show banner for next device
            clear_screen()
            rprint(Panel.fit(
                "[bold magenta]WCH-Link Firmware Update Tool[/bold magenta]\n"
                "[blue]Version 1.0[/blue]",
                border_style="green"
            ))
            
            # Only ask for changes if explicitly requested
            if questionary.confirm(
                "Would you like to change any settings?",
                default=False
            ).ask():
                if questionary.confirm(
                    "Would you like to change the device type?",
                    default=False
                ).ask():
                    device_type = get_device_type()
                    # Reinitialize options for new device type
                    if device_type == "VSD Squadran Mini (CH32V30X)":
                        wlink_options = {
                            'erase_method': 'power-off'
                        }
                    else:
                        options = get_wlink_options(device_type)
                        wlink_options = select_wlink_options(device_type)
                if questionary.confirm(
                    "Would you like to change the firmware file location?",
                    default=False
                ).ask():
                    firmware_path = None
        
        clear_screen()
        console.print("\n[bold blue]✨ Thank you for using the WCH-Link Firmware Update Tool! ✨[/bold blue]")
        show_exit_animation()
        
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Program interrupted by user[/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Critical Error: {e}[/bold red]")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main() 