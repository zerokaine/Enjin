#!/usr/bin/env bash
# =============================================================================
# Enjin OSINT Platform — Quick-start for local testing
#
# Spins up the full stack with a fast hot-reload frontend (no production build).
# Databases, API, and frontend are always started.
# The ingestion worker is opt-in via --with-ingestion.
#
# Usage:
#   ./quickstart.sh                  # API + frontend + databases
#   ./quickstart.sh --with-ingestion # Also start the ingestion worker
#   ./quickstart.sh --down           # Stop and remove all containers
#   ./quickstart.sh --logs           # Follow logs after starting
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[info]${RESET}  $*"; }
success() { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
die()     { echo -e "${RED}[error]${RESET} $*" >&2; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
WITH_INGESTION=false
FOLLOW_LOGS=false
BRING_DOWN=false

for arg in "$@"; do
  case "$arg" in
    --with-ingestion) WITH_INGESTION=true ;;
    --logs)           FOLLOW_LOGS=true ;;
    --down)           BRING_DOWN=true ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# \{0,2\}//' | tail -n +2
      exit 0 ;;
    *) die "Unknown argument: $arg. Run '$0 --help' for usage." ;;
  esac
done

# ── Resolve script directory (so it works from any cwd) ───────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Compose file lists ────────────────────────────────────────────────────────
BASE_FILES=(-f docker-compose.yml -f docker-compose.test.yml)
PROFILES=()
$WITH_INGESTION && PROFILES=(--profile ingestion)

DC=(docker compose "${BASE_FILES[@]}" "${PROFILES[@]}")

# ── --down shortcut ───────────────────────────────────────────────────────────
if $BRING_DOWN; then
  info "Stopping and removing all Enjin test containers..."
  "${DC[@]}" down --remove-orphans
  success "All containers stopped."
  exit 0
fi

# ── Preflight checks ──────────────────────────────────────────────────────────
echo -e "\n${BOLD}Enjin OSINT Platform — Quick-start${RESET}\n"

command -v docker &>/dev/null      || die "Docker is not installed. Get it at https://docs.docker.com/get-docker/"
docker info &>/dev/null            || die "Docker daemon is not running. Start it first."
docker compose version &>/dev/null || die "Docker Compose plugin not found. Update Docker Desktop or install the plugin."

success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
success "Docker Compose $(docker compose version --short)"

# ── Environment file ──────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    info "Created .env from .env.example (edit it if you need custom values)."
  else
    warn ".env not found and no .env.example to copy from — services may fail to start."
  fi
else
  info "Using existing .env"
fi

# ── Bring up the stack ────────────────────────────────────────────────────────
echo
info "Starting services (this may take a few minutes on first run while images build)..."
$WITH_INGESTION && info "  Mode: full stack (databases + API + frontend + ingestion)" \
                || info "  Mode: core stack (databases + API + frontend)"
echo

"${DC[@]}" up --build -d

# ── Wait for API health ───────────────────────────────────────────────────────
echo
info "Waiting for API to become healthy..."

MAX_WAIT=120  # seconds
ELAPSED=0
INTERVAL=5

until curl -sf http://localhost:8000/health >/dev/null 2>&1; do
  if (( ELAPSED >= MAX_WAIT )); then
    warn "API did not become healthy within ${MAX_WAIT}s."
    warn "Check logs with: docker compose ${BASE_FILES[*]} logs api"
    break
  fi
  printf "  waiting... %ds\r" "$ELAPSED"
  sleep "$INTERVAL"
  ELAPSED=$(( ELAPSED + INTERVAL ))
done

if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
  success "API is healthy"
fi

# ── Wait for frontend ─────────────────────────────────────────────────────────
info "Waiting for frontend dev server..."
ELAPSED=0

until curl -sf http://localhost:3000 >/dev/null 2>&1; do
  if (( ELAPSED >= MAX_WAIT )); then
    warn "Frontend did not respond within ${MAX_WAIT}s — it may still be compiling."
    break
  fi
  printf "  waiting... %ds\r" "$ELAPSED"
  sleep "$INTERVAL"
  ELAPSED=$(( ELAPSED + INTERVAL ))
done

if curl -sf http://localhost:3000 >/dev/null 2>&1; then
  success "Frontend is ready"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Enjin is running!${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo
echo -e "  ${BOLD}Frontend${RESET}     http://localhost:3000"
echo -e "  ${BOLD}API${RESET}          http://localhost:8000"
echo -e "  ${BOLD}API docs${RESET}     http://localhost:8000/docs"
echo -e "  ${BOLD}API health${RESET}   http://localhost:8000/health"
echo
echo -e "  ${BOLD}Neo4j browser${RESET}   http://localhost:7474  (neo4j / enjin_dev)"
echo -e "  ${BOLD}Meilisearch${RESET}     http://localhost:7700  (key: enjin_dev_key)"
echo -e "  ${BOLD}PostgreSQL${RESET}      localhost:5432         (enjin / enjin_dev)"
echo -e "  ${BOLD}Redis${RESET}           localhost:6379"
echo
echo -e "  ${BOLD}Useful commands:${RESET}"
echo -e "    Follow all logs:     docker compose ${BASE_FILES[*]} logs -f"
echo -e "    Follow API logs:     docker compose ${BASE_FILES[*]} logs -f api"
echo -e "    Stop everything:     $0 --down"
echo -e "    Rebuild after code changes: $0 (re-run this script)"
echo
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

$FOLLOW_LOGS && { echo; info "Following logs (Ctrl+C to stop)..."; "${DC[@]}" logs -f; }
