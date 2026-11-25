#!/usr/bin/env bash
# ============================================================================
#  Install StepCast on Linux (e.g. Ubuntu) or macOS
#  On these systems StepCast opens, edits and updates lessons.
#  Recording new lessons needs Windows.  Finished lessons play everywhere.
#
#  Run it:  right-click this file -> "Run as a Program"
#           or in a terminal:  bash install-linux-mac.sh
#
#  StepCast 1.3 - Dr Sivakumar Manickam <skumar@staff.odc.edu.om>, Oman Dental College
#  Developed with the help of Claude (Anthropic) as an AI coding assistant.
# ============================================================================
set -e
cd "$(dirname "$0")"
HOME_DIR="$(pwd)"
echo
echo "  StepCast - installation (Linux / macOS)"
echo

say_fix() { echo; echo "  !! $1"; echo; read -r -p "  Press Enter to close..." _; exit 1; }

# 1. Python 3.10+ with Tk
if ! command -v python3 >/dev/null; then
  if [ "$(uname)" = "Darwin" ]; then say_fix "Python 3 is missing. Install it from https://www.python.org/downloads/ and run this again."
  else say_fix "Python 3 is missing. Install it with:  sudo apt install python3 python3-venv python3-tk"; fi
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || say_fix "StepCast needs Python 3.10 or newer."
if ! python3 -c 'import tkinter' 2>/dev/null; then
  if [ "$(uname)" = "Darwin" ]; then say_fix "Tk is missing. Install it with:  brew install python-tk   (or use Python from python.org)"
  else
    echo "[1/4] Installing Tk for Python (your password may be asked)..."
    sudo apt-get install -y python3-tk python3-venv || say_fix "Please run:  sudo apt install python3-tk python3-venv"
  fi
fi
echo "[1/4] Python OK"

# 2. libraries in a private environment
echo "[2/4] Installing StepCast's libraries..."
python3 -m venv app/.venv 2>/dev/null || { sudo apt-get install -y python3-venv && python3 -m venv app/.venv; } \
  || say_fix "Please run:  sudo apt install python3-venv   and try again."
app/.venv/bin/python -m pip install --quiet --disable-pip-version-check --upgrade pip
app/.venv/bin/python -m pip install --quiet --disable-pip-version-check -r app/requirements.txt \
  || say_fix "The libraries could not be installed. Check your internet connection and try again."

# 3. ffmpeg
echo "[3/4] Checking for ffmpeg..."
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  if [ "$(uname)" = "Darwin" ]; then
    command -v brew >/dev/null && brew install ffmpeg || say_fix "Install ffmpeg with Homebrew:  brew install ffmpeg"
  else
    echo "      Installing ffmpeg (your password may be asked)..."
    sudo apt-get install -y ffmpeg || say_fix "Please run:  sudo apt install ffmpeg"
  fi
fi

# 4. menu entry (Linux)
echo "[4/4] Adding StepCast to your applications menu..."
chmod +x "start-linux-mac.sh" 2>/dev/null || true
if [ "$(uname)" != "Darwin" ]; then
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/stepcast.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=StepCast
Comment=Interactive step-by-step screen lessons
Exec="$HOME_DIR/app/.venv/bin/python" "$HOME_DIR/app/record.py"
Path=$HOME_DIR
Icon=$HOME_DIR/app/logo.png
Terminal=false
Categories=Education;
DESKTOP
fi
echo
echo "  StepCast is ready. Start it from your applications menu,"
echo "  or run  start-linux-mac.sh  in this folder."
echo
read -r -p "  Start StepCast now? [Y/n] " a
case "$a" in n|N) ;; *) nohup app/.venv/bin/python app/record.py >/dev/null 2>&1 & ;; esac
