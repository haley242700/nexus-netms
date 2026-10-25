#!/usr/bin/env bash
set -euo pipefail

REPO="${SPEEDTEST_REPO:-/workspace/SpeedTest}"
TARGET="${NEXUS_DEPLOY_DIR:-/volume1/docker/nexus}"

cd "$REPO"
PYTHON="${SPEEDTEST_PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3
"$PYTHON" manage.py test
"$PYTHON" manage.py package nexus

for name in \
  Dockerfile requirements.txt .dockerignore docker-compose.yaml \
  runtime network-dashboard reyee-exporter prometheus blackbox; do
  cp -a "$REPO/dist/nexus/$name" "$TARGET/"
done

docker compose -f "$TARGET/docker-compose.yaml" up -d --build
curl --fail --silent --show-error http://127.0.0.1:3002/api/health
printf '\nNEXUS deployment completed.\n'
