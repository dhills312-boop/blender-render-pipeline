#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <pod-ssh-host> [blend-file-relative-to-project] [render-script] [--terminate-after]"
  exit 1
fi

POD_HOST="$1"
BLEND_FILE="${2:-blender-output/lift-off/LO_083_spiderverse_downloaded_recipe.blend}"
RENDER_SCRIPT="${3:-render_still.py}"
SSH_OPTS="${SSH_OPTS:-}"
TERMINATE_AFTER="false"
if [[ "${4:-}" == "--terminate-after" ]]; then
  TERMINATE_AFTER="true"
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${ROOT_DIR}/workspace/project"
START_TIME="$(date +%s)"

echo "[render-remote] Syncing Blender project payload"
"${ROOT_DIR}/remote/sync-to-volume.sh" "$POD_HOST" "$PROJECT_DIR" "/workspace/project"

echo "[render-remote] Syncing render scripts/config"
ssh ${SSH_OPTS} "$POD_HOST" "mkdir -p /workspace/render-scripts /workspace/output"
rsync -avz --progress -e "ssh ${SSH_OPTS}" "${ROOT_DIR}/scripts/" "${POD_HOST}:/workspace/render-scripts/"

REMOTE_BLEND="/workspace/project/${BLEND_FILE}"
REMOTE_SCRIPT="/workspace/render-scripts/${RENDER_SCRIPT}"
REMOTE_CONFIG="/workspace/render-scripts/render_config.json"
echo "[render-remote] Rendering ${REMOTE_BLEND} with ${REMOTE_SCRIPT}"
ssh ${SSH_OPTS} "$POD_HOST" "cd /workspace/project && blender -b '${REMOTE_BLEND}' -P '${REMOTE_SCRIPT}' -- --config '${REMOTE_CONFIG}' --blend-file '${REMOTE_BLEND}'"

"${ROOT_DIR}/remote/pull-renders.sh" "$POD_HOST" "${ROOT_DIR}/renders"

END_TIME="$(date +%s)"
echo "[render-remote] Total elapsed: $((END_TIME - START_TIME)) seconds"

if [[ "$TERMINATE_AFTER" == "true" ]]; then
  echo "[render-remote] terminate-after requested."
  echo "[render-remote] Add RunPod API termination here once pod id/API token workflow is chosen."
fi
