#!/usr/bin/env python3
"""
Fan Control Monitor for Linux
Displays temperatures and fan speeds, with optional automatic control
"""

import os
import sys
import time
import argparse
import select
import termios
import tty
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import deque


class KeyboardHandler:
    """Handle non-blocking keyboard input"""

    def __init__(self):
        self.old_settings = None
        self.enabled = True

    def __enter__(self):
        """Set terminal to raw mode for non-blocking input"""
        try:
            if sys.stdin.isatty():
                self.old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            else:
                self.enabled = False
        except:
            self.enabled = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore terminal settings"""
        if self.old_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            except:
                pass

    def get_key(self, timeout: float = 0.0) -> Optional[str]:
        """Get a key press without blocking. Returns None if no key pressed."""
        if not self.enabled:
            return None
        if select.select([sys.stdin], [], [], timeout)[0]:
            ch = sys.stdin.read(1)
            # Handle escape sequences (arrow keys)
            if ch == '\x1b':
                # Give a bit more time for the rest of the escape sequence
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        if select.select([sys.stdin], [], [], 0.1)[0]:
                            ch3 = sys.stdin.read(1)
                            if ch3 == 'A':
                                return 'UP'
                            elif ch3 == 'B':
                                return 'DOWN'
                            elif ch3 == 'C':
                                return 'RIGHT'
                            elif ch3 == 'D':
                                return 'LEFT'
                return 'ESC'  # Just ESC key pressed
            return ch
        return None


class FanController:
    """Controls and monitors system fans and temperatures"""

    def __init__(self, hwmon_path: str = "/sys/class/hwmon/hwmon3", history_size: int = 60):
        self.hwmon_path = Path(hwmon_path)

        # Temperature control curve parameters
        self.temp_min = 45.0  # Minimum speed temperature (°C)
        self.temp_max = 80.0  # Maximum speed temperature (°C)
        self.pwm_min = 10     # Minimum PWM value (0-255) ~4%
        self.pwm_max = 255    # Maximum PWM value (0-255) 100%

        # History tracking
        self.history_size = history_size
        self.temp_history = deque(maxlen=history_size)
        self.fan_history = deque(maxlen=history_size)

        # Manual control
        self.manual_pwm_offset = 0  # Offset from auto value for manual adjustment

        # Terminal size detection
        try:
            terminal_size = shutil.get_terminal_size(fallback=(140, 40))
            self.term_width = terminal_size.columns
        except:
            self.term_width = 140  # Default fallback

        # ANSI color codes
        self.COLOR_GREEN = '\033[92m'
        self.COLOR_YELLOW = '\033[93m'
        self.COLOR_RED = '\033[91m'
        self.COLOR_CYAN = '\033[96m'
        self.COLOR_RESET = '\033[0m'

        # Auto-detect sensors, fans, and PWM controls
        self.temp_sensors = []  # List of (path, label) tuples
        self.fan_sensors = []   # List of (path, label) tuples
        self.pwm_controls = []  # List of (path, enable_path, label) tuples
        self._detect_hardware()

    def read_file(self, path: Path) -> str:
        """Read a sysfs file and return its contents"""
        try:
            return path.read_text().strip()
        except (FileNotFoundError, PermissionError) as e:
            return None

    def write_file(self, path: Path, value: str) -> bool:
        """Write a value to a sysfs file"""
        try:
            path.write_text(value)
            return True
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Error writing to {path}: {e}")
            return False

    def _detect_hardware(self):
        """Auto-detect available temperature sensors, fans, and PWM controls"""
        hwmon_base = Path("/sys/class/hwmon")

        if not hwmon_base.exists():
            print("Warning: /sys/class/hwmon not found")
            return

        # Scan all hwmon devices
        for hwmon_dir in sorted(hwmon_base.iterdir()):
            if not hwmon_dir.is_symlink() and not hwmon_dir.is_dir():
                continue

            # Get device name
            name_file = hwmon_dir / "name"
            device_name = self.read_file(name_file) if name_file.exists() else hwmon_dir.name

            # Detect temperature sensors
            for temp_file in sorted(hwmon_dir.glob("temp*_input")):
                # Get label if available
                label_file = temp_file.parent / temp_file.name.replace("_input", "_label")
                if label_file.exists():
                    label = self.read_file(label_file)
                else:
                    # Generate label from device name and temp number
                    temp_num = temp_file.name.replace("temp", "").replace("_input", "")
                    label = f"{device_name}_temp{temp_num}"

                self.temp_sensors.append((temp_file, label))

            # Detect fan sensors
            for fan_file in sorted(hwmon_dir.glob("fan*_input")):
                # Get label if available
                label_file = fan_file.parent / fan_file.name.replace("_input", "_label")
                if label_file.exists():
                    label = self.read_file(label_file)
                else:
                    # Generate label from device name and fan number
                    fan_num = fan_file.name.replace("fan", "").replace("_input", "")
                    label = f"{device_name}_fan{fan_num}"

                self.fan_sensors.append((fan_file, label))

            # Detect PWM controls (only from the configured hwmon device for safety)
            if hwmon_dir.resolve() == self.hwmon_path.resolve():
                for pwm_file in sorted(hwmon_dir.glob("pwm[0-9]*")):
                    # Skip files like pwm1_enable, pwm1_mode, etc.
                    if '_' in pwm_file.name:
                        continue

                    pwm_num = pwm_file.name.replace("pwm", "")
                    enable_file = pwm_file.parent / f"pwm{pwm_num}_enable"

                    # Only add if enable file exists (means it's controllable)
                    if enable_file.exists():
                        label = f"PWM{pwm_num}"
                        self.pwm_controls.append((pwm_file, enable_file, label))

        # Check for NVIDIA GPU
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,temperature.gpu", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # Add GPU as a virtual temperature sensor
                gpu_name = result.stdout.strip().split(',')[0].strip()
                self.temp_sensors.append(("nvidia-smi", gpu_name))
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass  # NVIDIA tools not available or GPU not present

        # Print detection summary
        print(f"🔍 Detected {len(self.temp_sensors)} temperature sensor(s)")
        print(f"🔍 Detected {len(self.fan_sensors)} fan sensor(s)")
        print(f"🔍 Detected {len(self.pwm_controls)} PWM control(s)")

    def get_temperatures(self) -> Dict[str, float]:
        """Get all available temperature sensors"""
        temps = {}

        for sensor_path, label in self.temp_sensors:
            # Handle NVIDIA GPU specially
            if sensor_path == "nvidia-smi":
                try:
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        temp = float(result.stdout.strip())
                        temps[label] = temp
                except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
                    pass  # GPU temp unavailable
            else:
                # Regular sysfs sensor
                value = self.read_file(sensor_path)
                if value:
                    try:
                        temp_c = int(value) / 1000.0
                        # Skip invalid readings
                        if 0 < temp_c < 120:
                            temps[label] = temp_c
                    except (ValueError, TypeError):
                        pass  # Skip invalid values

        return temps

    def get_fan_speeds(self) -> Dict[str, int]:
        """Get current fan speeds in RPM"""
        speeds = {}

        for fan_path, label in self.fan_sensors:
            value = self.read_file(fan_path)
            if value:
                try:
                    rpm = int(value)
                    # Skip invalid readings (0 RPM often means disconnected fan)
                    if rpm > 0:
                        speeds[label] = rpm
                except (ValueError, TypeError):
                    pass  # Skip invalid values

        return speeds

    def get_pwm_values(self) -> Dict[str, Tuple[int, int]]:
        """Get current PWM values and modes (value, mode)"""
        pwm_info = {}

        for pwm_path, enable_path, label in self.pwm_controls:
            pwm_num = pwm_path.name.replace("pwm", "")
            mode_path = pwm_path.parent / f"pwm{pwm_num}_mode"

            value = self.read_file(pwm_path)
            mode = self.read_file(mode_path)
            enable = self.read_file(enable_path)

            if value:
                try:
                    pwm_value = int(value)
                    pwm_percent = pwm_value / 255.0 * 100

                    mode_str = "PWM" if mode == "1" else "DC" if mode else "unknown"
                    enable_str = {
                        "0": "off/full",
                        "1": "manual",
                        "2": "auto",
                        "3": "auto",
                        "4": "auto",
                        "5": "auto"
                    }.get(enable, "unknown")

                    pwm_info[label] = (pwm_value, pwm_percent, mode_str, enable_str)
                except (ValueError, TypeError):
                    pass  # Skip invalid values

        return pwm_info

    def calculate_pwm_from_temp(self, temp: float) -> int:
        """Calculate PWM value based on temperature using linear curve"""
        if temp <= self.temp_min:
            return self.pwm_min
        elif temp >= self.temp_max:
            return self.pwm_max
        else:
            # Linear interpolation
            ratio = (temp - self.temp_min) / (self.temp_max - self.temp_min)
            pwm = self.pwm_min + ratio * (self.pwm_max - self.pwm_min)
            return int(pwm)

    def set_pwm_manual_mode(self, pwm_path: Path, enable_path: Path) -> bool:
        """Set a PWM channel to manual mode"""
        return self.write_file(enable_path, "1")

    def restore_bios_control(self, enable_path: Path) -> bool:
        """Restore BIOS/automatic control for a PWM channel"""
        # Try to write "2" for auto mode
        write_result = self.write_file(enable_path, "2")

        # Verify the write was successful by reading back
        if write_result:
            actual_value = self.read_file(enable_path)
            if actual_value != "2":
                return False

        return write_result

    def restore_all_bios_control(self):
        """Restore BIOS/automatic control for all PWM channels"""
        print("\n🔄 Restoring BIOS control for all fans...")
        success_count = 0
        failed_pwms = []

        for pwm_path, enable_path, label in self.pwm_controls:
            if self.restore_bios_control(enable_path):
                success_count += 1
                print(f"  {label}: ✓ Restored to BIOS control (auto mode)")
            else:
                failed_pwms.append(label)
                print(f"  {label}: ✗ Failed to restore BIOS control")
                # For channels that don't support auto mode, keep them in manual
                # but set a safe PWM value (medium speed)
                print(f"  {label}: Setting to safe speed (50%) in manual mode")
                self.write_file(pwm_path, "128")  # 50% speed

        total_pwms = len(self.pwm_controls)
        if success_count == total_pwms:
            print(f"✓ Successfully restored BIOS control for all {total_pwms} PWM channels")
        else:
            print(f"⚠ Restored BIOS control for {success_count}/{total_pwms} PWM channels")
            print(f"  Failed PWMs set to 50% manual speed: {', '.join(failed_pwms)}")

    def set_pwm_value(self, pwm_path: Path, value: int) -> bool:
        """Set PWM value (0-255)"""
        if not 0 <= value <= 255:
            print(f"Invalid PWM value: {value} (must be 0-255)")
            return False

        return self.write_file(pwm_path, str(value))

    def get_temp_color(self, temp: float) -> str:
        """Get color code based on temperature"""
        if temp < 50:
            return self.COLOR_GREEN
        elif temp < 70:
            return self.COLOR_YELLOW
        else:
            return self.COLOR_RED

    def get_fan_color(self, rpm: float, max_rpm: float = 3000) -> str:
        """Get color code based on fan speed"""
        percent = (rpm / max_rpm) * 100
        if percent < 40:
            return self.COLOR_GREEN
        elif percent < 70:
            return self.COLOR_YELLOW
        else:
            return self.COLOR_RED

    def record_history(self, max_temp: float, avg_fan_speed: float):
        """Record temperature and fan speed to history"""
        self.temp_history.append(max_temp)
        self.fan_history.append(avg_fan_speed)

    def create_vertical_bars(self, data: deque, max_value: float, width: int = 60, height: int = 8,
                            is_temp: bool = True) -> List[str]:
        """Create vertical bar chart from historical data with color coding"""
        if not data:
            return ["░" * width] * height

        # Prepare data - average if we have more points than width
        data_points = len(data)
        display_data = []

        if data_points <= width:
            # Show each point
            display_data = list(data)
            # Pad with zeros if needed
            display_data.extend([0] * (width - len(display_data)))
        else:
            # Average multiple points per column
            points_per_col = data_points / width
            for i in range(width):
                start_idx = int(i * points_per_col)
                end_idx = int((i + 1) * points_per_col)
                chunk = list(data)[start_idx:end_idx]
                if chunk:
                    display_data.append(sum(chunk) / len(chunk))
                else:
                    display_data.append(0)

        # Create the vertical bars with colors
        lines = []
        for row in range(height, 0, -1):
            line_chars = []
            threshold = (row / height) * max_value
            for value in display_data:
                # Determine color based on value
                if is_temp:
                    color = self.get_temp_color(value)
                else:
                    color = self.get_fan_color(value, max_value)

                if value >= threshold:
                    line_chars.append(color + '█' + self.COLOR_RESET)
                elif value >= threshold - (max_value / height / 2):
                    # Half block for smoother transition
                    line_chars.append(color + '▄' + self.COLOR_RESET)
                else:
                    line_chars.append(' ')
            lines.append(''.join(line_chars))

        return lines

    def clear_screen(self):
        """Clear screen and move cursor to top using ANSI escape codes"""
        print("\033[H\033[J", end="", flush=True)

    def display_status(self, clear: bool = False, show_history: bool = False, control_info: str = ""):
        """Display current temperatures and fan speeds"""
        # Build entire output in memory first for instant redraw
        output = []

        # Get all data first
        temps = self.get_temperatures()
        speeds = self.get_fan_speeds()
        pwm_info = self.get_pwm_values()
        max_temp = max(temps.values()) if temps else 0
        avg_fan_speed = sum(speeds.values()) / len(speeds) if speeds else 0

        # Record history
        if show_history:
            self.record_history(max_temp, avg_fan_speed)

        # Calculate display widths based on terminal size
        sep_width = min(self.term_width, 140)

        # Find maximum label lengths for each section
        max_temp_label = max(len(name) for name in temps.keys()) if temps else 12
        max_fan_label = max(len(name) for name in speeds.keys()) if speeds else 12
        max_pwm_label = max(len(name) for name in pwm_info.keys()) if pwm_info else 12

        # Calculate bar widths dynamically to fill the terminal width
        # Temperature format: "  {name:Ns}: {temp:5.1f}°C  [{bar}]"
        # Fixed parts: 2 (indent) + N (label) + 2 (": ") + 5 (temp) + 2 ("°C") + 2 ("  ") + 1 ("[") + 1 ("]") = 15 + N
        temp_bar_width = max(20, sep_width - (15 + max_temp_label))

        # Fan speed format: "  {name:Ns}: {rpm:4d} RPM  [{bar}]"
        # Fixed parts: 2 + N + 2 + 4 + 4 + 2 + 1 + 1 = 16 + N
        fan_bar_width = max(20, sep_width - (16 + max_fan_label))

        # PWM format: "  {name:Ns}: {value:3d}/255 ({percent:5.1f}%)  [{bar}]"
        # Fixed parts: 2 + N + 2 + 3 + 4 + 2 + 5 + 3 + 2 + 1 + 1 = 25 + N
        pwm_bar_width = max(20, sep_width - (25 + max_pwm_label))

        # Build output
        output.append("\n" + "=" * sep_width)
        output.append("SYSTEM MONITORING")
        output.append("=" * sep_width)

        # Display temperatures
        output.append("\n📊 TEMPERATURES:")
        output.append("-" * sep_width)

        for name, temp in sorted(temps.items()):
            bar_length = int(temp / 100 * temp_bar_width)
            color = self.get_temp_color(temp)
            bar = color + "█" * bar_length + self.COLOR_RESET + "░" * (temp_bar_width - bar_length)
            output.append(f"  {name:{max_temp_label}s}: {temp:5.1f}°C  [{bar}]")

        max_temp_color = self.get_temp_color(max_temp)
        output.append(f"\n  {'Max Temp':{max_temp_label}s}: {max_temp_color}{max_temp:5.1f}°C{self.COLOR_RESET}")

        # Display fan speeds
        output.append("\n🌀 FAN SPEEDS:")
        output.append("-" * sep_width)

        for name, rpm in sorted(speeds.items()):
            bar_length = int(min(rpm / 3000 * fan_bar_width, fan_bar_width))
            color = self.get_fan_color(rpm, 3000)
            bar = color + "█" * bar_length + self.COLOR_RESET + "░" * (fan_bar_width - bar_length)
            output.append(f"  {name:{max_fan_label}s}: {rpm:4d} RPM  [{bar}]")

        avg_color = self.get_fan_color(avg_fan_speed, 3000)
        output.append(f"\n  {'Avg Speed':{max_fan_label}s}: {avg_color}{avg_fan_speed:4.0f} RPM{self.COLOR_RESET}")

        # Display PWM values
        output.append("\n⚙️  PWM CONTROLS:")
        output.append("-" * sep_width)

        for name, (value, percent, mode, enable) in sorted(pwm_info.items()):
            bar_length = int(percent / 100 * pwm_bar_width)
            # Color based on PWM percentage (similar to fan speed)
            if percent < 40:
                color = self.COLOR_GREEN
            elif percent < 70:
                color = self.COLOR_YELLOW
            else:
                color = self.COLOR_RED
            bar = color + "█" * bar_length + self.COLOR_RESET + "░" * (pwm_bar_width - bar_length)
            output.append(f"  {name:{max_pwm_label}s}: {value:3d}/255 ({percent:5.1f}%)  [{bar}]")

        # Display history graphs
        if show_history and len(self.temp_history) > 1:
            output.append("\n📈 HISTORY:")
            output.append("-" * sep_width)

            # Calculate graph width to match separator width
            # Need room for: "  100.0 │" (9 chars) + graph + "│" (1 char) = 10 + graph
            # Don't limit by history_size - create_vertical_bars will compress data to fit
            graph_width = sep_width - 10

            # Temperature history
            temp_min = min(self.temp_history)
            temp_max_val = max(self.temp_history)
            # self.temp_history.maxlen = graph_width
            temp_bars = self.create_vertical_bars(self.temp_history, 100.0, width=graph_width, height=8, is_temp=True)
            temp_color = self.get_temp_color(max_temp)
            output.append(f"  Temperature (°C)  Max: {temp_max_val:.1f}  Min: {temp_min:.1f}  Current: {temp_color}{max_temp:.1f}{self.COLOR_RESET}")
            for i, line in enumerate(temp_bars):
                value = 100.0 * (8 - i) / 8
                output.append(f"  {value:5.1f} │{line}│")
            output.append(f"    0.0 └{'─' * graph_width}┘")

            output.append("")  # Blank line between graphs

            # Fan speed history
            fan_min = min(self.fan_history)
            fan_max_val = max(self.fan_history)
            # self.fan_history.maxlen = graph_width;
            fan_bars = self.create_vertical_bars(self.fan_history, 3000.0, width=graph_width, height=8, is_temp=False)
            fan_color = self.get_fan_color(avg_fan_speed, 3000)
            output.append(f"  Fan Speed (RPM)   Max: {fan_max_val:.0f}  Min: {fan_min:.0f}  Current: {fan_color}{avg_fan_speed:.0f}{self.COLOR_RESET}")
            for i, line in enumerate(fan_bars):
                value = 3000.0 * (8 - i) / 8
                output.append(f"  {value:5.0f} │{line}│")
            output.append(f"      0 └{'─' * graph_width}┘")
            output.append(f"        Last {len(self.temp_history)} samples")

        # Control information
        if control_info:
            output.append("")
            output.append(control_info)

        output.append("=" * sep_width)

        # Clear and print all at once
        if clear:
            self.clear_screen()
        print("\n".join(output), flush=True)

        return max_temp

    def auto_control(self, interval: float = 2.0, max_iterations: int = None):
        """Automatically control fans based on temperature"""
        print("\n🤖 AUTOMATIC FAN CONTROL ENABLED")
        print(f"Temperature range: {self.temp_min}°C - {self.temp_max}°C")
        print(f"PWM range: {self.pwm_min}/255 ({self.pwm_min/255*100:.1f}%) - {self.pwm_max}/255 ({self.pwm_max/255*100:.1f}%)")
        if max_iterations:
            print(f"Test mode: Running for {max_iterations} iterations")
        print("\nControls: [Q]uit  [W]Increase  [S]Decrease fan speed\n")

        # Set all PWM channels to manual mode
        print("Setting PWM channels to manual mode...")
        for pwm_path, enable_path, label in self.pwm_controls:
            if not self.set_pwm_manual_mode(pwm_path, enable_path):
                print(f"Warning: Could not set {label} to manual mode")

        time.sleep(1)

        try:
            with KeyboardHandler() as kb:
                try:
                    first_iteration = True
                    last_update = time.time()
                    force_update = False
                    iteration_count = 0

                    while True:
                        current_time = time.time()

                        # Check for keyboard input
                        key = kb.get_key(timeout=0.05)
                        if key:
                            if key in ('q', 'Q'):
                                break
                            elif key in ('w', 'W', 'UP'):
                                self.manual_pwm_offset = min(self.manual_pwm_offset + 10, 255)
                                force_update = True
                            elif key in ('s', 'S', 'DOWN'):
                                self.manual_pwm_offset = max(self.manual_pwm_offset - 10, -255)
                                force_update = True

                        # Update display at intervals or when forced
                        if force_update or current_time - last_update >= interval:
                            # Get maximum temperature
                            temps = self.get_temperatures()
                            if not temps:
                                print("No temperature readings available!")
                                time.sleep(interval)
                                continue

                            max_temp = max(temps.values())

                            # Calculate PWM value with manual offset
                            base_pwm = self.calculate_pwm_from_temp(max_temp)
                            pwm_value = max(0, min(255, base_pwm + self.manual_pwm_offset))

                            # Set all PWM channels
                            for pwm_path, enable_path, label in self.pwm_controls:
                                self.set_pwm_value(pwm_path, pwm_value)

                            # Build control info
                            control_info = f"🎯 Control: Max temp = {max_temp:.1f}°C → Base PWM = {base_pwm}/255"
                            if self.manual_pwm_offset != 0:
                                control_info += f"  Offset: {self.manual_pwm_offset:+d} → Final PWM = {pwm_value}/255 ({pwm_value/255*100:.1f}%)"
                            else:
                                control_info += f" → PWM = {pwm_value}/255 ({pwm_value/255*100:.1f}%)"
                            control_info += f"\n⌨️  Controls: [Q]uit  [W]Increase  [S]Decrease  |  Offset: {self.manual_pwm_offset:+d}"

                            # Display status (clear screen after first iteration)
                            self.display_status(clear=not first_iteration, show_history=True, control_info=control_info)
                            first_iteration = False
                            last_update = current_time
                            force_update = False
                            iteration_count += 1

                            # Check if we've reached max iterations
                            if max_iterations and iteration_count >= max_iterations:
                                break

                except KeyboardInterrupt:
                    print("\n\n⚠️  Interrupted by user...")
        finally:
            # Always restore BIOS control when exiting, even if there was an error
            self.restore_all_bios_control()


def get_config_path():
    """Get the path to the config file"""
    config_dir = Path.home() / '.config' / 'fan_control'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / 'fan_control.conf'


def create_default_config():
    """Create default config content"""
    return """# Fan Control Configuration
