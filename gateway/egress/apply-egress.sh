#!/bin/bash
# Default-deny egress for containers on the argus network, enforced in DOCKER-USER (Docker bypasses ufw).
# Static container IPs (see compose): caddy .12, shim .10, litellm .11, postgres .13
# Env: POD_IP, POD_PORT. Inbound traffic to published ports is untouched: only packets sourced from the subnet are filtered.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
: "${POD_IP:?}" "${POD_PORT:?}"
NET=172.28.0.0/24; SHIM=172.28.0.10; LLM=172.28.0.11; CADDY=172.28.0.12
"$D/refresh-ipsets.sh"
iptables -N ARGUS-EGRESS 2>/dev/null || iptables -F ARGUS-EGRESS
iptables -C DOCKER-USER -s $NET -j ARGUS-EGRESS 2>/dev/null || iptables -I DOCKER-USER 1 -s $NET -j ARGUS-EGRESS
A() { iptables -A ARGUS-EGRESS "$@"; }
A -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
A -d $NET -j RETURN
for ns in $(awk '/^nameserver/{print $2}' /run/systemd/resolve/resolv.conf | sort -u); do
  A -d "$ns" -p udp --dport 53 -j RETURN; A -d "$ns" -p tcp --dport 53 -j RETURN
done
A -s $LLM -d "$POD_IP" -p tcp --dport "$POD_PORT" -j RETURN
A -s $SHIM -p tcp --dport 443 -m set --match-set allow_zitadel dst -j RETURN
A -s $CADDY -p tcp --dport 443 -m set --match-set allow_acme dst -j RETURN
A -j REJECT --reject-with icmp-port-unreachable
