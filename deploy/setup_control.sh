#!/usr/bin/env bash
# CONTROL VM (Ubuntu 24.04, Vultr, same VPC). Run as root from the repo root.
# Usage: RUNNER_PRIVATE_IP=10.x.x.x RUNNER_SECRET=... VULTR_INFERENCE_API_KEY=... [MODEL=kimi-k2-instruct] [ACCESS_CODE=...] ./deploy/setup_control.sh
set -euo pipefail
: "${RUNNER_PRIVATE_IP:?}" "${RUNNER_SECRET:?}" "${VULTR_INFERENCE_API_KEY:?}"
PUBIP="$(curl -fsS https://ifconfig.me)"; DOMAIN="${DOMAIN:-${PUBIP//./-}.nip.io}"
apt-get update && apt-get install -y python3-venv caddy ufw
id agent &>/dev/null || useradd -r -m -s /usr/sbin/nologin agent
mkdir -p /opt/agent && cp -r control /opt/agent/ && chown -R agent /opt/agent
python3 -m venv /opt/agent/venv && /opt/agent/venv/bin/pip install -r control/requirements.txt
mkdir -p /etc/agent
cat > /etc/agent/control.env <<ENV
RUNNER_URL=http://$RUNNER_PRIVATE_IP:8001
RUNNER_SECRET=$RUNNER_SECRET
SESSION_SECRET=$(openssl rand -hex 32)
LLM_PROVIDER=vultr
VULTR_INFERENCE_API_KEY=$VULTR_INFERENCE_API_KEY
MODEL=${MODEL:-kimi-k2-instruct}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
ACCESS_CODE=${ACCESS_CODE:-}
BROWSER_ALLOWLIST=${BROWSER_ALLOWLIST:-example.com,wikipedia.org}
ENV
chmod 600 /etc/agent/control.env
curl -fsS https://api.vultrinference.com/v1/models -H "Authorization: Bearer $VULTR_INFERENCE_API_KEY" | grep -o '"id":"[^"]*"' | head -20 || echo "WARN: could not list models, check your key"
cp deploy/agent.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now agent
echo "$DOMAIN { encode gzip
  reverse_proxy 127.0.0.1:8000 { flush_interval -1 }
}" > /etc/caddy/Caddyfile && systemctl restart caddy
ufw default deny incoming && ufw default allow outgoing && ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
echo "Live at https://$DOMAIN"
