#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <pod-ssh-host> [local-destination] [remote-output-dir]"
  exit 1
fi

POD_HOST="$1"
DEST="${2:-./renders}"
REMOTE_OUTPUT="${3:-/workspace/output}"
SSH_OPTS="${SSH_OPTS:-}"

mkdir -p "$DEST"
echo "[pull-renders] ${POD_HOST}:${REMOTE_OUTPUT} -> ${DEST}"
rsync -avz --progress -e "ssh ${SSH_OPTS}" "${POD_HOST}:${REMOTE_OUTPUT%/}/" "${DEST%/}/"
