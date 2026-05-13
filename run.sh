#!/usr/bin/env bash
# run.sh — TaskFlow Pro one-command setup & launcher
# Works on Linux, macOS, and Termux

set -e

# ── Colors ────────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║      TaskFlow Pro — DevNest          ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── Detect project directory ──────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Detect OS ─────────────────────────────────────────────────────────────────
OS="$(uname)"

if [[ "$PREFIX" == *"com.termux"* ]]; then
    PLATFORM="termux"
elif [[ "$OS" == "Darwin" ]]; then
    PLATFORM="macos"
else
    PLATFORM="linux"
fi

echo -e "${GREEN}✅ Platform detected: ${PLATFORM}${NC}"

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 not found.${NC}"

    if [[ "$PLATFORM" == "macos" ]]; then
        echo -e "${YELLOW}Install using: brew install python${NC}"
    elif [[ "$PLATFORM" == "termux" ]]; then
        echo -e "${YELLOW}Install using: pkg install python${NC}"
    else
        echo -e "${YELLOW}Install using your package manager.${NC}"
    fi

    exit 1
fi

PY_VER=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJ=$(python3 -c "import sys; print(sys.version_info.major)")

if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_VER" -lt 9 ]; }; then
    echo -e "${RED}❌ Python 3.9+ required.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python detected${NC}"

# ── Create virtual environment ────────────────────────────────────────────────
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo -e "${CYAN}🔧 Creating virtual environment...${NC}"
    python3 -m venv "$PROJECT_DIR/venv"
fi

# ── Activate virtual environment ──────────────────────────────────────────────
source "$PROJECT_DIR/venv/bin/activate"

# ── Upgrade pip ───────────────────────────────────────────────────────────────
echo -e "${CYAN}⬆️ Upgrading pip...${NC}"
python -m pip install --upgrade pip

# ── Install dependencies ──────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo -e "${CYAN}📦 Installing dependencies...${NC}"
    pip install -r "$PROJECT_DIR/requirements.txt"
    echo -e "${GREEN}✅ Dependencies installed${NC}"
fi

# ── Install tzdata if needed ──────────────────────────────────────────────────
echo -e "${CYAN}🕐 Checking timezone data...${NC}"

if ! python3 -c "from zoneinfo import ZoneInfo; ZoneInfo('UTC')" 2>/dev/null; then
    echo -e "${YELLOW}⚠️ tzdata missing — installing...${NC}"
    pip install tzdata
fi

echo -e "${GREEN}✅ Timezone data OK${NC}"

# ── Create global command ─────────────────────────────────────────────────────
echo -e "${CYAN}🔗 Creating global command...${NC}"

TASKFLOW_CMD='#!/usr/bin/env bash
source "'"$PROJECT_DIR"'/venv/bin/activate"
python "'"$PROJECT_DIR"'/main.py" "$@"'

if [[ "$PLATFORM" == "termux" ]]; then
    echo "$TASKFLOW_CMD" > "$PREFIX/bin/taskflow"
    chmod +x "$PREFIX/bin/taskflow"

elif [[ "$PLATFORM" == "macos" || "$PLATFORM" == "linux" ]]; then
    mkdir -p "$HOME/.local/bin"

    echo "$TASKFLOW_CMD" > "$HOME/.local/bin/taskflow"
    chmod +x "$HOME/.local/bin/taskflow"

    # Add PATH automatically if missing
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        SHELL_RC="$HOME/.bashrc"

        if [[ "$SHELL" == *"zsh"* ]]; then
            SHELL_RC="$HOME/.zshrc"
        fi

        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"

        echo -e "${YELLOW}⚠️ Restart terminal or run:${NC}"
        echo "source $SHELL_RC"
    fi
fi

echo -e "${GREEN}✅ Global command installed${NC}"

# ── Launch app ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🚀 Launching TaskFlow Pro...${NC}"
echo ""

python "$PROJECT_DIR/main.py" "$@"
