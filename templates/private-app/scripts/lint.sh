#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
pre-commit run --all-files
semgrep scan --error --metrics=off --severity ERROR \
  --config semgrep/frappe --config semgrep/kit \
  --exclude .agents --exclude .claude --exclude semgrep
