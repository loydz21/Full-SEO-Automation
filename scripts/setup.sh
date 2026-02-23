#!/usr/bin/env bash
# =============================================================================
# Full SEO Automation — Setup Script
# =============================================================================
# Usage: chmod +x scripts/setup.sh && ./scripts/setup.sh
# =============================================================================
set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- Helpers ---
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[  OK]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[FAIL]${NC}  $1"; }
step()    { echo -e "\n${BOLD}${CYAN}── Step $1: $2${NC}"; }

echo -e "\n${BOLD}${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║     🚀  Full SEO Automation — Setup             ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════╝${NC}\n"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
info "Project directory: $PROJECT_DIR"

# ── Step 1: Check Python version ─────────────────────────────────────────────
step 1 "Checking Python version"

if ! command -v python3 &>/dev/null; then
    error "Python 3 is not installed. Please install Python 3.10+ first."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    error "Python 3.10+ required. Found: Python $PY_VERSION"
    exit 1
fi
success "Python $PY_VERSION detected"

# ── Step 2: Create virtual environment ───────────────────────────────────────
step 2 "Setting up virtual environment"

if [ -d "venv" ]; then
    warn "Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    success "Virtual environment created: venv/"
fi

# Activate
# shellcheck disable=SC1091
source venv/bin/activate
success "Virtual environment activated"

# ── Step 3: Install dependencies ─────────────────────────────────────────────
step 3 "Installing Python dependencies"

pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
success "All packages installed from requirements.txt"

# Install Playwright browsers
info "Installing Playwright Chromium browser..."
python -m playwright install chromium --quiet 2>/dev/null || playwright install chromium
success "Playwright Chromium installed"

# ── Step 4: Create data directories ──────────────────────────────────────────
step 4 "Creating data directories"

for dir in data data/cache data/exports data/templates config docs scripts; do
    mkdir -p "$dir"
done
success "Directories created: data/{cache,exports,templates}, config/, docs/, scripts/"

# ── Step 5: Configure environment ────────────────────────────────────────────
step 5 "Configuring environment"

if [ -f ".env" ]; then
    warn ".env file already exists. Skipping copy."
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        success "Copied .env.example → .env"
        warn "Edit .env to add your API keys: nano .env"
    else
        error ".env.example not found. Create .env manually."
    fi
fi

# ── Step 6: Initialize database ──────────────────────────────────────────────
step 6 "Initializing database"

python3 -c "
from src.database import init_database
import asyncio
asyncio.run(init_database())
print('Database initialized successfully')
" 2>/dev/null && success "SQLite database initialized" || warn "Database init skipped (run 'seo setup' to initialize later)"

# ── Step 7: Validate Python files ────────────────────────────────────────────
step 7 "Validating Python source files"

ERROR_COUNT=0
FILE_COUNT=0
while IFS= read -r -d '' pyfile; do
    FILE_COUNT=$((FILE_COUNT + 1))
    if ! python3 -c "import ast; ast.parse(open('$pyfile').read())" 2>/dev/null; then
        error "Syntax error: $pyfile"
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
done < <(find src dashboard tests -name '*.py' -print0 2>/dev/null)

if [ "$ERROR_COUNT" -eq 0 ]; then
    success "All $FILE_COUNT Python files passed syntax validation"
else
    warn "$ERROR_COUNT of $FILE_COUNT files have syntax issues"
fi

# ── Complete ─────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║     ✅  Setup Complete!                           ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}\n"

echo -e "${BOLD}Next steps:${NC}"
echo -e "  1. ${CYAN}nano .env${NC}              — Add your API keys"
echo -e "  2. ${CYAN}source venv/bin/activate${NC}  — Activate environment"
echo -e "  3. ${CYAN}seo setup${NC}             — Run interactive setup wizard"
echo -e "  4. ${CYAN}seo status${NC}            — Verify configuration"
echo -e "  5. ${CYAN}seo dashboard${NC}         — Launch web dashboard"
echo -e "  6. ${CYAN}seo full --domain example.com${NC}  — Run full pipeline\n"

echo -e "${BOLD}Documentation:${NC}  ${CYAN}cat README.md${NC}"
echo -e "${BOLD}Run tests:${NC}      ${CYAN}python -m pytest tests/ -v${NC}\n"
