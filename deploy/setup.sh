#!/usr/bin/env bash
# =============================================================================
# Enjin OSINT Platform - First-Time VPS Setup Script
# Run as root on a fresh Ubuntu 22.04+ VPS (Hetzner/DigitalOcean).
#
# Usage: curl -sSL <raw_url>/deploy/setup.sh | sudo bash
#    or: sudo bash deploy/setup.sh
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
readonly APP_USER="enjin"
readonly APP_DIR="/opt/enjin"
readonly SCRIPT_NAME="$(basename "$0")"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log_info()  { echo "[INFO]  ${SCRIPT_NAME}: $*"; }
log_warn()  { echo "[WARN]  ${SCRIPT_NAME}: $*" >&2; }
log_error() { echo "[ERROR] ${SCRIPT_NAME}: $*" >&2; }

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
preflight_checks() {
    if [[ "$(id -u)" -ne 0 ]]; then
        log_error "This script must be run as root."
        exit 1
    fi

    if ! command -v apt-get &>/dev/null; then
        log_error "This script requires a Debian/Ubuntu-based system with apt."
        exit 1
    fi

    log_info "Pre-flight checks passed."
}

# -----------------------------------------------------------------------------
# Update system packages
# -----------------------------------------------------------------------------
update_system() {
    log_info "Updating system packages..."
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        software-properties-common \
        ufw \
        fail2ban \
        unattended-upgrades \
        jq \
        git
    log_info "System packages updated."
}

# -----------------------------------------------------------------------------
# Install Docker Engine (official repository)
# -----------------------------------------------------------------------------
install_docker() {
    if command -v docker &>/dev/null; then
        log_info "Docker is already installed: $(docker --version)"
        return
    fi

    log_info "Installing Docker Engine..."

    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Add the Docker repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Enable and start Docker
    systemctl enable docker
    systemctl start docker

    log_info "Docker installed: $(docker --version)"
    log_info "Docker Compose: $(docker compose version)"
}

# -----------------------------------------------------------------------------
# Install Certbot
# -----------------------------------------------------------------------------
install_certbot() {
    if command -v certbot &>/dev/null; then
        log_info "Certbot is already installed: $(certbot --version 2>&1)"
        return
    fi

    log_info "Installing Certbot..."

    # Try snap first (preferred), fall back to apt
    if command -v snap &>/dev/null; then
        snap install core 2>/dev/null || true
        snap refresh core 2>/dev/null || true
        snap install --classic certbot
        ln -sf /snap/bin/certbot /usr/bin/certbot
    else
        apt-get install -y certbot
    fi

    log_info "Certbot installed: $(certbot --version 2>&1)"
}

# -----------------------------------------------------------------------------
# Create application user
# -----------------------------------------------------------------------------
create_app_user() {
    if id "${APP_USER}" &>/dev/null; then
        log_info "User '${APP_USER}' already exists."
    else
        log_info "Creating user '${APP_USER}'..."
        useradd --create-home --shell /bin/bash "${APP_USER}"
    fi

    # Add to docker group so the user can run docker without sudo
    usermod -aG docker "${APP_USER}"
    log_info "User '${APP_USER}' added to docker group."
}

# -----------------------------------------------------------------------------
# Create application directory
# -----------------------------------------------------------------------------
create_app_dir() {
    log_info "Creating application directory at ${APP_DIR}..."
    mkdir -p "${APP_DIR}"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}"
    chmod 750 "${APP_DIR}"

    # Create subdirectories for backups and logs
    mkdir -p "${APP_DIR}/backups"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/backups"

    log_info "Application directory created."
}

# -----------------------------------------------------------------------------
# Configure UFW firewall
# -----------------------------------------------------------------------------
configure_firewall() {
    log_info "Configuring UFW firewall..."

    # Reset to defaults
    ufw --force reset

    # Default policies
    ufw default deny incoming
    ufw default allow outgoing

    # Allow SSH (critical - do this first to avoid lockout)
    ufw allow 22/tcp comment "SSH"

    # Allow HTTP and HTTPS
    ufw allow 80/tcp comment "HTTP"
    ufw allow 443/tcp comment "HTTPS"

    # Enable firewall
    ufw --force enable

    log_info "Firewall configured. Allowed ports: 22, 80, 443."
    ufw status verbose
}

# -----------------------------------------------------------------------------
# Configure automatic security updates
# -----------------------------------------------------------------------------
configure_auto_updates() {
    log_info "Configuring automatic security updates..."

    cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

    cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

    systemctl enable unattended-upgrades
    systemctl start unattended-upgrades

    log_info "Automatic security updates configured."
}

# -----------------------------------------------------------------------------
# Configure fail2ban for SSH protection
# -----------------------------------------------------------------------------
configure_fail2ban() {
    log_info "Configuring fail2ban..."

    cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

    systemctl enable fail2ban
    systemctl restart fail2ban

    log_info "fail2ban configured for SSH protection."
}

# -----------------------------------------------------------------------------
# Print next steps
# -----------------------------------------------------------------------------
print_next_steps() {
    echo ""
    echo "============================================================================="
    echo " Enjin VPS Setup Complete!"
    echo "============================================================================="
    echo ""
    echo " Next steps:"
    echo ""
    echo "   1. Copy your project to the server:"
    echo "      rsync -avz --exclude node_modules --exclude .git \\"
    echo "        ./ ${APP_USER}@<SERVER_IP>:${APP_DIR}/"
    echo ""
    echo "   2. Copy your production env file:"
    echo "      scp .env.prod ${APP_USER}@<SERVER_IP>:${APP_DIR}/.env.prod"
    echo ""
    echo "   3. SSH into the server as '${APP_USER}':"
    echo "      ssh ${APP_USER}@<SERVER_IP>"
    echo ""
    echo "   4. Run the deploy script:"
    echo "      cd ${APP_DIR} && bash deploy/deploy.sh --domain your.domain.com \\"
    echo "        --email admin@domain.com --env-file .env.prod"
    echo ""
    echo "   Or use the automated deploy script from your local machine:"
    echo "      bash deploy/deploy.sh --domain your.domain.com \\"
    echo "        --email admin@domain.com --env-file .env.prod \\"
    echo "        --host <SERVER_IP> --user ${APP_USER}"
    echo ""
    echo "============================================================================="
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    log_info "Starting Enjin VPS setup..."
    preflight_checks
    update_system
    install_docker
    install_certbot
    create_app_user
    create_app_dir
    configure_firewall
    configure_auto_updates
    configure_fail2ban
    print_next_steps
    log_info "Setup complete."
}

main "$@"
