#!/usr/bin/env bash
set -euo pipefail

# setup.sh
# Assumes these files are in the same directory as this script:
#   - img_handler.com        (nginx site config template)
#   - img_handler.service     (systemd unit)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NGINX_SRC="${SCRIPT_DIR}/img_handler.com"
NGINX_AVAIL="/etc/nginx/sites-available/img_handler.com"
NGINX_ENABLED="/etc/nginx/sites-enabled/img_handler.com"

ENV_DIR="/etc/img_handler"
ENV_FILE="${ENV_DIR}/img_handler.env"

SYSTEMD_SRC="${SCRIPT_DIR}/img_handler.service"
SYSTEMD_DEST="/etc/systemd/system/img_handler.service"

SERVICE_NAME="img_handler"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Please run as root (e.g. sudo ./setup.sh)" >&2
    exit 1
  fi
}

require_files() {
  [[ -f "$NGINX_SRC" ]] || { echo "ERROR: Missing $NGINX_SRC" >&2; exit 1; }
  [[ -f "$SYSTEMD_SRC" ]] || { echo "ERROR: Missing $SYSTEMD_SRC" >&2; exit 1; }
}

step1_nginx_install() {
  echo "[2/4] Installing Nginx site config..."
  sed "s|__PUBLIC_LINK_SECRET__|${PUBLIC_LINK_SECRET}|g" "$NGINX_SRC" > "$NGINX_AVAIL"
  ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"
}

step2_nginx_restart() {
  echo "[3/4] Testing and restarting Nginx..."
  nginx -t
  systemctl restart nginx
}

generate_secret() {
  # Prefer openssl, fallback to python
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
  fi
}

read_existing_env_value() {
  local key="$1"
  if [[ -f "$ENV_FILE" ]]; then
    grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true
  fi
}

step3_env_file() {
  echo "[1/4] Creating / updating env file with service secrets..."
  mkdir -p "$ENV_DIR"
  chmod 700 "$ENV_DIR"

  AUTH_TOKEN="$(read_existing_env_value AUTH_TOKEN)"
  PUBLIC_LINK_SECRET="$(read_existing_env_value PUBLIC_LINK_SECRET)"

  if [[ -z "$AUTH_TOKEN" ]]; then
    AUTH_TOKEN="$(generate_secret)"
  fi

  if [[ -z "$PUBLIC_LINK_SECRET" ]]; then
    PUBLIC_LINK_SECRET="$(generate_secret)"
  fi

  umask 077
  {
    echo "AUTH_TOKEN=${AUTH_TOKEN}"
    echo "PUBLIC_LINK_SECRET=${PUBLIC_LINK_SECRET}"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"

   echo "   Wrote ${ENV_FILE} (permissions 600)."
}

step4_systemd_install_start() {
  echo "[4/4] Installing systemd service and starting it..."
  cp -f "$SYSTEMD_SRC" "$SYSTEMD_DEST"
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"
  systemctl --no-pager --full status "$SERVICE_NAME" || true
}

main() {
  require_root
  require_files

  step3_env_file
  step1_nginx_install
  step2_nginx_restart
  step4_systemd_install_start

  echo "Done."
}

main "$@"
