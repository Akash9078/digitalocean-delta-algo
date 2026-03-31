#!/usr/bin/env bash
# =============================================================================
# deploy/setup_droplet.sh
# One-shot DigitalOcean Droplet setup for the Delta Algo Trading Bot
#
# Run as root on a fresh Ubuntu 22.04 / 24.04 Droplet:
#   curl -sL https://raw.githubusercontent.com/Akash9078/digitalocean-delta-algo/main/deploy/setup_droplet.sh | bash
# =============================================================================
set -euo pipefail

APP_DIR="/opt/delta-algo"
REPO="https://github.com/Akash9078/digitalocean-delta-algo.git"

echo "╔══════════════════════════════════════════════════════╗"
echo "║  Delta Algo Bot – DigitalOcean Droplet Setup         ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── 1. System updates ─────────────────────────────────────────────────────────
echo "[1/7] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Install Docker ─────────────────────────────────────────────────────────
echo "[2/7] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

# Install docker compose plugin
if ! command -v docker compose &>/dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi

# ── 3. Clone repository ───────────────────────────────────────────────────────
echo "[3/7] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "  Directory $APP_DIR already exists – pulling latest..."
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO" "$APP_DIR"
fi

# ── 4. Create .env from example ───────────────────────────────────────────────
echo "[4/7] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "⚠  ACTION REQUIRED: Edit $APP_DIR/.env and add your Delta API credentials."
    echo "   nano $APP_DIR/.env"
fi

# ── 5. Open firewall ports ────────────────────────────────────────────────────
echo "[5/7] Configuring UFW firewall..."
ufw allow ssh
ufw allow 8501/tcp
ufw --force enable

# ── 6. Start services ─────────────────────────────────────────────────────────
echo "[6/7] Building and starting containers..."
cd "$APP_DIR"
docker compose build --no-cache bot
docker compose up -d

# ── 7. Install systemd service for auto-restart on reboot ────────────────────
echo "[7/7] Installing systemd service..."
cat > /etc/systemd/system/delta-algo.service << EOF
[Unit]
Description=Delta Algo Trading Bot
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable delta-algo.service

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                      ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Commands:                                           ║"
echo "║    cd $APP_DIR"
echo "║    docker compose logs -f bot     # live bot logs    ║"
echo "║    docker compose ps              # container status  ║"
echo "║    docker compose restart bot     # restart bot       ║"
echo "║                                                       ║"
echo "║  API:       http://$(curl -s ifconfig.me):8501         ║"
echo "║  API Docs: http://$(curl -s ifconfig.me):8501/docs    ║"
echo "╚══════════════════════════════════════════════════════╝"
