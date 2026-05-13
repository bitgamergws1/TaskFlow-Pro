#!/usr/bin/env bash
# run.sh — TaskFlow Pro one-command setup & launch

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   TaskFlow Pro — DevNest Setup       ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 not found. Install from https://python.org${NC}"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJ=$(python3 -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_VER" -lt 9 ]; }; then
    echo -e "${RED}❌ Python 3.9+ required. You have 3.${PY_VER}.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 3.${PY_VER} found${NC}"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo -e "${CYAN}🔧 Creating virtual environment...${NC}"
    python3 -m venv venv
fi
source venv/bin/activate

# ── Install dependencies ──────────────────────────────────────────────────────
echo -e "${CYAN}📦 Installing dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo -e "${GREEN}✅ Dependencies installed${NC}"

# ── tzdata check (required on Linux/macOS without system tz data) ─────────────
echo -e "${CYAN}🕐 Checking timezone data...${NC}"
if ! python3 -c "from zoneinfo import ZoneInfo; ZoneInfo('UTC')" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  tzdata missing — installing...${NC}"
    pip install --quiet tzdata
    echo -e "${GREEN}✅ tzdata installed${NC}"
else
    echo -e "${GREEN}✅ Timezone data OK${NC}"
fi

echo ""
echo -e "${GREEN}🚀 Launching TaskFlow Pro...${NC}"
echo ""
python3 main.py "$@"
