#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# setup.sh — One-time setup for the gmaps-lead-finder system.
#
# Usage:
#   bash setup.sh          # full setup
#   bash setup.sh --no-venv  # skip virtual environment creation
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Colour

ok()   { echo -e "${GREEN}  ✓  $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠  $*${NC}"; }
err()  { echo -e "${RED}  ✗  $*${NC}"; }
step() { echo -e "\n${YELLOW}▶ $*${NC}"; }

USE_VENV=true
for arg in "$@"; do
    [[ "$arg" == "--no-venv" ]] && USE_VENV=false
done

echo ""
echo "════════════════════════════════════════════════"
echo "  gmaps-lead-finder  —  Setup"
echo "════════════════════════════════════════════════"
echo ""

# ── 1. Python version check ──────────────────────────────────
step "Checking Python version…"
if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install Python 3.10+ from https://python.org"
    exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10) ]]; then
    err "Python 3.10+ required (found $PY_VERSION)"
    exit 1
fi
ok "Python $PY_VERSION"

# ── 2. Virtual environment ───────────────────────────────────
if $USE_VENV; then
    step "Setting up virtual environment…"
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
        ok "Created .venv"
    else
        ok ".venv already exists"
    fi
    # Activate
    source .venv/bin/activate
    PYTHON=".venv/bin/python"
    PIP=".venv/bin/pip"
else
    PYTHON="$(command -v python3)"
    PIP="$(command -v pip3)"
    warn "Skipping venv — installing into system Python"
fi

# ── 3. Upgrade pip ───────────────────────────────────────────
step "Upgrading pip…"
"$PIP" install --upgrade pip --quiet
ok "pip up to date"

# ── 4. Install Python dependencies ───────────────────────────
step "Installing Python dependencies…"
"$PIP" install -r requirements.txt --quiet
ok "All packages installed"

# ── 5. Install Playwright browsers ───────────────────────────
step "Installing Playwright Chromium browser (~150 MB)…"
"$PYTHON" -m playwright install chromium
ok "Chromium installed"

# ── 6. Create required directories ───────────────────────────
step "Creating directory structure…"
mkdir -p output/logs
ok "output/ and output/logs/ ready"

# ── 7. .env setup ────────────────────────────────────────────
step "Checking credentials…"
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.template" ]]; then
        cp .env.template .env
        warn ".env created from template — EDIT IT NOW before running!"
        warn "  nano .env"
    else
        cat > .env << 'EOF'
GMAIL_EMAIL=zfkhan321@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
DELAY_BETWEEN_EMAILS=8
SCRAPERS_PARALLEL=10
EOF
        warn ".env created with placeholders — fill in GMAIL_APP_PASSWORD before running."
    fi
else
    ok ".env already exists"
fi

# ── 8. Validate .env ─────────────────────────────────────────
step "Validating .env…"
set -a; source .env; set +a

MISSING=()
[[ -z "${GMAIL_APP_PASSWORD:-}" ]] && MISSING+=("GMAIL_APP_PASSWORD")

if [[ ${#MISSING[@]} -gt 0 ]]; then
    warn "Missing in .env: ${MISSING[*]}"
    warn "Edit .env then re-run:  bash setup.sh"
else
    ok "Credentials present"
fi

# ── 9. Quick SMTP test ───────────────────────────────────────
step "Testing Gmail SMTP connection…"
GMAIL_USER="${GMAIL_EMAIL:-${GMAIL_USER:-zfkhan321@gmail.com}}"
APP_PW="${GMAIL_APP_PASSWORD:-}"

if [[ -n "$APP_PW" && "$APP_PW" != "xxxx xxxx xxxx xxxx" ]]; then
    SMTP_OK=$("$PYTHON" - <<PYEOF
import smtplib, sys
try:
    s = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
    s.ehlo(); s.starttls(); s.ehlo()
    s.login("$GMAIL_USER", "$APP_PW")
    s.quit()
    print("ok")
except Exception as e:
    print(f"fail: {e}")
PYEOF
)
    if [[ "$SMTP_OK" == "ok" ]]; then
        ok "Gmail SMTP connection successful"
    else
        err "Gmail SMTP test failed: $SMTP_OK"
        warn "Check your app password at: myaccount.google.com/security → App passwords"
    fi
else
    warn "Skipping SMTP test — GMAIL_APP_PASSWORD not set yet."
fi

# ── 10. Summary ──────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
echo "  Setup complete!"
echo "════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit .env and set GMAIL_APP_PASSWORD"
echo "     (myaccount.google.com/security → App passwords)"
echo ""
echo "  2. Run a dry-run to confirm everything works:"
echo "     python run_all.py --dry-run"
echo ""
echo "  3. Run for real:"
echo "     python run_all.py"
echo ""
echo "  4. Run on a 7-day loop:"
echo "     python run_all.py --loop"
echo ""
echo "  See README.md for full documentation."
echo ""
