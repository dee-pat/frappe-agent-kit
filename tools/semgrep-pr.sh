#!/usr/bin/env bash
# Report the Semgrep findings a change introduces, using Frappe's rules.
# Canonical copy: https://github.com/dee-pat/frappe-agent-kit/blob/main/tools/semgrep-pr.sh
#
# Usage: scripts/semgrep-pr.sh [--fail-on-new] [--json FILE] BASE [HEAD]
#   BASE  the PR's base branch or commit; findings already present at the merge
#         base of BASE and HEAD are existing debt and are not reported.
#   HEAD  the commit under review (default: HEAD). Uncommitted changes are not
#         scanned; commit them or scan the files directly.
#   --fail-on-new  exit 1 when the change introduces a finding. Without it the
#                  script only reports and exits 0.
#   --json FILE    also write Semgrep's JSON output to FILE.
#
# The scan runs in a temporary shared clone, so the checkout, its index and
# its uncommitted changes are never touched. Rules come from
# FRAPPE_SEMGREP_RULES (default: semgrep/frappe, vendored by sync-skills.sh);
# Semgrep from SEMGREP_BIN, PATH, or the bench's env/bin/semgrep.

set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_ROOT="$(cd "${APP_ROOT}/../.." && pwd)"
RULES="${FRAPPE_SEMGREP_RULES:-${APP_ROOT}/semgrep/frappe}"

usage() {
    echo "Usage: scripts/semgrep-pr.sh [--fail-on-new] [--json FILE] BASE [HEAD]" >&2
}

FAIL_ON_NEW=0
JSON_COPY=""
while (($#)); do
    case "$1" in
        --fail-on-new) FAIL_ON_NEW=1 ;;
        --json)
            [[ $# -ge 2 ]] || {
                usage
                exit 2
            }
            JSON_COPY="$2"
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*)
            usage
            exit 2
            ;;
        *) break ;;
    esac
    shift
done
if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 2
fi

semgrep_binary() {
    local binary="${SEMGREP_BIN:-}"
    if [[ -z "${binary}" ]] && command -v semgrep >/dev/null 2>&1; then
        binary="$(command -v semgrep)"
    fi
    if [[ -z "${binary}" && -x "${BENCH_ROOT}/env/bin/semgrep" ]]; then
        binary="${BENCH_ROOT}/env/bin/semgrep"
    fi
    if [[ -z "${binary}" || ! -x "${binary}" ]]; then
        echo "Semgrep is unavailable; run 'bench setup requirements --dev' or set SEMGREP_BIN." >&2
        exit 1
    fi
    printf '%s\n' "${binary}"
}

resolve() {
    git -C "${APP_ROOT}" rev-parse --verify --quiet "$1^{commit}" || {
        echo "Unknown revision: $1" >&2
        exit 2
    }
}

if [[ ! -d "${RULES}" ]]; then
    echo "No Frappe Semgrep rules at ${RULES}; vendor them with sync-skills.sh or set FRAPPE_SEMGREP_RULES." >&2
    exit 1
fi
RULES="$(cd "${RULES}" && pwd)"
SEMGREP="$(semgrep_binary)"
# Command substitution does not propagate exit from resolve, so assign
# separately: set -e then stops on a failed assignment.
HEAD_SHA="$(resolve "${2:-HEAD}")"
BASE_REF_SHA="$(resolve "$1")"
BASE_SHA="$(git -C "${APP_ROOT}" merge-base "${BASE_REF_SHA}" "${HEAD_SHA}")"

if [[ "${2:-HEAD}" == "HEAD" && -n "$(git -C "${APP_ROOT}" status --porcelain --untracked-files=no)" ]]; then
    echo "Note: uncommitted changes are not scanned; this reports ${HEAD_SHA:0:12} only." >&2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/semgrep-pr.XXXXXX")"
trap 'rm -rf "${WORK}"' EXIT
git clone -q --shared --no-checkout "${APP_ROOT}" "${WORK}/repo"
git -C "${WORK}/repo" checkout -q --detach "${HEAD_SHA}"

echo "Frappe Semgrep: findings introduced by ${BASE_SHA:0:12}..${HEAD_SHA:0:12} ($("${SEMGREP}" --version 2>/dev/null | tail -1))"
status=0
(
    cd "${WORK}/repo"
    # semgrep/ holds rules and fixtures with deliberate findings, not app code.
    "${SEMGREP}" scan \
        --quiet \
        --metrics=off \
        --disable-version-check \
        --config "${RULES}" \
        --baseline-commit "${BASE_SHA}" \
        --exclude semgrep \
        --exclude node_modules \
        --exclude .agents \
        --json-output "${WORK}/results.json" \
        .
) || status=$?
if [[ "${status}" -ne 0 ]]; then
    echo "Semgrep failed with status ${status}." >&2
    exit "${status}"
fi

[[ -n "${JSON_COPY}" ]] && cp "${WORK}/results.json" "${JSON_COPY}"
new_findings="$(python3 -I -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["results"]))' "${WORK}/results.json")"
echo "${new_findings} new finding(s); findings already present at ${BASE_SHA:0:12} are not shown."
if [[ "${FAIL_ON_NEW}" -eq 1 && "${new_findings}" -gt 0 ]]; then
    exit 1
fi
