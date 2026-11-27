#!/usr/bin/env bash
# SDLC AI Toolkit - one-line installer for macOS / Linux / WSL.
#   curl -fsSL https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.sh | bash
#   ... | bash -s -- --target all --workspace ~/work
# Extra arguments are passed to install.py (--target, --workspace, --set k=v, --uninstall ...).
set -euo pipefail

REPO_URL="${SDLC_REPO_URL:-https://github.com/sarivoli/sdlc-ai-toolkit.git}"
DEST="${SDLC_HOME:-$HOME/.sdlc-ai-toolkit}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' is required but not installed." >&2; exit 1; }; }
need git

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "ERROR: Python 3.8+ is required." >&2; exit 1; }

if [ -d "$DEST/.git" ]; then
  echo "Updating $DEST ..."
  git -C "$DEST" pull --ff-only
else
  echo "Cloning $REPO_URL -> $DEST ..."
  git clone --depth 1 "$REPO_URL" "$DEST"
fi

exec "$PY" "$DEST/install.py" "$@"
