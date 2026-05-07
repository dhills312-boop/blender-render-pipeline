#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <pod-ssh-host> <local-project-dir> [remote-dir]"
  exit 1
fi

POD_HOST="$1"
LOCAL_DIR="$2"
REMOTE_DIR="${3:-/workspace/project}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_OPTS="${SSH_OPTS:-}"

echo "[sync-to-volume] ${LOCAL_DIR} -> ${POD_HOST}:${REMOTE_DIR}"
rsync -avz --progress \
  -e "ssh ${SSH_OPTS}" \
  --exclude-from="${SCRIPT_DIR}/.rsyncignore" \
  "${LOCAL_DIR%/}/" "${POD_HOST}:${REMOTE_DIR%/}/"
