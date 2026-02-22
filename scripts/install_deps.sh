#!/bin/bash
set -e

echo "Starting Swarmbot dependency installation..."

# 0. Detect OS and Python command
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "Error: Python 3 is not installed."
        exit 1
    fi
fi

# 1. Setup independent environment directory (Virtual Environment)
# We will create a venv inside the project to isolate dependencies and avoid PEP 668 issues.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "Installation directory: $PROJECT_ROOT"
echo "Creating Virtual Environment at: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

# Activate venv for subsequent commands
source "$VENV_DIR/bin/activate"

# Upgrade pip inside venv
pip install --upgrade pip

# 2. Check Node.js and npm (Optional)
if command -v npm &> /dev/null; then
    echo "Node.js detected."
    echo "Node.js is optional. Swarmbot does not require npm for installation."
else
    echo "npm is not installed (optional)."
fi

# 3. Install Python dependencies inside venv
echo "Installing Python dependencies inside virtual environment..."
pip install -e .

# 4. Create a convenience wrapper script 'swarmbot_run' in the root
WRAPPER_SCRIPT="$PROJECT_ROOT/swarmbot_run"
cat > "$WRAPPER_SCRIPT" <<EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec swarmbot "\$@"
EOF
chmod +x "$WRAPPER_SCRIPT"

# 5. Try to link to system bin for global access
if [ -w "/usr/local/bin" ]; then
    echo "Creating global link: /usr/local/bin/swarmbot -> $WRAPPER_SCRIPT"
    rm -f /usr/local/bin/swarmbot
    ln -s "$WRAPPER_SCRIPT" /usr/local/bin/swarmbot
elif [ -d "$HOME/.local/bin" ]; then
     echo "Creating user link: $HOME/.local/bin/swarmbot -> $WRAPPER_SCRIPT"
     rm -f "$HOME/.local/bin/swarmbot"
     ln -s "$WRAPPER_SCRIPT" "$HOME/.local/bin/swarmbot"
     # Check PATH
     if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo "Warning: $HOME/.local/bin is not in your PATH."
     fi
else
     echo "Could not create global link. You can use ./swarmbot_run or add alias."
fi

echo "Installation complete!"
echo ""
if command -v swarmbot &> /dev/null; then
    echo "You can now run 'swarmbot' command directly!"
else
    echo "To run Swarmbot, use:"
    echo "  ./swarmbot_run <command>"
fi
