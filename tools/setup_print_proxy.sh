#!/bin/bash
# Setup script for ESC/POS Print Proxy Server
# Run this once on the server where Odoo is hosted.

set -e

echo "=== ESC/POS Print Proxy Setup ==="

# Install Python dependencies
echo "Installing Python dependencies..."
pip install flask python-escpos Pillow

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/odoo-print-proxy.service > /dev/null << EOF
[Unit]
Description=Odoo ESC/POS Print Proxy
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${SCRIPT_DIR}
ExecStart=$(which python3) ${SCRIPT_DIR}/print_proxy.py --config ${SCRIPT_DIR}/print_proxy_config.json
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable odoo-print-proxy
sudo systemctl start odoo-print-proxy

echo ""
echo "=== Setup Complete ==="
echo "Print proxy is running on http://localhost:8073"
echo ""
echo "Commands:"
echo "  Status:  sudo systemctl status odoo-print-proxy"
echo "  Logs:    sudo journalctl -u odoo-print-proxy -f"
echo "  Restart: sudo systemctl restart odoo-print-proxy"
echo "  Stop:    sudo systemctl stop odoo-print-proxy"
echo ""
echo "Next steps:"
echo "  1. Edit ${SCRIPT_DIR}/print_proxy_config.json with your printer IP"
echo "  2. Restart the service: sudo systemctl restart odoo-print-proxy"
echo "  3. In Odoo, create a preparation printer with type 'Network ESC/POS'"
