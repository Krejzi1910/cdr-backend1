#!/usr/bin/env bash
# =====================================================================
# Color Dice Rigged Backend — installer for Ubuntu (Oracle Cloud / VPS)
#
# Run as root or with sudo:
#   curl -sSL <URL>/install.sh | sudo bash
# Or:
#   sudo bash install.sh
#
# Requires Ubuntu 22.04+ (works on ARM64 / x86_64).
# =====================================================================
set -euo pipefail

# colors
G="\033[1;32m"; Y="\033[1;33m"; R="\033[1;31m"; B="\033[1;34m"; N="\033[0m"

if [[ "${EUID}" -ne 0 ]]; then
  echo -e "${R}Run as root (sudo bash install.sh)${N}"
  exit 1
fi

APP_DIR="/opt/cdr-backend"
DATA_DIR="/var/lib/cdr"
SERVICE_USER="cdr"
SERVICE_NAME="cdr-backend"
DEFAULT_PORT=8000

echo -e "${B}== Color Dice Rigged Backend — installer ==${N}"

# ---------- read inputs ----------
read -r -p "Port to listen on [${DEFAULT_PORT}]: " PORT
PORT="${PORT:-${DEFAULT_PORT}}"

if [[ -f "${APP_DIR}/.env" ]] && grep -q "CDR_API_KEY=" "${APP_DIR}/.env"; then
  API_KEY=$(grep "CDR_API_KEY=" "${APP_DIR}/.env" | cut -d= -f2)
  echo -e "${Y}Reusing existing API key.${N}"
else
  API_KEY=$(openssl rand -hex 16)
fi

echo -e "${G}API key:${N} ${API_KEY}"
echo -e "${G}Port:${N}    ${PORT}"
echo

# ---------- install deps ----------
echo -e "${B}[1/6] Installing system packages...${N}"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip ufw curl >/dev/null
echo -e "${G}OK${N}"

# ---------- system user ----------
echo -e "${B}[2/6] Creating service user...${N}"
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --shell /usr/sbin/nologin --home "${APP_DIR}" "${SERVICE_USER}"
fi
mkdir -p "${APP_DIR}" "${DATA_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" "${DATA_DIR}"
echo -e "${G}OK${N}"

# ---------- copy code ----------
echo -e "${B}[3/6] Copying app files...${N}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
cp -f "${SRC_DIR}/server.py" "${SRC_DIR}/farmer.py" "${SRC_DIR}/db.py" "${SRC_DIR}/requirements.txt" "${APP_DIR}/"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
echo -e "${G}OK${N}"

# ---------- venv ----------
echo -e "${B}[4/6] Creating Python venv and installing deps...${N}"
sudo -u "${SERVICE_USER}" python3 -m venv "${APP_DIR}/venv"
sudo -u "${SERVICE_USER}" "${APP_DIR}/venv/bin/pip" install --upgrade pip -q
sudo -u "${SERVICE_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q
echo -e "${G}OK${N}"

# ---------- env file ----------
cat > "${APP_DIR}/.env" <<EOF
CDR_API_KEY=${API_KEY}
CDR_DB_PATH=${DATA_DIR}/cdr.sqlite
CDR_PORT=${PORT}
EOF
chmod 600 "${APP_DIR}/.env"
chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}/.env"

# ---------- systemd unit ----------
echo -e "${B}[5/6] Installing systemd service...${N}"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Color Dice Rigged Backend
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"
echo -e "${G}OK${N}"

# ---------- firewall ----------
echo -e "${B}[6/6] Opening firewall port ${PORT}...${N}"
# iptables (Oracle Ubuntu uses iptables by default; ufw if configured)
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow "${PORT}/tcp" >/dev/null
  echo "  ufw rule added"
fi
# Oracle Ubuntu's default iptables-persistent
if iptables -L INPUT -n 2>/dev/null | grep -q "REJECT\|DROP"; then
  iptables -I INPUT -p tcp --dport "${PORT}" -j ACCEPT
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save >/dev/null 2>&1 || true
  fi
  echo "  iptables rule added"
fi
echo -e "${G}OK${N}"

# ---------- summary ----------
PUBLIC_IP=$(curl -s --max-time 3 https://api.ipify.org || echo "<your-server-ip>")
echo
echo -e "${G}========================================================${N}"
echo -e "${G}  Backend installed and running.${N}"
echo -e "${G}========================================================${N}"
echo
echo -e "  Backend URL:  ${Y}http://${PUBLIC_IP}:${PORT}${N}"
echo -e "  API Key:      ${Y}${API_KEY}${N}"
echo
echo -e "  Health check: ${B}curl http://${PUBLIC_IP}:${PORT}/api/health${N}"
echo -e "  Live logs:    ${B}sudo journalctl -fu ${SERVICE_NAME}${N}"
echo -e "  Restart:      ${B}sudo systemctl restart ${SERVICE_NAME}${N}"
echo
echo -e "${Y}Next step:${N} paste the Backend URL and API Key into the"
echo -e "Color Dice extension (popup → Backend Settings)."
echo
echo -e "${Y}IMPORTANT (Oracle Cloud):${N}"
echo -e "  In Oracle Cloud Console, open Security List of your VCN/subnet"
echo -e "  and add Ingress Rule: TCP, Source 0.0.0.0/0, Destination Port ${PORT}."
echo -e "  Without this, the port is blocked at the cloud network level."
echo
