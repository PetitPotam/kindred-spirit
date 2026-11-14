#!/bin/bash
# Linux (and any computer with Docker): start her brain from its Docker image, or update it (#128, docker/README.md).
# Her settings and memories stay in your ~/.kindred-spirit; the ports are published on 127.0.0.1 only.
#
#   scripts/docker-run.sh            the newest image (downloads it the first time: about 1 GB)
#   scripts/docker-run.sh 0.4.0      a given version
#   scripts/docker-run.sh --stop     stop and remove the container (your files stay)
#   KINDRED_IMAGE=kindred-spirit-brain scripts/docker-run.sh   an image you built yourself
set -euo pipefail
NAME=kindred-spirit
IMAGE="${KINDRED_IMAGE:-ghcr.io/petitpotam/kindred-spirit-brain:${1:-latest}}"
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
command -v docker >/dev/null || { echo "Docker isn't installed: https://docs.docker.com/engine/install/"; exit 1; }
docker rm -f "$NAME" >/dev/null 2>&1 || true
[[ "${1:-}" == --stop ]] && { echo "Stopped."; exit 0; }
mkdir -p "$KH"  # (yours: Docker would make it as root)
[[ -n "${KINDRED_IMAGE:-}" ]] || docker pull -q "$IMAGE"
docker run -d --name "$NAME" --restart unless-stopped --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:47811:47811 -p 127.0.0.1:11440:11440 \
  -v "$KH:/home/pip/.kindred-spirit" ${KINDRED_DOCKER_ARGS:-} "$IMAGE" >/dev/null
echo "Her brain is starting (the first time, it downloads her voice and hearing: a few minutes)."
echo "Her dashboard: http://127.0.0.1:11440   Her log: docker logs -f $NAME   Stop: scripts/docker-run.sh --stop"
