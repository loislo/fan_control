# Fan Control Script

A Python script for monitoring and automatically controlling system fans on Linux using the hwmon interface.

## ⚠️ DISCLAIMER

**USE AT YOUR OWN RISK!**

This software directly controls your computer's cooling system. Improper use may result in:
- Hardware overheating and potential damage
- System instability or crashes
- Voided warranties
- Data loss

**By using this software, you acknowledge that:**
- You understand the risks involved in manual fan control
- You are responsible for monitoring your system temperatures
- The authors are NOT liable for any damage to your hardware, data loss, or any other consequences
- This software is provided "AS IS" without warranty of any kind, express or implied
- You should test carefully and monitor temperatures when first using this script

**Recommendations:**
- Start with conservative settings (higher minimum fan speeds)
- Monitor your system temperatures closely when first using the script
- Have temperature monitoring tools ready (e.g., `sensors`, `htop`)
- Test the `--test-pwm` feature to verify your fans respond correctly
- Keep BIOS fan control as a fallback option

## System Information

- **Hardware**: NCT6797 fan controller
- **Fans**: 7 fans total (3 PWM + 4 DC capable)
- **Pump**: 1 pump
- **Control**: All 7 channels can use PWM control

## Features

- 📊 Real-time temperature monitoring from multiple sensors
  - Auto-detects all available sensors (CPU, GPU, motherboard, NVMe)
  - Highlights sensors used for fan control (cyan color)
  - Smart filtering: displays all temps, but only uses CPU cores + GPU for control
- 🌀 Fan speed monitoring (RPM)
- ⚙️ PWM control status display
- 🤖 Automatic fan control based on temperature curves
- 📈 Visual progress bars and history graphs with color coding
- 🎨 Color-coded bars (green=low, yellow=medium, red=high)
- ⌨️ Interactive keyboard controls (W/S to adjust fan speed, Q to quit)
- 📝 Plain text configuration file with easy editing
- 🔬 PWM channel testing to verify fans respond correctly
  - Quick test: validates current BIOS configuration
  - Comprehensive test: detects optimal PWM/DC mode

## Configuration

The script uses a plain text configuration file located at `~/.config/fan_control/fan_control.conf`.

On first run, a default config file is created automatically. You can edit it manually or use the `set` command.

### Configuration File Format

```
# Fan Control Configuration
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
```

### Updating Configuration

**Method 1: Edit the file directly**
```bash
nano ~/.config/fan_control/fan_control.conf
```

**Method 2: Use the `set` command**
```bash
# Update temperature range and save to config
./fan_monitor.py set --temp-min 40 --temp-max 75

# Update PWM limits and save to config
./fan_monitor.py set --pwm-min 20 --pwm-max 255

# Update multiple settings at once
./fan_monitor.py set --temp-min 40 --temp-max 75 --pwm-min 20 --interval 1.0
```

The `set` command saves the specified flags to the config file for future use.

### Using Configuration

- By default, all values are loaded from the config file
- Command-line flags override config values for that run only
- Use `set` command with flags to permanently update the config

**Example:**
```bash
# Uses config values (temp_min=45, temp_max=80)
./fan_monitor.py --watch

# Override temp range for this run only (config unchanged)
./fan_monitor.py --watch --temp-min 40 --temp-max 70

# Permanently change config
./fan_monitor.py set --temp-min 40 --temp-max 70

# Now uses new config values
./fan_monitor.py --watch
```

## Usage

The script automatically adapts its behavior based on user privileges:

- **Non-root users**: Automatically runs in continuous monitoring mode (watch mode)
- **Root users without flags**: Automatically runs fan control (auto mode)
- **Root users with --watch**: Runs in monitoring-only mode

### 1. Automatic Fan Control (Default for Root)

```bash
sudo ./fan_monitor.py
```

When run as root without flags, automatically controls fans based on temperature.
This is the recommended way to run the script for active cooling management.

