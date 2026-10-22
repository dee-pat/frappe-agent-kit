#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -n "$(git config --get core.hooksPath || true)" ]]; then
  echo "core.hooksPath is configured; integrate .githooks/pre-push with your existing hooks." >&2
  exit 1
fi

target="$(git rev-parse --git-path hooks/pre-push)"
if [[ -e "$target" || -L "$target" ]]; then
  if ! cmp -s .githooks/pre-push "$target"; then
    echo "Existing pre-push hook preserved; integrate .githooks/pre-push manually." >&2
    exit 1
  fi
fi
cp .githooks/pre-push "$target"
chmod +x "$target"
echo "Installed pre-push safeguard. Direct updates to main are blocked."
