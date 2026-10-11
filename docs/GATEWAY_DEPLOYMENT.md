# NEXVARY Voice: light Ubuntu gateway (AWS 909 MiB RAM)

## Purpose

The existing server has about **909 MiB total RAM**, ~**423 MiB available**
in the latest user-supplied snapshot, and hosts FG MTM API, worker, PostgreSQL,
Watchtower, Shadowbox and Nginx. Do not start the Whisper/Piper inference stack
on this machine.

The dedicated *lightweight gateway* is intentionally separate from
`deploy/ubuntu/compose.yml` and never installs/loads Whisper, Piper, Argos or
FFmpeg. It can route compatible Android and Windows endpoints to a different,
trusted inference worker. **Until such a worker is configured, translation and
dubbing deliberately return HTTP 503**. The gateway is not itself a translation
engine.

The image runs under a non-root UID, with its own Compose project, 256 MiB
container memory cap, 0.5 CPU quota, and no Linux capabilities. It listens
ONLY on `127.0.0.1:18782`, not 80/443 or the FG MTM 8080/8787/909x ports.

## Read-only environment check

```bash
cd ~/NEXVARY-Voice
git pull --ff-only
bash deploy/ubuntu/preflight.sh
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
sudo docker stats --no-stream
sudo nginx -t
```

Do not restart, stop or recreate existing containers. Docker access via
`sudo` worked in the user-supplied second check; there is no reason to
change group membership or the socket permissions.

## Validation without deploying

```bash
cd ~/NEXVARY-Voice
sudo docker compose --env-file deploy/ubuntu/.env.gateway.example \
  -f deploy/ubuntu/compose.gateway.yml config --quiet
```

This only validates Compose syntax. It does not create containers.

## Optional lightweight deployment — requires an actual worker later

Use `cp deploy/ubuntu/.env.gateway.example deploy/ubuntu/.env.gateway`
and replace the placeholder token with `openssl rand -hex 32` **locally**.
Do not paste your token in ChatGPT or GitHub.
Leave `NEXVARY_WORKER_URL` empty until the external worker is
reachable and secured with HTTPS; do not assume this server can translate
without one. If port 18782 is unoccupied and resources remain adequate:

```bash
sudo docker compose --env-file deploy/ubuntu/.env.gateway \
  -f deploy/ubuntu/compose.gateway.yml up -d --build
curl -fsS http://127.0.0.1:18782/health
```

Expected response reports `worker_configured:false` until a worker is
configured. Even with a configured worker, this response does not establish
model availability or quality. No Nginx route is created automatically.
To connect phones remotely, audit existing Nginx configuration first and
add a **separate, authenticated HTTPS/WebSocket virtual host**, not a
replacement for an existing application. Plan concurrency/rate limiting,
IP restrictions and token rotation before opening any public route.

To stop only this new service, and not FG MTM/Outline:

```bash
sudo docker compose --env-file deploy/ubuntu/.env.gateway \
  -f deploy/ubuntu/compose.gateway.yml down
```

Do not run `down -v`, `docker system prune`, or any global restart.

## Worker deployment later

A separate inference machine (preferably 8 GiB RAM or more for initial
testing; benchmark the actual models) should offer:
`/v1/translate`, `/v1/subtitles/translate`, `/v1/live/audio`,
and `/v1/dub/jobs...` from the existing NEXVARY Voice engine over
authenticated HTTPS/WSS. Set `NEXVARY_WORKER_URL` to its base HTTPS
origin and `NEXVARY_WORKER_TOKEN` to the worker token. For private
network worker HTTP, a deliberate `NEXVARY_ALLOW_PRIVATE_HTTP_WORKER=1`
would be required in the gateway container configuration; the current
deployment blocks that by default.

Keep the frontend token separate from the worker token. Tokens are
configured only through local environment files and are not logged.

## Resource limits

The 256 MiB cap is a protective limit, **not** a measured guarantee
of stability on the 909 MiB server. Watch RSS, swap and container restart
counts after any approved deployment. Video upload is bounded to 80 MiB
and spooled to temporary storage rather than reading all data into RAM.
The gateway does not persist user transcripts or voice files.
