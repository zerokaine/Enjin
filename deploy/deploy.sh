#!/usr/bin/env bash
# =============================================================================
# Enjin OSINT Platform - Deployment Script
# Handles both first-time deployment and updates.
#
# Usage:
#   First deploy (run ON the server in /opt/enjin):
#     bash deploy/deploy.sh --domain enjin.example.com --email admin@example.com
#
#   Update deploy (run ON the server in /opt/enjin):
#     bash deploy/deploy.sh --update
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly COMPOSE_FILE="${PROJECT_DIR}/docker-compose.prod.yml"
readonly NGINX_DIR="${PROJECT_DIR}/deploy/nginx"
readonly SCHEMA_DIR="${PROJECT_DIR}/data/schema"
readonly COMPOSE_CMD="docker compose -f ${COMPOSE_FILE}"

# -----------------------------------------------------------------------------
# Default values
# -----------------------------------------------------------------------------
DOMAIN=""
EMAIL=""
ENV_FILE="${PROJECT_DIR}/.env.prod"
UPDATE_ONLY=false
SKIP_CERTBOT=false

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

die() { log_error "$@"; exit 1; }

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --domain)
                DOMAIN="$2"
                shift 2
                ;;
            --email)
                EMAIL="$2"
                shift 2
                ;;
            --env-file)
                ENV_FILE="$2"
                shift 2
                ;;
            --update)
                UPDATE_ONLY=true
                shift
                ;;
            --skip-certbot)
                SKIP_CERTBOT=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                die "Unknown argument: $1. Use --help for usage."
                ;;
        esac
    done
}

usage() {
    cat <<'EOF'
Usage: deploy.sh [OPTIONS]

Options:
  --domain DOMAIN       Domain name for the deployment (required for first deploy)
  --email EMAIL         Email for Let's Encrypt notifications (required for first deploy)
  --env-file FILE       Path to production env file (default: .env.prod)
  --update              Perform update deployment only (skip SSL setup)
  --skip-certbot        Skip certbot certificate generation
  -h, --help            Show this help message

Examples:
  First deploy:
    bash deploy/deploy.sh --domain enjin.example.com --email admin@example.com

  Update:
    bash deploy/deploy.sh --update
EOF
}

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
validate_args() {
    if [[ "${UPDATE_ONLY}" == "false" ]]; then
        [[ -z "${DOMAIN}" ]] && die "--domain is required for first deployment."
        [[ -z "${EMAIL}" ]] && die "--email is required for first deployment."
    fi

    if [[ ! -f "${ENV_FILE}" ]]; then
        die "Environment file not found: ${ENV_FILE}. Copy .env.prod.example to .env.prod and fill in values."
    fi

    if ! command -v docker &>/dev/null; then
        die "Docker is not installed. Run deploy/setup.sh first."
    fi

    if ! docker compose version &>/dev/null; then
        die "Docker Compose plugin is not installed. Run deploy/setup.sh first."
    fi
}

# -----------------------------------------------------------------------------
# Substitute domain placeholder in nginx configs
# -----------------------------------------------------------------------------
configure_nginx_domain() {
    log_info "Configuring nginx for domain: ${DOMAIN}"

    # Replace the ENJIN_DOMAIN placeholder in both config files
    for conf_file in "${NGINX_DIR}/default.conf" "${NGINX_DIR}/default.nossl.conf"; do
        if [[ -f "${conf_file}" ]]; then
            sed -i "s/ENJIN_DOMAIN/${DOMAIN}/g" "${conf_file}"
            log_info "Updated domain in ${conf_file}"
        fi
    done
}

# -----------------------------------------------------------------------------
# Start services with HTTP-only nginx config (pre-SSL)
# -----------------------------------------------------------------------------
start_http_only() {
    log_info "Starting services with HTTP-only nginx config..."

    # Use the no-SSL config for initial startup
    cp "${NGINX_DIR}/default.nossl.conf" "${NGINX_DIR}/default.conf.bak"
    cp "${NGINX_DIR}/default.nossl.conf" "${NGINX_DIR}/default.conf.active"

    # Temporarily replace default.conf with nossl version for the build
    local original_conf="${NGINX_DIR}/default.conf"
    local ssl_conf_backup="${NGINX_DIR}/default.conf.ssl"

    # Back up the SSL config
    cp "${original_conf}" "${ssl_conf_backup}"

    # Use nossl config as default.conf for building
    cp "${NGINX_DIR}/default.nossl.conf" "${original_conf}"

    # Build and start
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" build
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" up -d

    log_info "Services started with HTTP-only configuration."

    # Wait for services to be ready
    log_info "Waiting for services to stabilize..."
    sleep 15
}

