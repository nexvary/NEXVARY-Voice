#!/usr/bin/env bash
# Read-only diagnostics. Does not change Docker access groups or any service.
set -euo pipefail
echo "NEXVARY Voice — read-only Ubuntu preflight"
printf '\nSystem and CPU:\n'
uname -a
nproc
printf '\nDisk free:\n'
df -h /
printf '\nRAM and swap:\n'
free -h
total_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
avail_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
printf 'RAM capacity: %s MiB; available now: %s MiB\n' "$((total_kib/1024))" "$((avail_kib/1024))"
if (( total_kib < 4194304 || avail_kib < 2097152 )); then
  echo "RESOURCE WARNING: Full local speech inference not approved for deployment on current memory."
  echo "Use this host for lightweight control services only after container and proxy review."
else
  echo "Memory thresholds passed for a *candidate* deployment; performance still requires benchmarking."
fi
printf '\nDocker versions:\n'
docker --version 2>&1 || true
docker compose version 2>&1 || true
printf '\nListening ports:\n'
ss -lntp || true
printf '\nExisting containers (read-only):\n'
if docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
  docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' || true
elif command -v sudo >/dev/null && sudo -n docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
  sudo -n docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
  sudo -n docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' || true
else
  echo "Docker daemon access unavailable to this user; use 'sudo docker ps' separately."
  echo "Do not add the account to the docker group automatically (root-equivalent privileges)."
fi
printf '\nReverse proxy services:\n'
for service in nginx apache2 caddy; do
  printf '%s: ' "$service"
  systemctl is-active "$service" 2>/dev/null || true
done
echo "No configuration was modified."