### 2. Monitoring Mode Only (Watch)

```bash
./fan_monitor.py --watch
# Or for root users who only want to monitor:
sudo ./fan_monitor.py --watch
```

Updates the display every 2 seconds. Press **Q** to quit.

**Notes**:
- Non-root users automatically run in watch mode
- Root users need the `--watch` flag to monitor without controlling fans

### 3. Explicit Auto Control Mode

```bash
sudo ./fan_monitor.py --auto
```

Explicitly enable automatic fan control (same as running without flags as root).
Automatically adjusts fan speeds based on temperature:
- **45°C**: Minimum fan speed (~4%)
- **80°C**: Maximum fan speed (100%)
- Linear curve between these points

The script uses the **maximum temperature** from all sensors to determine fan speed.

### 4. Custom Temperature Curve

```bash
sudo ./fan_monitor.py --auto --temp-min 40 --temp-max 75 --pwm-min 80 --pwm-max 255
```

This example:
- Starts ramping up at 40°C
- Reaches 100% at 75°C
- Minimum speed is 80/255 (~31%)
- Maximum speed is 255/255 (100%)

### 5. Custom Update Interval

```bash
./fan_monitor.py --watch --interval 5
```

Updates every 5 seconds instead of the default 2 seconds.

### 6. PWM Channel Testing

**Quick Test (Current Mode Only)**
```bash
sudo ./fan_monitor.py --test-pwm
```

Tests each PWM channel in its current BIOS-configured mode (PWM or DC). Takes ~8 seconds per channel.

**Output:**
- ✓ "Working correctly" - Fan responds to PWM changes as expected
- ⚠️ "Not responding" - Fan doesn't respond (misconfiguration or broken/disconnected fan)

**Comprehensive Test (Both Modes)**
```bash
sudo ./fan_monitor.py --test-pwm-full
```

Tests each channel in both PWM and DC modes to detect optimal configuration. Takes ~16 seconds per channel.

**Output:**
- Identifies which mode works better (if both work)
- Detects misconfigurations (e.g., BIOS set to PWM but hardware needs DC)
- Recommends mode changes for better performance

**When to use:**
- Run quick test (`--test-pwm`) after initial setup to verify all fans are working
- Run comprehensive test (`--test-pwm-full`) if you suspect BIOS mode misconfiguration
- Run before enabling automatic control to ensure fans respond correctly

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `-w, --watch` | Continuously monitor and update display | Off |
| `-a, --auto` | Enable automatic fan control | Off |
| `-i, --interval` | Update interval in seconds | 2.0 |
| `-n, --iterations` | Number of iterations before exiting (for testing) | None |
| `--temp-min` | Minimum temperature for fan curve (°C) | 45 |
| `--temp-max` | Maximum temperature for fan curve (°C) | 80 |
| `--pwm-min` | Minimum PWM value (0-255) | 10 |
| `--pwm-max` | Maximum PWM value (0-255) | 255 |
| `--history-size` | Number of history samples | 300 |
| `--hwmon` | Path to hwmon device | /sys/class/hwmon/hwmon3 |
| `--test-pwm` | Test PWM channels in current mode (requires root) | Off |
| `--test-pwm-full` | Test PWM channels in both PWM and DC modes (requires root) | Off |

## Keyboard Controls

### Watch Mode
- **Q** - Quit monitoring

### Auto Control Mode
- **W** - Increase fan speed (+10 PWM offset)
- **S** - Decrease fan speed (-10 PWM offset)
- **Q** - Quit auto control

The offset is applied to the automatic temperature-based PWM calculation, allowing you to fine-tune fan speed in real-time while maintaining the automatic temperature response.

## Temperature Sensors

The script **displays** all available temperature sensors including:
- **CPU Cores**: Individual CPU core temperatures (highlighted in cyan)
- **CPU Package**: Overall CPU temperature (highlighted in cyan)
- **NVIDIA GPU**: Graphics card temperature (highlighted in cyan)
- **Motherboard sensors**: CPUTIN, SYSTIN, AUXTIN0-2, PECI Agent
- **Storage**: NVMe SSD temperature (Composite, Sensor 2)
- **System**: WiFi card, PCH, ACPI sensors

