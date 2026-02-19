#!/bin/bash
set -e

echo "Starting Swarmbot dependency installation..."

# 1. Setup independent environment directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.deps"
mkdir -p "$INSTALL_DIR"
export PATH="$INSTALL_DIR/bin:$PATH"

echo "Installation directory: $INSTALL_DIR"

# 2. Check Node.js and npm
if ! command -v npm &> /dev/null; then
    echo "Error: npm is not installed. Please install Node.js and npm first."
    exit 1
fi

# 3. Install QMD locally
echo "Installing QMD..."
# We use npm prefix to install in .deps
npm config set prefix "$INSTALL_DIR"
npm install -g @tobilu/qmd

# Verify QMD
if command -v qmd &> /dev/null; then
    echo "QMD installed successfully: $(qmd --version)"
else
    echo "Warning: qmd command not found in PATH. You may need to add $INSTALL_DIR/bin to your PATH."
fi

# 4. Install Python dependencies
echo "Installing Python dependencies..."
# Assuming we are in a virtualenv or user wants to install in current python env
pip install -e .

echo "Installation complete!"
echo "To use qmd, add the following to your shell config:"
echo "export PATH=\"$INSTALL_DIR/bin:\$PATH\""
