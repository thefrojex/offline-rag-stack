#!/bin/sh
# One-shot gate: fail fast, with a clear message, if the model volume is missing a model.
# Nothing is downloaded here; the stack has no network.
set -eu

missing=""
for model in $REQUIRED_MODELS; do
  case "$model" in *:*) wanted="$model" ;; *) wanted="$model:latest" ;; esac
  if ! ollama list | awk 'NR>1 {print $1}' | grep -qx "$wanted"; then
    missing="$missing $wanted"
  fi
done

if [ -n "$missing" ]; then
  echo "model-check: missing models:$missing" >&2
  echo "model-check: online machine -> run 'make pull-models'; offline machine -> run scripts/install-offline.sh" >&2
  exit 1
fi
echo "model-check: all required models present: $REQUIRED_MODELS"