# Lines starting with # are comments

# Hardware monitor device path
hwmon_path = /sys/class/hwmon/hwmon3

# Temperature range (Celsius)
temp_min = 45.0
temp_max = 80.0

# PWM range (0-255)
pwm_min = 10
pwm_max = 255

# Update interval in seconds
interval = 2.0

# History size (number of samples to keep)
history_size = 60
"""


def load_config():
    """Load configuration from file"""
    config_path = get_config_path()
    default_config = {
        'interval': 2.0,
        'temp_min': 45.0,
        'temp_max': 80.0,
        'pwm_min': 10,
        'pwm_max': 255,
        'history_size': 60,
        'hwmon_path': '/sys/class/hwmon/hwmon3'
    }

    if not config_path.exists():
        # Create default config file
        try:
            with open(config_path, 'w') as f:
                f.write(create_default_config())
            print(f"Created default config file at {config_path}")
        except Exception as e:
            print(f"Warning: Could not create config file: {e}")
        return default_config

    # Parse existing config
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # Parse key = value
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Convert to appropriate type
                    if key in ['temp_min', 'temp_max', 'interval']:
                        default_config[key] = float(value)
                    elif key in ['pwm_min', 'pwm_max', 'history_size']:
                        default_config[key] = int(value)
                    elif key == 'hwmon_path':
                        default_config[key] = value
    except Exception as e:
        print(f"Warning: Could not load config file: {e}")

    return default_config


def save_config(config):
    """Save configuration to file"""
    config_path = get_config_path()
    try:
        content = f"""# Fan Control Configuration
