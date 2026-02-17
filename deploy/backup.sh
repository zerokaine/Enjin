#!/usr/bin/env bash
# =============================================================================
# Enjin OSINT Platform - Backup Script
# Designed to run via cron. Creates timestamped backups of all data stores.
#
# Usage:
#   Manual:  bash deploy/backup.sh
#   Cron:    0 2 * * * /opt/enjin/deploy/backup.sh >> /var/log/enjin-backup.log 2>&1
#
# Environment variables (optional):
#   BACKUP_DIR      Override backup directory (default: /opt/enjin/backups)
#   BACKUP_RETAIN   Number of daily backups to keep (default: 7)
#   S3_BUCKET       S3/B2 bucket for offsite upload (optional)
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly COMPOSE_FILE="${PROJECT_DIR}/docker-compose.prod.yml"
readonly ENV_FILE="${PROJECT_DIR}/.env.prod"
readonly COMPOSE_CMD="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE}"

readonly TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
readonly BACKUP_BASE="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
readonly BACKUP_PATH="${BACKUP_BASE}/${TIMESTAMP}"
readonly RETAIN_DAYS="${BACKUP_RETAIN:-7}"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log_info()  { echo "[BACKUP] $(date '+%Y-%m-%d %H:%M:%S') [INFO]  $*"; }
log_warn()  { echo "[BACKUP] $(date '+%Y-%m-%d %H:%M:%S') [WARN]  $*" >&2; }
log_error() { echo "[BACKUP] $(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*" >&2; }

die() { log_error "$@"; exit 1; }

cleanup_on_error() {
    log_error "Backup failed. Cleaning up partial backup at ${BACKUP_PATH}..."
    rm -rf "${BACKUP_PATH}"
    exit 1
}

# Set trap for error cleanup
trap cleanup_on_error ERR

# -----------------------------------------------------------------------------
# Load environment variables for credentials
# -----------------------------------------------------------------------------
load_env() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        die "Environment file not found: ${ENV_FILE}"
    fi

    # Source env file (filter out comments and empty lines)
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$')
    set +a

    log_info "Environment loaded from ${ENV_FILE}"
}

# -----------------------------------------------------------------------------
# Create backup directory
# -----------------------------------------------------------------------------
create_backup_dir() {
    log_info "Creating backup directory: ${BACKUP_PATH}"
    mkdir -p "${BACKUP_PATH}"
}

# -----------------------------------------------------------------------------
# Backup PostgreSQL
# -----------------------------------------------------------------------------
backup_postgres() {
    log_info "Backing up PostgreSQL..."

    local pg_user="${POSTGRES_USER:-enjin}"
    local pg_db="${POSTGRES_DB:-enjin}"
    local dump_file="${BACKUP_PATH}/postgres_${pg_db}.sql.gz"

    ${COMPOSE_CMD} exec -T postgres \
        pg_dump -U "${pg_user}" -d "${pg_db}" --clean --if-exists --no-owner \
        | gzip > "${dump_file}"

    local size
    size=$(du -sh "${dump_file}" | cut -f1)
    log_info "PostgreSQL backup complete: ${dump_file} (${size})"
}

# -----------------------------------------------------------------------------
# Backup Neo4j
# -----------------------------------------------------------------------------
backup_neo4j() {
    log_info "Backing up Neo4j..."

    local neo4j_user="${NEO4J_USER:-neo4j}"
    local neo4j_pass="${NEO4J_PASSWORD}"
    local dump_file="${BACKUP_PATH}/neo4j_export.cypher.gz"

    # Export all nodes and relationships using cypher-shell
    # We use APOC export if available, otherwise fall back to a basic Cypher dump
    ${COMPOSE_CMD} exec -T neo4j cypher-shell \
        -u "${neo4j_user}" -p "${neo4j_pass}" \
        --format plain \
        "CALL apoc.export.cypher.all(null, {streamStatements:true, format:'cypher-shell'})" \
        2>/dev/null \
        | gzip > "${dump_file}" || {

        log_warn "APOC export not available. Falling back to basic node/relationship export..."

        # Fallback: dump nodes and relationships as JSON
        local fallback_file="${BACKUP_PATH}/neo4j_nodes.json.gz"
        ${COMPOSE_CMD} exec -T neo4j cypher-shell \
            -u "${neo4j_user}" -p "${neo4j_pass}" \
            --format plain \
            "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props LIMIT 1000000" \
            | gzip > "${fallback_file}"

        local rel_file="${BACKUP_PATH}/neo4j_relationships.json.gz"
        ${COMPOSE_CMD} exec -T neo4j cypher-shell \
            -u "${neo4j_user}" -p "${neo4j_pass}" \
            --format plain \
            "MATCH (a)-[r]->(b) RETURN id(a) AS from_id, type(r) AS type, properties(r) AS props, id(b) AS to_id LIMIT 1000000" \
            | gzip > "${rel_file}"

        log_info "Neo4j fallback export complete."
        return
    }

    local size
    size=$(du -sh "${dump_file}" | cut -f1)
    log_info "Neo4j backup complete: ${dump_file} (${size})"
}