**For fan control calculations**, the script uses **only**:
- CPU core temperatures (Core 0-7)
- CPU package temperature
- NVIDIA GPU temperature

Sensors highlighted in **cyan** are used for PWM control. All other sensors are displayed for informational purposes only. This filtering ensures fan speeds respond to the most critical components while avoiding unreliable or irrelevant sensors.

## PWM Control Details

- **PWM Range**: 0-255 (0 = off, 255 = 100%)
- **Mode**: PWM (Pulse Width Modulation) or DC
- **Enable States**:
  - `off/full`: Hardware control or full speed
  - `manual`: Software controlled (required for auto mode)
  - `auto`: BIOS/hardware automatic control

## Safety Notes

1. **Root Privileges**: Automatic control requires `sudo` to write to `/sys/class/hwmon/`
   - Non-root users automatically run in safe monitoring mode only
   - Attempting `--auto` without root privileges will fall back to watch mode with a warning
2. **Fan Stall Prevention**: The default minimum is 10/255 (~4%). Adjust if your fans stall at low speeds
3. **Exit Behavior**: When you stop the script (Ctrl+C or Q), BIOS control is automatically restored
4. **Crash Protection**: The script uses a try/finally block to restore BIOS control even if it crashes
5. **Automatic Restoration**: All PWM channels are set back to auto mode (BIOS control) when the script exits

## Examples

### Silent Operation (Low Temps)
```bash
sudo ./fan_monitor.py --auto --temp-min 50 --temp-max 85 --pwm-min 40
```

### Aggressive Cooling
```bash
sudo ./fan_monitor.py --auto --temp-min 35 --temp-max 70 --pwm-min 100
```

### Monitor Only (No Control)
```bash
./fan_monitor.py --watch --interval 1
```

## Troubleshooting

### Permission Denied Errors
Use `sudo` for automatic control:
```bash
sudo ./fan_monitor.py --auto
```

### Fans Not Responding
Check if PWM is in manual mode:
```bash
cat /sys/class/hwmon/hwmon3/pwm1_enable
```
Should be `1` for manual control.

### Invalid hwmon Path
Find your fan controller:
```bash
ls -la /sys/class/hwmon/
sensors
```
Then use `--hwmon` option with the correct path.

## Installation

### Manual Installation

For system-wide installation:

```bash
# 1. Install the script to system location
sudo cp fan_monitor.py /usr/local/bin/
sudo chmod +x /usr/local/bin/fan_monitor.py

# 2. Run once to create default config in ~/.config/fan_control/
/usr/local/bin/fan_monitor.py --watch --iterations 1

# 3. (Optional) Create system-wide config
sudo mkdir -p /etc/fan_control
sudo cp ~/.config/fan_control/fan_control.conf /etc/fan_control/

# 4. Test the installation
sudo /usr/local/bin/fan_monitor.py --test-pwm
```

### Running at Startup (systemd service)

To run automatic fan control at boot:

```bash
# 1. Copy the service file
sudo cp fan-control.service /etc/systemd/system/

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Enable the service to start at boot
sudo systemctl enable fan-control.service

# 4. Start the service now
sudo systemctl start fan-control.service

# 5. Check status
sudo systemctl status fan-control.service
```

**Managing the service:**

```bash
# View logs
sudo journalctl -u fan-control.service -f

# Stop the service
sudo systemctl stop fan-control.service

# Restart the service
sudo systemctl restart fan-control.service

# Disable auto-start
sudo systemctl disable fan-control.service
```

The service file is included in the repository and will run the script with default config settings. To customize, edit your config file at `~/.config/fan_control/fan_control.conf` or `/etc/fan_control/fan_control.conf`.

## License

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
