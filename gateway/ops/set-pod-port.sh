#!/bin/bash
# After a pod restart RunPod may reassign the public TCP port. Point LiteLLM and the egress rule at the new one.
# Usage: set-pod-port.sh NEW_PORT   (run on the droplet, from /opt/argus/gateway)
set -euo pipefail
NEW="$1"
cd /opt/argus/gateway
sed -i -E "s#(api_base: http://[0-9.]+):[0-9]+/v1#\1:${NEW}/v1#" litellm-config.yaml
sed -i -E "s#^POD_PORT=.*#POD_PORT=${NEW}#" /etc/argus/egress.env
systemctl restart argus-egress.service
docker compose up -d --force-recreate litellm >/dev/null 2>&1
for i in $(seq 1 30); do [ "$(docker compose ps litellm --format '{{.Health}}')" = healthy ] && break; sleep 5; done
docker compose restart shim >/dev/null 2>&1
echo "pod port now ${NEW}; litellm $(docker compose ps litellm --format '{{.Health}}')"
