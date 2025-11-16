#!/bin/bash
# Fan Control Installation Script

set -e  # Exit on error

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

echo "Installing Fan Control..."

# Install the script
echo "- Installing fan_control.py to /usr/local/bin/"
cp -f fan_control.py /usr/local/bin/
chmod +x /usr/local/bin/fan_control.py

# Install the service file
echo "- Installing fan-control.service to /etc/systemd/system/"
cp -f fan-control.service /etc/systemd/system/

# Reload systemd
echo "- Reloading systemd daemon"
systemctl daemon-reload

# Check if service is already enabled
if systemctl is-enabled fan-control.service &>/dev/null; then
    echo "- Service is already enabled"
    SERVICE_ENABLED=true
else
    echo "- Service is not enabled yet"
    SERVICE_ENABLED=false
fi

# Check if service is running
if systemctl is-active fan-control.service &>/dev/null; then
    echo "- Restarting fan-control.service"
    systemctl restart fan-control.service
    SERVICE_RESTARTED=true
else
    echo "- Service is not running"
    SERVICE_RESTARTED=false
fi

echo ""
echo "Installation complete!"
echo ""

# Show next steps
if [ "$SERVICE_ENABLED" = false ]; then
    echo "To enable the service at boot:"
    echo "  sudo systemctl enable fan-control.service"
    echo ""
fi

if [ "$SERVICE_RESTARTED" = false ]; then
    echo "To start the service now:"
    echo "  sudo systemctl start fan-control.service"
    echo ""
fi

echo "Useful commands:"
echo "  sudo systemctl status fan-control.service   # Check service status"
echo "  sudo journalctl -u fan-control.service -f   # View live logs"
echo "  sudo systemctl stop fan-control.service     # Stop the service"
echo "  /usr/local/bin/fan_control.py --help        # View command options"
echo ""
