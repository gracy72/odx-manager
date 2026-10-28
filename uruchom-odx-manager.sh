#!/usr/bin/env bash
# ODX Manager - GUI na Linuksie (silnik: docker run webodm/odx).
# Wymaga: python3 z tkinterem (sudo apt install python3-tk) oraz docker.
set -euo pipefail
cd "$(dirname "$0")"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "[BLAD] Brak python3. Zainstaluj: sudo apt install python3 python3-tk"
  exit 1
fi
exec "$PY" gui/odx_gui.py "$@"