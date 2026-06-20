#!/usr/bin/env bash
# Seed + serve the four env-0 mock services on their config.toml ports so the
# Env0Mobile app (or Env0Kit integration tests) can talk to a real local world.
#
#   ./run_local_services.sh start    # seed (once) + serve all four in background
#   ./run_local_services.sh stop     # stop everything
#   ./run_local_services.sh health   # curl each /health
#
# Ports: gmail 9001, gcal 9003, gdoc 9004, gdrive 9005 (from repo config.toml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENVS_DIR="$REPO_ROOT/packages/environments"
DATA_DIR="${ENV0_DATA_DIR:-/tmp/env0-mobile-data}"
PID_FILE="$DATA_DIR/pids"
SCENARIO="${ENV0_SCENARIO:-default}"

# service:port pairs
SERVICES=("gmail:9001" "gcal:9003" "gdoc:9004" "gdrive:9005")

start() {
  mkdir -p "$DATA_DIR"
  : > "$PID_FILE"
  for entry in "${SERVICES[@]}"; do
    svc="${entry%%:*}"; port="${entry##*:}"
    db="$DATA_DIR/$svc.db"
    if [[ ! -f "$db" ]]; then
      echo "seeding $svc ($SCENARIO) -> $db"
      ( cd "$ENVS_DIR/$svc" && uv run "$svc" --db "$db" seed --scenario "$SCENARIO" >/dev/null 2>&1 ) \
        || echo "  (seed failed for $svc; serving empty db)"
    fi
    echo "serving $svc on 127.0.0.1:$port"
    ( cd "$ENVS_DIR/$svc" && uv run "$svc" --db "$db" serve --host 127.0.0.1 --port "$port" --no-mcp \
        >"$DATA_DIR/$svc.log" 2>&1 ) &
    echo "$!" >> "$PID_FILE"
  done
  echo "waiting for /health ..."
  for entry in "${SERVICES[@]}"; do
    svc="${entry%%:*}"; port="${entry##*:}"
    for _ in $(seq 1 40); do
      if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        echo "  $svc ready"; break
      fi
      sleep 0.5
    done
  done
  echo "all started. logs in $DATA_DIR/*.log"
}

stop() {
  [[ -f "$PID_FILE" ]] || { echo "no pid file"; return 0; }
  while read -r pid; do [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true; done < "$PID_FILE"
  rm -f "$PID_FILE"
  echo "stopped."
}

health() {
  for entry in "${SERVICES[@]}"; do
    svc="${entry%%:*}"; port="${entry##*:}"
    printf '%-8s ' "$svc"
    curl -fsS "http://127.0.0.1:$port/health" 2>/dev/null || echo "DOWN"
    echo
  done
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  health) health ;;
  *) echo "usage: $0 {start|stop|health}"; exit 1 ;;
esac
