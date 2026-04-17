#!/bin/sh
# Entrypoint script — runs as root, fixes bind-mount permissions, then drops to agora_user.
#
# Problem: bind-mounted host directories are owned by root (or another host user).
# The application user (agora_user) cannot write to them.
# Solution: chown the mount points while still root, then exec as agora_user.
#
# Directories that may be bind-mounted and need write access:
#   /app/resources/docs  — Platon docs download cache
#   /opt/models          — HuggingFace model cache

set -e

AGORA_UID=$(id -u agora_user)
AGORA_GID=$(id -g agora_user)

for dir in /app/resources/docs /opt/models; do
    if [ -d "$dir" ]; then
        current_owner=$(stat -c '%u' "$dir")
        if [ "$current_owner" != "$AGORA_UID" ]; then
            echo "[entrypoint] Fixing ownership of $dir (was uid=$current_owner, setting to uid=$AGORA_UID)"
            chown -R "$AGORA_UID:$AGORA_GID" "$dir"
        fi
    else
        echo "[entrypoint] Creating $dir"
        mkdir -p "$dir"
        chown "$AGORA_UID:$AGORA_GID" "$dir"
    fi
done

# UVICORN_WORKERS defaults to 1 if not set. Override via the environment
# (e.g. UVICORN_WORKERS=4 in .env.prod) to scale up for production.
WORKERS="${UVICORN_WORKERS:-1}"
RELOAD_FLAG=""
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
    RELOAD_FLAG="--reload"
fi

exec gosu agora_user uvicorn src.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$WORKERS" \
    $RELOAD_FLAG

