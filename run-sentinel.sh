#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ -x "$HOME/.local/share/artin-sentinel/runtime/bin/artin-sentinel" ]]; then
  exec "$HOME/.local/share/artin-sentinel/runtime/bin/artin-sentinel" "$@"
fi

if python3 -c 'import PySide6' >/dev/null 2>&1; then
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  exec python3 -m artin_sentinel.app "$@"
fi

echo "PySide6 não encontrado. Execute ./install.sh primeiro." >&2
exit 1
