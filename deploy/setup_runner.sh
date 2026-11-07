#!/usr/bin/env bash
# RUNNER VM (Ubuntu 24.04, Vultr, VPC attached). Run as root from the repo root.
# Usage: PRIVATE_IP=10.x.x.x CONTROL_PRIVATE_IP=10.x.x.y RUNNER_SECRET=... ./deploy/setup_runner.sh
set -euo pipefail
: "${PRIVATE_IP:?}" "${CONTROL_PRIVATE_IP:?}" "${RUNNER_SECRET:?}"
ALLOW="${BROWSER_ALLOWLIST:-example.com,wikipedia.org}"
apt-get update && apt-get install -y docker.io python3-venv ufw curl gpg
curl -fsSL https://gvisor.dev/archive.key | gpg --dearmor -o /usr/share/keyrings/gvisor.gpg
echo "deb [signed-by=/usr/share/keyrings/gvisor.gpg] https://storage.googleapis.com/gvisor/releases release main" > /etc/apt/sources.list.d/gvisor.list
apt-get update && apt-get install -y runsc
runsc install && systemctl restart docker

id runner &>/dev/null || useradd -r -m -s /usr/sbin/nologin -G docker runner
mkdir -p /opt/agent && cp -r runner /opt/agent/ && chown -R runner /opt/agent
python3 -m venv /opt/agent/venv && /opt/agent/venv/bin/pip install -r runner/requirements.txt

docker build -t sbx-python:1  -f runner/Dockerfile.python  runner/
docker build -t sbx-browser:1 -f runner/Dockerfile.browser runner/
docker build -t sbx-proxy:1   -f runner/Dockerfile.proxy   runner/

# Internal network: no route to the internet. The ONLY exit is the allowlist proxy.
docker network inspect sbx-internal &>/dev/null || docker network create --internal sbx-internal
docker rm -f egress-proxy &>/dev/null || true
echo "nameserver 1.1.1.1" > /opt/agent/resolv.conf
echo "nameserver 8.8.8.8" >> /opt/agent/resolv.conf
docker run -d --name egress-proxy --restart always --runtime=runsc --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 128m --pids-limit 100 -e ALLOW="$ALLOW" -v /opt/agent/resolv.conf:/etc/resolv.conf:ro sbx-proxy:1
docker network connect --alias egress-proxy sbx-internal egress-proxy
docker restart egress-proxy

mkdir -p /etc/agent
cat > /etc/agent/runner.env <<ENV
PRIVATE_IP=$PRIVATE_IP
RUNNER_SECRET=$RUNNER_SECRET
BROWSER_ALLOWLIST=$ALLOW
ENV
chmod 600 /etc/agent/runner.env && chown runner /etc/agent/runner.env
cp deploy/runner.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now runner

ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow from "$CONTROL_PRIVATE_IP" to any port 8001 proto tcp
ufw --force enable
echo "Runner up on $PRIVATE_IP:8001"
