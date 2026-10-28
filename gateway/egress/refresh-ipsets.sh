#!/bin/bash
# Resolve hostname lists into ipsets. Run at boot, on a timer, and before each demo run.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
refresh() {  # ipset-name hostfile
  ipset create -exist "$1" hash:ip family inet timeout 3600
  grep -v '^#' "$2" | while read -r h; do
    [ -z "$h" ] && continue
    for ip in $(getent ahostsv4 "$h" | awk '{print $1}' | sort -u); do ipset add -exist "$1" "$ip" timeout 3600; done
  done
}
refresh allow_zitadel "$D/hosts-zitadel.txt"
refresh allow_acme "$D/hosts-acme.txt"
