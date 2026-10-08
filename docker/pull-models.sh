#!/bin/sh
# Online-only helper (compose profile `online`): starts a throwaway Ollama server on the
# shared model volume, pulls the requested models, and exits. The main stack never runs this.
set -eu

ollama serve >/tmp/ollama.log 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  ollama list >/dev/null 2>&1 && break
  sleep 1
done

for model in $PULL_MODELS; do
  echo "pulling $model"
  ollama pull "$model"
done
ollama list
