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

# 2. Check Node.js and npm (Optional but recommended for nanobot extensions)
if command -v npm &> /dev/null; then
    echo "Node.js detected."
    # We no longer install QMD via npm globally to avoid issues.
    # Swarmbot now includes an embedded python-based QMD implementation (SQLite).
    echo "Using Embedded QMD (SQLite) - No external QMD installation required."
else
    echo "Warning: npm is not installed. Some nanobot extensions might be limited."
fi

# 3. Install Python dependencies inside venv
echo "Installing Python dependencies inside virtual environment..."
pip install -e .

# 4. Create a convenience wrapper script 'swarmbot' in the root
WRAPPER_SCRIPT="$PROJECT_ROOT/swarmbot_run"
cat > "$WRAPPER_SCRIPT" <<EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec swarmbot "\$@"
EOF
chmod +x "$WRAPPER_SCRIPT"

echo "Installation complete!"
echo ""
echo "To run Swarmbot, use the wrapper script:"
echo "  ./swarmbot_run onboard"
echo "  ./swarmbot_run run"
echo ""
echo "Or activate the virtual environment manually:"
echo "  source .venv/bin/activate"
echo "  swarmbot onboard"
