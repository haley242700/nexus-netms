#!/usr/bin/env bash
set -euo pipefail

REPO="${SPEEDTEST_REPO:-/workspace/SpeedTest}"
TARGET="${NEXUS_DEPLOY_DIR:-/volume1/docker/nexus}"
HEALTH_URL="${NEXUS_HEALTH_URL:-http://192.168.110.54:3002/api/health}"

cd "$REPO"
PYTHON="${SPEEDTEST_PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3
"$PYTHON" manage.py test
"$PYTHON" manage.py package nexus
find "$REPO/dist/nexus" -type d -exec chmod 755 {} +
find "$REPO/dist/nexus" -type f -exec chmod 644 {} +

for name in \
  Dockerfile requirements.txt .dockerignore docker-compose.yaml \
  runtime network-dashboard reyee-exporter prometheus blackbox; do
  cp -a "$REPO/dist/nexus/$name" "$TARGET/"
done

docker compose -f "$TARGET/docker-compose.yaml" up -d --build
for attempt in $(seq 1 30); do
  if HEALTH=$(curl --fail --silent "$HEALTH_URL"); then
    printf '%s\n' "$HEALTH"
    break
  fi
  sleep 2
done
if [ -z "${HEALTH:-}" ]; then
  printf 'NEXUS health check failed.\n' >&2
  exit 1
fi
printf 'NEXUS deployment completed.\n'
