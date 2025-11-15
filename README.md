# Fan Control Script

A Python script for monitoring and automatically controlling system fans on Linux using the hwmon interface.

## System Information

- **Hardware**: NCT6797 fan controller
- **Fans**: 7 fans total (3 PWM + 4 DC capable)
- **Pump**: 1 pump
- **Control**: All 7 channels can use PWM control

## Features

- 📊 Real-time temperature monitoring from multiple sensors
- 🌀 Fan speed monitoring (RPM)
- ⚙️ PWM control status display
- 🤖 Automatic fan control based on temperature curves
- 📈 Visual progress bars and history graphs with color coding
- 🎨 Color-coded bars (green=low, yellow=medium, red=high)
- ⌨️ Interactive keyboard controls (W/S to adjust fan speed, Q to quit)
- 📝 Plain text configuration file with easy editing

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

### 1. View Current Status (Single Snapshot)

```bash
./fan_monitor.py
```

Displays current temperatures, fan speeds, and PWM values once.

### 2. Continuous Monitoring

```bash
./fan_monitor.py --watch
```

Updates the display every 2 seconds. Press **Q** to quit.

### 3. Automatic Fan Control

**⚠️ IMPORTANT**: This requires root/sudo privileges to write to sysfs!

```bash
sudo ./fan_monitor.py --auto
```

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

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `-w, --watch` | Continuously monitor and update display | Off |
| `-a, --auto` | Enable automatic fan control | Off |
| `-i, --interval` | Update interval in seconds | 2.0 |
| `--temp-min` | Minimum temperature for fan curve (°C) | 45 |
| `--temp-max` | Maximum temperature for fan curve (°C) | 80 |
| `--pwm-min` | Minimum PWM value (0-255) | 10 |
| `--pwm-max` | Maximum PWM value (0-255) | 255 |
| `--history-size` | Number of history samples | 60 |
| `--hwmon` | Path to hwmon device | /sys/class/hwmon/hwmon3 |

## Keyboard Controls

### Watch Mode
- **Q** - Quit monitoring

### Auto Control Mode
- **W** - Increase fan speed (+10 PWM offset)
- **S** - Decrease fan speed (-10 PWM offset)
- **Q** - Quit auto control

The offset is applied to the automatic temperature-based PWM calculation, allowing you to fine-tune fan speed in real-time while maintaining the automatic temperature response.

## Temperature Sensors

The script monitors:
- **CPU Package**: Main CPU temperature
- **CPUTIN**: CPU temperature (from motherboard)
- **SYSTIN**: System temperature
- **AUXTIN0-2**: Auxiliary temperature sensors
- **NVMe**: NVMe SSD temperature

## PWM Control Details

- **PWM Range**: 0-255 (0 = off, 255 = 100%)
- **Mode**: PWM (Pulse Width Modulation) or DC
- **Enable States**:
  - `off/full`: Hardware control or full speed
  - `manual`: Software controlled (required for auto mode)
  - `auto`: BIOS/hardware automatic control

## Safety Notes

1. **Root Privileges**: Automatic control requires `sudo` to write to `/sys/class/hwmon/`
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

## Running at Startup

To run automatic fan control at boot, you can create a systemd service. Create `/etc/systemd/system/fan-control.service`:

```ini
[Unit]
Description=Automatic Fan Control
After=multi-user.target

[Service]
Type=simple
ExecStart=/home/ilya/Projects/fan_control/fan_monitor.py --auto --temp-min 45 --temp-max 80
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

Then enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fan-control.service
sudo systemctl start fan-control.service
```

## License

Free to use and modify as needed.