# Lines starting with # are comments

# Hardware monitor device path
hwmon_path = {config.get('hwmon_path', '/sys/class/hwmon/hwmon3')}

# Temperature range (Celsius)
temp_min = {config.get('temp_min', 45.0)}
temp_max = {config.get('temp_max', 80.0)}

# PWM range (0-255)
pwm_min = {config.get('pwm_min', 10)}
pwm_max = {config.get('pwm_max', 255)}

# Update interval in seconds
interval = {config.get('interval', 2.0)}

# History size (number of samples to keep)
history_size = {config.get('history_size', 60)}
"""
        with open(config_path, 'w') as f:
            f.write(content)
        print(f"Configuration saved to {config_path}")
        return True
    except Exception as e:
        print(f"Error: Could not save config file: {e}")
        return False


def main():
    # Load config first
    config = load_config()

    parser = argparse.ArgumentParser(description='Fan Control Monitor')
    parser.add_argument('command', nargs='?', choices=['set'], default=None,
                       help='Command: "set" to save current flags to config')
    parser.add_argument('-w', '--watch', action='store_true',
                       help='Continuously monitor (update every 2 seconds)')
    parser.add_argument('-a', '--auto', action='store_true',
                       help='Enable automatic fan control based on temperature')
    parser.add_argument('-i', '--interval', type=float, default=None,
                       help=f'Update interval in seconds (config: {config["interval"]})')
    parser.add_argument('--hwmon', type=str, default=None,
                       help=f'Path to hwmon device (config: {config["hwmon_path"]})')
    parser.add_argument('--temp-min', type=float, default=None,
                       help=f'Minimum temperature for fan curve (config: {config["temp_min"]}°C)')
    parser.add_argument('--temp-max', type=float, default=None,
                       help=f'Maximum temperature for fan curve (config: {config["temp_max"]}°C)')
    parser.add_argument('--pwm-min', type=int, default=None,
                       help=f'Minimum PWM value 0-255 (config: {config["pwm_min"]})')
    parser.add_argument('--pwm-max', type=int, default=None,
                       help=f'Maximum PWM value 0-255 (config: {config["pwm_max"]})')
    parser.add_argument('--history-size', type=int, default=None,
                       help=f'Number of history samples to keep (config: {config["history_size"]})')
    parser.add_argument('-n', '--iterations', type=int, default=None,
                       help='Number of iterations before exiting (for testing)')

    args = parser.parse_args()

    # Merge command line args with config (command line takes precedence)
    interval = args.interval if args.interval is not None else config['interval']
    hwmon_path = args.hwmon if args.hwmon is not None else config['hwmon_path']
    temp_min = args.temp_min if args.temp_min is not None else config['temp_min']
    temp_max = args.temp_max if args.temp_max is not None else config['temp_max']
    pwm_min = args.pwm_min if args.pwm_min is not None else config['pwm_min']
    pwm_max = args.pwm_max if args.pwm_max is not None else config['pwm_max']
    history_size = args.history_size if args.history_size is not None else config['history_size']

    # If "set" command is used, save config and exit
    if args.command == 'set':
        new_config = {
            'interval': interval,
            'hwmon_path': hwmon_path,
            'temp_min': temp_min,
            'temp_max': temp_max,
            'pwm_min': pwm_min,
            'pwm_max': pwm_max,
            'history_size': history_size
        }
        save_config(new_config)
        return

    controller = FanController(hwmon_path=hwmon_path, history_size=history_size)
    controller.temp_min = temp_min
    controller.temp_max = temp_max
    controller.pwm_min = pwm_min
    controller.pwm_max = pwm_max

    # Check if running as root
    is_root = os.geteuid() == 0

    # Determine behavior based on user privileges and flags
    if not is_root:
        # Non-root users can only watch (no fan control)
        if args.auto:
            print("⚠️  Warning: Automatic fan control requires root privileges.")
            print("Running in watch mode instead.\n")
        # Force watch mode for non-root users
        args.watch = True
        args.auto = False
    else:
        # Root user without any flags: default to auto mode
        if not args.auto and not args.watch:
            args.auto = True

    if args.auto:
        # Root user with --auto flag: control fans
        controller.auto_control(interval=interval, max_iterations=args.iterations)
    elif args.watch:
        if args.iterations:
            print(f"Controls: [Q]uit to stop | Test mode: Running for {args.iterations} iterations\n")
        else:
            print("Controls: [Q]uit to stop\n")
        time.sleep(0.5)

        with KeyboardHandler() as kb:
            try:
                first_iteration = True
                last_update = time.time()
                iteration_count = 0

                while True:
                    current_time = time.time()

                    # Check for keyboard input
                    key = kb.get_key(timeout=0.05)
                    if key:
                        if key in ('q', 'Q'):
                            break

                    # Update display at intervals
                    if current_time - last_update >= interval:
                        control_info = "⌨️  Controls: [Q]uit"
                        controller.display_status(clear=not first_iteration, show_history=True, control_info=control_info)
                        first_iteration = False
                        last_update = current_time
                        iteration_count += 1

                        # Check if we've reached max iterations
                        if args.iterations and iteration_count >= args.iterations:
                            break

            except KeyboardInterrupt:
                pass

        print("\n\nStopped monitoring.")
    else:
        controller.display_status()


if __name__ == "__main__":
    main()