# -----------------------------------------------------------------------------
# Obtain SSL certificate via certbot
# -----------------------------------------------------------------------------
obtain_ssl_certificate() {
    if [[ "${SKIP_CERTBOT}" == "true" ]]; then
        log_warn "Skipping certbot (--skip-certbot flag set)."
        return
    fi

    if [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
        log_info "SSL certificate already exists for ${DOMAIN}. Skipping certbot."
        return
    fi

    if ! command -v certbot &>/dev/null; then
        die "Certbot is not installed. Run deploy/setup.sh first."
    fi

    log_info "Obtaining SSL certificate for ${DOMAIN}..."

    # Get the certbot webroot path from the running container
    certbot certonly \
        --webroot \
        --webroot-path /var/lib/docker/volumes/enjin_certbot_webroot/_data \
        --domain "${DOMAIN}" \
        --email "${EMAIL}" \
        --agree-tos \
        --no-eff-email \
        --non-interactive

    log_info "SSL certificate obtained successfully."
}

# -----------------------------------------------------------------------------
# Switch to SSL nginx config
# -----------------------------------------------------------------------------
switch_to_ssl() {
    log_info "Switching nginx to SSL configuration..."

    local ssl_conf="${NGINX_DIR}/default.conf.ssl"
    local active_conf="${NGINX_DIR}/default.conf"

    if [[ -f "${ssl_conf}" ]]; then
        cp "${ssl_conf}" "${active_conf}"
    fi

    # Rebuild and restart nginx with SSL config
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" build nginx
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" up -d nginx

    log_info "Nginx restarted with SSL configuration."
}

# -----------------------------------------------------------------------------
# Setup certbot auto-renewal cron
# -----------------------------------------------------------------------------
setup_certbot_renewal() {
    log_info "Setting up certbot auto-renewal..."

    local cron_cmd="0 3 * * * certbot renew --quiet --deploy-hook 'docker compose -f ${COMPOSE_FILE} exec nginx nginx -s reload'"

    # Add cron job if it does not already exist
    if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
        (crontab -l 2>/dev/null; echo "${cron_cmd}") | crontab -
        log_info "Certbot renewal cron job added."
    else
        log_info "Certbot renewal cron job already exists."
    fi
}

# -----------------------------------------------------------------------------
# Apply database schemas
# -----------------------------------------------------------------------------
apply_schemas() {
    log_info "Applying database schemas..."

    # Wait for Neo4j to be fully ready
    log_info "Waiting for Neo4j to be ready..."
    local retries=30
    while [[ ${retries} -gt 0 ]]; do
        if ${COMPOSE_CMD} --env-file "${ENV_FILE}" exec -T neo4j cypher-shell -u neo4j -p "$(grep NEO4J_PASSWORD "${ENV_FILE}" | cut -d= -f2)" "RETURN 1" &>/dev/null; then
            break
        fi
        retries=$((retries - 1))
        sleep 2
    done

    if [[ ${retries} -eq 0 ]]; then
        log_warn "Neo4j did not become ready in time. Skipping schema application."
        return 1
    fi

    # Apply Neo4j constraints
    if [[ -f "${SCHEMA_DIR}/neo4j_constraints.cypher" ]]; then
        log_info "Applying Neo4j constraints..."
        local neo4j_pass
        neo4j_pass="$(grep NEO4J_PASSWORD "${ENV_FILE}" | cut -d= -f2)"

        # Filter out comment lines before piping to cypher-shell
        grep -v '^//' "${SCHEMA_DIR}/neo4j_constraints.cypher" \
            | grep -v '^$' \
            | ${COMPOSE_CMD} --env-file "${ENV_FILE}" exec -T neo4j cypher-shell \
                -u neo4j \
                -p "${neo4j_pass}" \
                --format plain

        log_info "Neo4j constraints applied."
    else
        log_warn "Neo4j constraints file not found: ${SCHEMA_DIR}/neo4j_constraints.cypher"
    fi

    # PostgreSQL init is automatic via docker-entrypoint-initdb.d mount
    log_info "PostgreSQL schema is applied automatically on first start via init script."
}

# -----------------------------------------------------------------------------
# Seed initial sources (first deploy only)
# -----------------------------------------------------------------------------
seed_sources() {
    log_info "Checking if sources need seeding..."

    local pg_pass
    pg_pass="$(grep POSTGRES_PASSWORD "${ENV_FILE}" | cut -d= -f2)"

    local count
    count=$(${COMPOSE_CMD} --env-file "${ENV_FILE}" exec -T postgres \
        psql -U enjin -d enjin -t -c "SELECT count(*) FROM sources;" 2>/dev/null | tr -d ' ' || echo "0")

    if [[ "${count}" -eq 0 || "${count}" == "" ]]; then
        log_info "Seeding default ingestion sources..."
        ${COMPOSE_CMD} --env-file "${ENV_FILE}" exec -T postgres \
            psql -U enjin -d enjin <<'SQL'
INSERT INTO sources (adapter, name, url, config, schedule_cron, active)
VALUES
    ('gdelt', 'GDELT Global Events', 'http://data.gdeltproject.org/api/v2', '{}', '*/30 * * * *', true),
    ('rss', 'Reuters World News', 'http://feeds.reuters.com/Reuters/worldNews', '{}', '*/15 * * * *', true),
    ('rss', 'AP News Top Headlines', 'https://rsshub.app/apnews/topics/apf-topnews', '{}', '*/15 * * * *', true)
ON CONFLICT DO NOTHING;
SQL
        log_info "Default sources seeded."
    else
        log_info "Sources table already has ${count} entries. Skipping seed."
    fi
}

# -----------------------------------------------------------------------------
# Update deployment (pull latest, rebuild, restart)
# -----------------------------------------------------------------------------
update_deploy() {
    log_info "Starting update deployment..."

    # Rebuild images
    log_info "Building updated images..."
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" build

    # Rolling restart
    log_info "Restarting services..."
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" up -d

    log_info "Update deployment complete."
}

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------
health_check() {
    log_info "Running health checks..."

    sleep 10

    local url="http://localhost:80/api/health"
    local retries=12
    local status=""

    while [[ ${retries} -gt 0 ]]; do
        status=$(curl -s -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null || echo "000")
        if [[ "${status}" == "200" ]]; then
            log_info "Health check passed (HTTP ${status})."
            return 0
        fi
        log_info "Health check returned HTTP ${status}, retrying... (${retries} attempts left)"
        retries=$((retries - 1))
        sleep 5
    done

    log_warn "Health check failed after all retries. Check service logs."
    return 1
}

# -----------------------------------------------------------------------------
# Show final status
# -----------------------------------------------------------------------------
show_status() {
    echo ""
    echo "============================================================================="
    echo " Deployment Status"
    echo "============================================================================="
    ${COMPOSE_CMD} --env-file "${ENV_FILE}" ps
    echo ""

    if [[ -n "${DOMAIN}" ]]; then
        echo " Application URL: https://${DOMAIN}"
        echo " API Health:      https://${DOMAIN}/api/health"
    fi
    echo "============================================================================="
}

# -----------------------------------------------------------------------------
# First deploy
# -----------------------------------------------------------------------------
first_deploy() {
    log_info "Starting first-time deployment for ${DOMAIN}..."

    configure_nginx_domain
    start_http_only
    obtain_ssl_certificate
    switch_to_ssl
    setup_certbot_renewal
    apply_schemas
    seed_sources
    health_check || true
    show_status

    log_info "First-time deployment complete!"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    cd "${PROJECT_DIR}"

    parse_args "$@"
    validate_args

    if [[ "${UPDATE_ONLY}" == "true" ]]; then
        update_deploy
        health_check || true
        show_status
    else
        first_deploy
    fi
}

main "$@"
