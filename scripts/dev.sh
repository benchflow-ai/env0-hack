#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL="$ROOT/scripts/mockflow_control.py"

usage() {
  cat <<'EOF'
Usage:
  dev.sh
  dev.sh task <name>

Internal control contract:
  scripts/mockflow_control.py --dry-run start-default [--devhub]
  scripts/mockflow_control.py --dry-run start-task [--devhub] <name>
  scripts/mockflow_control.py seed-default [service...]
  scripts/mockflow_control.py seed-task <name> [service...]
  scripts/mockflow_control.py reset [service...]
  scripts/mockflow_control.py snapshot <name> [service...]
  scripts/mockflow_control.py restore <name> [service...]
EOF
}

if [[ $# -eq 0 ]]; then
  exec python3 "$CONTROL" start-default --devhub
fi

case "${1:-}" in
  task)
    if [[ $# -ne 2 ]]; then
      usage >&2
      exit 2
    fi
    exec python3 "$CONTROL" start-task --devhub "$2"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
