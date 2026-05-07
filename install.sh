#!/usr/bin/env bash
set -e

VILAND_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$VILAND_DIR/.venv"
CONFIG_DIR="$HOME/.config/viland"

echo "Installing viland..."

# Create venv and install dependencies
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    uv venv "$VENV_DIR"
fi

echo "Installing dependencies..."
cd "$VILAND_DIR"
uv sync

# Create config directory
mkdir -p "$CONFIG_DIR"

# Create udevmon config
echo "Creating udevmon config..."
PYTHON_BIN="$VENV_DIR/bin/python"
sudo tee /etc/interception/udevmon.d/viland.yaml > /dev/null << EOF
# Viland config for udevmon (chained with caps2esc)
- JOB: intercept -g $DEVNODE | caps2esc | $PYTHON_BIN -m viland.filter | uinput -d $DEVNODE
  DEVICE:
    EVENTS:
      EV_KEY: [KEY_CAPSLOCK, KEY_ESC, KEY_H, KEY_J, KEY_K, KEY_L, KEY_W, KEY_B, KEY_E, KEY_Q, KEY_I, KEY_A, KEY_0, KEY_G, KEY_D, KEY_Y, KEY_C, KEY_U, KEY_R, KEY_P, KEY_SLASH, KEY_O, KEY_S, KEY_X, KEY_N, KEY_Z, KEY_V]
EOF

# Backup and disable caps2esc if needed
if [ -f /etc/interception/udevmon.d/caps2esc.conf.yaml ]; then
    echo "Backing up caps2esc config..."
    sudo mv /etc/interception/udevmon.d/caps2esc.conf.yaml /etc/interception/udevmon.d/caps2esc.conf.yaml.bak
fi

# Restart udevmon
echo "Restarting udevmon..."
sudo systemctl restart udevmon

echo ""
echo "Viland installed successfully!"
echo ""
echo "Controls:"
echo "  Double-tap CapsLock → Toggle Normal/Insert mode"
echo "  Double-tap ESC     → Enable/Disable viland"
echo ""
echo "Normal mode keys:"
echo "  h/j/k/l   → Arrow keys"
echo "  w/b/e     → Word forward/back/end"
echo "  0/$       → Line start/end"
echo "  i/a       → Exit to Insert mode"
echo ""
echo "To uninstall:"
echo "  sudo rm /etc/interception/udevmon.d/viland.yaml"
echo "  sudo mv /etc/interception/udevmon.d/caps2esc.conf.yaml.bak /etc/interception/udevmon.d/caps2esc.conf.yaml"
echo "  sudo systemctl restart udevmon"