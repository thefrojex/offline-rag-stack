#!/usr/bin/env bash
# Run on the OFFLINE machine. Needs Docker and the bundle tarball; needs no network.
#
# Usage: install-offline.sh <bundle.tar> [install-dir]
# Verifies checksums, loads images, restores the model volume, and starts the stack.
set -euo pipefail

BUNDLE="${1:?usage: install-offline.sh <bundle.tar> [install-dir]}"
DEST="${2:-./offline-rag-stack}"

sha256_check() { if command -v sha256sum >/dev/null; then sha256sum -c "$@"; else shasum -a 256 -c "$@"; fi; }

if [ -f "$BUNDLE.sha256" ]; then
  echo "== verifying tarball checksum"
  (cd "$(dirname "$BUNDLE")" && sha256_check "$(basename "$BUNDLE").sha256")
else
  echo "warning: $BUNDLE.sha256 not found, skipping outer checksum" >&2
fi

mkdir -p "$DEST"
echo "== extracting to $DEST"
tar -C "$DEST" -xf "$BUNDLE" --strip-components=1

cd "$DEST"
echo "== verifying contents"
sha256_check SHA256SUMS

echo "== loading images"
docker load -i images.tar

OLLAMA_IMAGE=$(grep '^ollama/' images.list | head -1)
echo "== restoring model volume"
docker volume create offline-rag-ollama-models >/dev/null
docker run --rm -v offline-rag-ollama-models:/models -v "$PWD":/in:ro \
  --entrypoint tar "$OLLAMA_IMAGE" -C /models -xf /in/models.tar

[ -f .env ] || cp .env.example .env

echo "== starting the stack (no build, no pull)"
docker compose up -d --no-build --pull never

echo "== waiting for health"
PORT=$(grep -E '^API_PORT=' .env | cut -d= -f2 || true)
PORT="${PORT:-8000}"
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "ready: http://127.0.0.1:$PORT"
    exit 0
  fi
  sleep 2
done
echo "stack did not become healthy in time; check: docker compose logs" >&2
exit 1
