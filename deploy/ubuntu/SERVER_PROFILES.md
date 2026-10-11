# Ubuntu deployment profiles and observed preflight

## Observed on 2026-10-11

The user-supplied Ubuntu 24.04.5 AWS preflight showed **909 MiB total RAM,
384 MiB available, and 2 GiB swap**, 31 GiB free disk space, Docker 29.8.2,
Compose v5.6.0, and an active Nginx instance serving several existing ports
(80, 443, 8443, 8787, 9090-9092 etc.). The process owner could not list Docker
containers because `ubuntu` lacked access to `/var/run/docker.sock`.
Port 18781 was not listening at the time of that check. These are point-in-time
observations, not proof of available container capacity or permission to deploy.

**Do not deploy the full Whisper/Argos/Piper workload on this machine as-is.**
Memory use can spike during model loading, inference and FFmpeg video jobs.
Swap does not provide real-time inference performance and can hurt all other services.

## Profiles

- **Coordination-only host (current AWS instance):** only after auditing existing
  containers, use lightweight reverse proxy / API coordination, not local ASR,
  audio TTS or video rendering. There is *no claimed ready-to-use full-speech
  image for this profile*. In particular, the full `compose.yml` is not safe to
  start here. The public or private IP must not be hardcoded in the Android client.
- **Dedicated inference worker:** a separate machine or upgraded instance with
  **at least 4 GiB RAM, preferably 8 GiB+** (capacity planning estimates, not
  measured guarantees), suitable CPU cores or GPU, and model disk budget.
  Benchmark Arabic/Hindi voices, concurrent use, and peak FFmpeg utilization
  before exposing any service.
- **Developer desktop:** Windows machine runs `python -m voice_engine.desktop_gui`
  and speech models locally; private Ubuntu can later act as secure control plane.

## Safe checks on existing server (read-only)

```bash
cd ~/NEXVARY-Voice
git pull --ff-only
bash deploy/ubuntu/preflight.sh
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
sudo docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
sudo nginx -t
```

Sharing the container names, ports and memory pressure is sufficient; **redact**
usernames, credentials, paths containing secrets, and public endpoints if private.
Do not share `nginx -T` unredacted because it can disclose private configuration.

Do not run `docker compose up`, `down`, `docker system prune`, `nginx -s reload`,
`apt upgrade`, or reboot as part of these diagnostics. Do not `chmod 666` the
Docker socket or add users to the Docker group merely to simplify installation:
that grants root-equivalent control.

## Admission guard for the full engine

On a **separate** adequately sized inference host, after inspecting services,
configure `deploy/ubuntu/.env` and use:

```bash
bash deploy/ubuntu/safe-up.sh
```

The guard blocks startup if the machine has under 4 GiB installed RAM, under
2 GiB available RAM, an invalid secret, an occupied port, or inaccessible Docker.
It does not manage Nginx, certificates or other Compose projects. A passed
threshold **does not guarantee** real-time audio performance.
