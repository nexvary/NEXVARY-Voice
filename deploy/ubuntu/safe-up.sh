#!/usr/bin/env bash
# Guarded full-speech setup. Deliberately refuses resource-starved hosts.
set -euo pipefail
cd "$(dirname "$0")"
min_total_kib=4194304   # conservative 4GiB admission threshold
min_available_kib=2097152 # 2GiB available headroom before starting
total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
if (( total < min_total_kib || available < min_available_kib )); then
  echo "REFUSED: insufficient RAM headroom for NEXVARY Voice full speech engine." >&2
  echo "Total: $((total/1024)) MiB; available: $((available/1024)) MiB." >&2
  echo "Keep existing Ubuntu workloads safe. Run deploy/ubuntu/preflight.sh." >&2
  exit 3
fi
if [[ ! -r .env ]]; then
  echo "REFUSED: deploy/ubuntu/.env is missing; configure a secret privately." >&2
  exit 4
fi
token=$(sed -n 's/^NEXVARY_API_TOKEN=//p' .env | tail -n 1)
if [[ ${#token} -lt 32 || "$token" == *CHANGE_TO* ]]; then
  echo "REFUSED: NEXVARY_API_TOKEN must be a non-placeholder secret >=32 characters." >&2
  exit 4
fi
if ! docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
  echo "REFUSED: no Docker daemon permissions. Check sudo docker ps manually." >&2
  exit 5
fi
port=$(sed -n 's/^NEXVARY_VOICE_PORT=//p' .env | tail -n 1)
port=${port:-18781}
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  echo "REFUSED: invalid host port." >&2
  exit 6
fi
if ss -ltnH | awk '{print $4}' | grep -Eq ":$port$"; then
  echo "REFUSED: port $port is already listening." >&2
  exit 6
fi
docker compose --env-file .env -f compose.yml config --quiet
echo "Checks passed. Starting only the named NEXVARY Voice Compose project on 127.0.0.1:$port."
docker compose --env-file .env -f compose.yml up -d --build
