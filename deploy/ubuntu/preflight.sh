#!/usr/bin/env bash
set -euo pipefail
echo "NEXVARY Voice — read-only Ubuntu preflight"
printf '\nSystem:\n'
uname -a
printf '\nDisk free:\n'
df -h /
printf '\nRAM:\n'
free -h
printf '\nDocker/Compose:\n'
docker --version 2>&1 || true
docker compose version 2>&1 || true
printf '\nListening ports:\n'
ss -lntp || true
printf '\nExisting containers:\n'
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}' || true
printf '\nExisting reverse proxy services:\n'
systemctl is-active nginx apache2 caddy 2>/dev/null || true
echo "Preflight complete. No settings were modified."