# -----------------------------------------------------------------------------
# Backup Redis
# -----------------------------------------------------------------------------
backup_redis() {
    log_info "Backing up Redis..."

    local dump_file="${BACKUP_PATH}/redis_appendonly.aof.gz"

    # Trigger a BGREWRITEAOF to ensure data is flushed
    ${COMPOSE_CMD} exec -T redis redis-cli BGREWRITEAOF >/dev/null 2>&1 || true
    sleep 3

    # Copy the AOF file from the container
    local container_id
    container_id=$(${COMPOSE_CMD} ps -q redis)

    if [[ -n "${container_id}" ]]; then
        docker cp "${container_id}:/data/appendonly.aof" "${BACKUP_PATH}/redis_appendonly.aof" 2>/dev/null || {
            # Fall back to RDB dump
            log_warn "AOF file not found, falling back to RDB dump..."
            ${COMPOSE_CMD} exec -T redis redis-cli BGSAVE >/dev/null 2>&1 || true
            sleep 3
            docker cp "${container_id}:/data/dump.rdb" "${BACKUP_PATH}/redis_dump.rdb" 2>/dev/null || true
        }

        # Compress whatever we got
        if [[ -f "${BACKUP_PATH}/redis_appendonly.aof" ]]; then
            gzip "${BACKUP_PATH}/redis_appendonly.aof"
        elif [[ -f "${BACKUP_PATH}/redis_dump.rdb" ]]; then
            gzip "${BACKUP_PATH}/redis_dump.rdb"
            dump_file="${BACKUP_PATH}/redis_dump.rdb.gz"
        fi
    else
        log_warn "Redis container not running. Skipping Redis backup."
        return
    fi

    if [[ -f "${dump_file}" ]]; then
        local size
        size=$(du -sh "${dump_file}" | cut -f1)
        log_info "Redis backup complete: ${dump_file} (${size})"
    fi
}

# -----------------------------------------------------------------------------
# Backup Meilisearch
# -----------------------------------------------------------------------------
backup_meilisearch() {
    log_info "Backing up Meilisearch data..."

    local dump_file="${BACKUP_PATH}/meilisearch_data.tar.gz"

    # Trigger a Meilisearch dump via API
    local meili_key="${MEILI_MASTER_KEY}"
    local dump_response
    dump_response=$(${COMPOSE_CMD} exec -T meilisearch \
        curl -s -X POST "http://localhost:7700/dumps" \
        -H "Authorization: Bearer ${meili_key}" 2>/dev/null || echo "{}")

    # Wait for dump to complete
    sleep 10

    # Copy the data volume contents
    local container_id
    container_id=$(${COMPOSE_CMD} ps -q meilisearch)

    if [[ -n "${container_id}" ]]; then
        docker cp "${container_id}:/meili_data/dumps" "${BACKUP_PATH}/meili_dumps" 2>/dev/null || true

        if [[ -d "${BACKUP_PATH}/meili_dumps" ]]; then
            tar -czf "${dump_file}" -C "${BACKUP_PATH}" meili_dumps
            rm -rf "${BACKUP_PATH}/meili_dumps"

            local size
            size=$(du -sh "${dump_file}" | cut -f1)
            log_info "Meilisearch backup complete: ${dump_file} (${size})"
        else
            log_warn "Meilisearch dumps directory not found. Skipping."
        fi
    else
        log_warn "Meilisearch container not running. Skipping."
    fi
}

# -----------------------------------------------------------------------------
# Create final archive
# -----------------------------------------------------------------------------
create_archive() {
    log_info "Creating final backup archive..."

    local archive="${BACKUP_BASE}/enjin_backup_${TIMESTAMP}.tar.gz"
    tar -czf "${archive}" -C "${BACKUP_BASE}" "${TIMESTAMP}"

    # Remove the uncompressed directory
    rm -rf "${BACKUP_PATH}"

    local size
    size=$(du -sh "${archive}" | cut -f1)
    log_info "Final archive created: ${archive} (${size})"
}

# -----------------------------------------------------------------------------
# Rotate old backups (keep last N days)
# -----------------------------------------------------------------------------
rotate_backups() {
    log_info "Rotating backups (keeping last ${RETAIN_DAYS} daily backups)..."

    local count=0
    # List backup archives sorted by date (newest first), skip the first RETAIN_DAYS
    while IFS= read -r old_backup; do
        if [[ -n "${old_backup}" ]]; then
            log_info "Removing old backup: ${old_backup}"
            rm -f "${old_backup}"
            count=$((count + 1))
        fi
    done < <(ls -1t "${BACKUP_BASE}"/enjin_backup_*.tar.gz 2>/dev/null | tail -n +"$((RETAIN_DAYS + 1))")

    if [[ ${count} -gt 0 ]]; then
        log_info "Removed ${count} old backup(s)."
    else
        log_info "No old backups to remove."
    fi
}

# -----------------------------------------------------------------------------
# Upload to S3/B2 (optional, placeholder)
# -----------------------------------------------------------------------------
upload_offsite() {
    local s3_bucket="${S3_BUCKET:-}"

    if [[ -z "${s3_bucket}" ]]; then
        log_info "No S3_BUCKET configured. Skipping offsite upload."
        return
    fi

    local archive="${BACKUP_BASE}/enjin_backup_${TIMESTAMP}.tar.gz"

    if ! command -v aws &>/dev/null; then
        log_warn "AWS CLI not installed. Skipping offsite upload."
        return
    fi

    log_info "Uploading backup to ${s3_bucket}..."
    aws s3 cp "${archive}" "s3://${s3_bucket}/enjin/enjin_backup_${TIMESTAMP}.tar.gz"
    log_info "Offsite upload complete."
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    log_info "=========================================="
    log_info "Starting Enjin backup..."
    log_info "=========================================="

    load_env
    create_backup_dir
    backup_postgres
    backup_neo4j
    backup_redis
    backup_meilisearch
    create_archive
    rotate_backups
    upload_offsite

    log_info "=========================================="
    log_info "Backup completed successfully!"
    log_info "=========================================="
}

main "$@"
