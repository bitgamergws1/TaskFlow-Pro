#!/usr/bin/env bash
# run.sh — TaskFlow Pro one-command setup & launcher
# Works on Linux, macOS, and Termux

set -e

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

# Tips shown while dependencies install
TIPS=(
    "Break big tasks into 25-min Pomodoro blocks."
    "High priority tasks first — your brain is freshest in the morning."
    "Name tasks as actions: 'Write report' beats 'Report' every time."
    "A 3-day streak beats a perfect week you never started."
    "If it takes less than 2 minutes, do it now — don't add it to the list."
    "Set due dates even for flexible tasks — deadlines create focus."
    "Group similar tasks by category — context-switching kills momentum."
    "Complete your hardest task before lunch. Everything else feels easy after."
    "Pending tasks drain mental energy even when you are not working on them."
    "What gets measured gets done — check your analytics weekly."
    "Timeboxing beats to-do lists. Schedule the task, not just the intention."
    "Done is better than perfect. Ship, then refine."
    "One task at a time. Multitasking is just fast task-switching — and it costs you."
    "Your future self will thank you for the due date you set today."
    "Productivity is not about doing more — it is about doing what matters."
)

SPINNERS=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

# Show rotating tips while a background PID is running
_tips_spinner() {
    local pid=$1
    local label=$2
    local tip_idx=0
    local spin_idx=0
    local tick=0

    while kill -0 "$pid" 2>/dev/null; do
        local spin="${SPINNERS[$spin_idx]}"
        local tip="${TIPS[$tip_idx]}"
        printf "\r  ${CYAN}${spin}${NC}  ${DIM}%-10s${NC}  ${tip}%-20s" "$label" " "
        sleep 0.12
        spin_idx=$(( (spin_idx + 1) % ${#SPINNERS[@]} ))
        tick=$(( tick + 1 ))
        # Rotate tip every ~3 seconds (25 ticks * 0.12s = 3s)
        if (( tick % 25 == 0 )); then
            tip_idx=$(( (tip_idx + 1) % ${#TIPS[@]} ))
        fi
    done

    # Clear the tip line
    printf "\r%-80s\r" " "
}

# Run a command in background, show tips while it runs, then check exit code
_run_with_tips() {
    local label=$1
    shift
    "$@" > /tmp/taskflow_install.log 2>&1 &
    local pid=$!
    _tips_spinner "$pid" "$label"
    wait "$pid"
    local code=$?
    if [ $code -ne 0 ]; then
        echo -e "${RED}[ERROR] $label failed. Check /tmp/taskflow_install.log${NC}"
        cat /tmp/taskflow_install.log
        exit $code
    fi
    echo -e "${GREEN}[OK]${NC}    $label"
}

# Banner
echo ""
echo -e "${CYAN}${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║      TaskFlow Pro — DevNest          ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# Detect project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect platform
OS="$(uname)"
if [[ "$PREFIX" == *"com.termux"* ]]; then
    PLATFORM="termux"
elif [[ "$OS" == "Darwin" ]]; then
    PLATFORM="macos"
else
    PLATFORM="linux"
fi

echo -e "${GREEN}[OK]${NC}    Platform: ${PLATFORM}"

# Python check
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[ERROR] Python 3 not found.${NC}"
    case "$PLATFORM" in
        macos)   echo -e "${YELLOW}Install: brew install python${NC}" ;;
        termux)  echo -e "${YELLOW}Install: pkg install python${NC}" ;;
        *)       echo -e "${YELLOW}Install Python 3.9+ via your package manager.${NC}" ;;
    esac
    exit 1
fi

PY_MAJ=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MIN=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 9 ]; }; then
    echo -e "${RED}[ERROR] Python 3.9+ required (found ${PY_MAJ}.${PY_MIN}).${NC}"
    exit 1
fi

echo -e "${GREEN}[OK]${NC}    Python ${PY_MAJ}.${PY_MIN}"
echo ""
echo -e "${DIM}  Tips will show while we get things ready...${NC}"
echo ""

# Virtual environment
if [ ! -d "$PROJECT_DIR/venv" ]; then
    _run_with_tips "Creating virtualenv" python3 -m venv "$PROJECT_DIR/venv"
else
    echo -e "${GREEN}[OK]${NC}    Virtualenv exists — skipping"
fi

# Activate
source "$PROJECT_DIR/venv/bin/activate"

# Upgrade pip
_run_with_tips "Upgrading pip" python -m pip install --upgrade pip

# Install dependencies
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    _run_with_tips "Installing dependencies" pip install -r "$PROJECT_DIR/requirements.txt"
else
    echo -e "${YELLOW}[WARN]${NC}  requirements.txt not found — skipping"
fi

# Timezone data check
if ! python3 -c "from zoneinfo import ZoneInfo; ZoneInfo('UTC')" 2>/dev/null; then
    _run_with_tips "Installing tzdata" pip install tzdata
else
    echo -e "${GREEN}[OK]${NC}    Timezone data"
fi

# Global command
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

    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        SHELL_RC="$HOME/.bashrc"
        [[ "$SHELL" == *"zsh"* ]] && SHELL_RC="$HOME/.zshrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo -e "${YELLOW}[WARN]${NC}  Restart terminal or run: source $SHELL_RC"
    fi
fi

echo -e "${GREEN}[OK]${NC}    Global command installed"

# Launch
echo ""
echo -e "${GREEN}${BOLD}  All set. Launching TaskFlow Pro...${NC}"
echo ""

python "$PROJECT_DIR/main.py" "$@"
