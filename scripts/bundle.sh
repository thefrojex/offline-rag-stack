#!/usr/bin/env bash
# Run on an ONLINE machine. Produces one tarball you can carry to an offline one:
#   dist/offline-rag-stack-<version>-<arch>.tar  (+ .sha256 beside it)
# containing: images.tar (docker save), models.tar (Ollama model volume), compose files,
# install scripts, and SHA256SUMS for everything inside.
#
# Usage: scripts/bundle.sh [--gpu] [--out DIR]
#   --gpu  also save the vLLM image (model weights for vLLM must be copied separately)
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="0.1.0"
OUT_DIR="dist"
WITH_GPU=0
while [ $# -gt 0 ]; do
  case "$1" in
    --gpu) WITH_GPU=1 ;;
    --out) OUT_DIR="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }

ARCH=$(docker info --format '{{.Architecture}}')
NAME="offline-rag-stack-$VERSION-$ARCH"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
PAYLOAD="$STAGE/$NAME"
mkdir -p "$PAYLOAD" "$OUT_DIR"

echo "== building and pulling images ($ARCH)"
docker compose build
docker compose pull ollama qdrant
IMAGES=$(docker compose config --images | grep -v '^vllm/' | sort -u)
if [ "$WITH_GPU" -eq 1 ]; then
  docker compose --profile gpu pull vllm
  IMAGES=$(docker compose --profile gpu config --images | sort -u)
fi

echo "== ensuring models are in the volume"
OLLAMA_IMAGE=$(docker compose config --images | grep '^ollama/' | head -1)
if ! docker volume inspect offline-rag-ollama-models >/dev/null 2>&1; then
  docker compose --profile online run --rm model-pull
fi
docker run --rm -v offline-rag-ollama-models:/root/.ollama --entrypoint ollama "$OLLAMA_IMAGE" list >/dev/null 2>&1 \
  || docker compose --profile online run --rm model-pull

echo "== saving images"
# shellcheck disable=SC2086
docker save -o "$PAYLOAD/images.tar" $IMAGES
echo "$IMAGES" > "$PAYLOAD/images.list"

echo "== exporting model volume"
docker run --rm -v offline-rag-ollama-models:/models:ro -v "$PAYLOAD":/out \
  --entrypoint tar "$OLLAMA_IMAGE" -C /models -cf /out/models.tar .

echo "== adding compose files and installer"
cp compose.yaml .env.example .env.gpu.example "$PAYLOAD/"
mkdir -p "$PAYLOAD/docker" "$PAYLOAD/scripts"
cp docker/check-models.sh docker/pull-models.sh "$PAYLOAD/docker/"
cp scripts/install-offline.sh scripts/verify_airgap.sh "$PAYLOAD/scripts/"
chmod +x "$PAYLOAD/scripts/"*.sh

echo "== checksums"
(cd "$PAYLOAD" && sha256 images.tar models.tar images.list compose.yaml .env.example .env.gpu.example \
  docker/check-models.sh docker/pull-models.sh scripts/install-offline.sh scripts/verify_airgap.sh > SHA256SUMS)
cat "$PAYLOAD/SHA256SUMS"

echo "== writing tarball"
tar -C "$STAGE" -cf "$OUT_DIR/$NAME.tar" "$NAME"
(cd "$OUT_DIR" && sha256 "$NAME.tar" > "$NAME.tar.sha256")
echo
echo "bundle:   $OUT_DIR/$NAME.tar"
echo "size:     $(du -h "$OUT_DIR/$NAME.tar" | cut -f1)"
echo "checksum: $(cut -d' ' -f1 "$OUT_DIR/$NAME.tar.sha256")"
echo "next:     copy the .tar and .tar.sha256 to the offline machine, then run scripts/install-offline.sh"
