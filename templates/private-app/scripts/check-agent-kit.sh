#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
scripts/sync-skills.sh check
python3 scripts/test_deny_rules.py
python3 scripts/test_doc_links.py
python3 scripts/test_workflow_concurrency.py
python3 scripts/test_merge_safeguards.py
python3 scripts/test_merge_checkout.py
python3 scripts/test_merge_ci.py
python3 scripts/test_merge_workflow.py
