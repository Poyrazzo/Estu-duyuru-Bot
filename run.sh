#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Sanal ortam bulunamadı. Önce './setup.sh' komutunu çalıştırın."
    exit 1
fi

cd "$SCRIPT_DIR"
exec "$VENV_PYTHON" bot.py "$@"
