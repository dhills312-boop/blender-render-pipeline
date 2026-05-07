#!/usr/bin/env bash
set -euo pipefail

BLENDER_VERSION="${BLENDER_VERSION:-4.5.0}"
INSTALL_DIR="${INSTALL_DIR:-/opt/blender}"
WORKSPACE="${WORKSPACE:-/workspace}"

echo "[pod-setup] Installing Blender ${BLENDER_VERSION}"
apt-get update
apt-get install -y --no-install-recommends wget ca-certificates xz-utils rsync openssh-client python3

mkdir -p "$INSTALL_DIR"
cd /tmp
wget -q "https://download.blender.org/release/Blender4.5/blender-${BLENDER_VERSION}-linux-x64.tar.xz"
tar -xf "blender-${BLENDER_VERSION}-linux-x64.tar.xz" -C "$INSTALL_DIR" --strip-components=1
ln -sf "$INSTALL_DIR/blender" /usr/local/bin/blender

mkdir -p "$WORKSPACE/project" "$WORKSPACE/output" "$WORKSPACE/cache"

echo "[pod-setup] Blender version:"
blender -b --version
echo "[pod-setup] Cycles device probe:"
blender -b --python-expr "import bpy; prefs=bpy.context.preferences.addons['cycles'].preferences; print('compute_device_type=', getattr(prefs, 'compute_device_type', 'unknown')); prefs.get_devices(); print([(d.name, d.type) for d in prefs.devices])"
