#!/usr/bin/env bash
# Vendor the pinned upstream skills listed in skills.lock into .agents/skills/.
#   check (default): exit non-zero when a vendored skill differs from its pin.
#   sync:            replace each vendored skill with its pinned upstream copy.

set -euo pipefail

MODE="${1:-check}"
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_ROOT="$(cd "${APP_ROOT}/../.." && pwd)"
LOCK_FILE="${APP_ROOT}/skills.lock"
SKILLS_DIR="${APP_ROOT}/.agents/skills"
CACHE_ROOT="${AGENT_SKILLS_CACHE:-${BENCH_ROOT}/.cache/agent-skills}"

usage() {
    echo "Usage: scripts/sync-skills.sh [check|sync]" >&2
}

pinned_checkout() {
    local repository="$1"
    local revision="$2"
    local checkout="${CACHE_ROOT}/${repository}/${revision}"

    if [[ ! -d "${checkout}/.git" ]]; then
        local staging
        staging="$(mktemp -d "${TMPDIR:-/tmp}/agent-skills.XXXXXX")"
        git init -q "${staging}"
        git -C "${staging}" remote add origin "https://github.com/${repository}.git"
        git -C "${staging}" fetch -q --depth 1 origin "${revision}"
        git -C "${staging}" checkout -q --detach FETCH_HEAD
        mkdir -p "$(dirname "${checkout}")"
        rm -rf "${checkout}"
        mv "${staging}" "${checkout}"
    fi

    local checked_out
    checked_out="$(git -C "${checkout}" rev-parse HEAD)"
    if [[ "${checked_out}" != "${revision}" ]]; then
        echo "Expected ${repository} at ${revision}, found ${checked_out}." >&2
        exit 1
    fi

    printf '%s\n' "${checkout}"
}

stage_skill() {
    local name="$1" repository="$2" path="$3" revision="$4" excludes="$5"
    local checkout
    checkout="$(pinned_checkout "${repository}" "${revision}")"

    if [[ ! -d "${checkout}/${path}" ]]; then
        echo "${repository}@${revision} has no ${path}." >&2
        exit 1
    fi

    cp -R "${checkout}/${path}" "${STAGE_ROOT}/${name}"
    if [[ "${excludes}" != "-" ]]; then
        local exclude
        for exclude in ${excludes//,/ }; do
            rm -rf "${STAGE_ROOT:?}/${name}/${exclude}"
        done
    fi
}

process_skill() {
    local name="$1" repository="$2" path="$3" revision="$4" excludes="$5"

    if [[ ! "${revision}" =~ ^[0-9a-f]{40}$ ]]; then
        echo "skills.lock: ${name} needs a full 40-character revision." >&2
        exit 1
    fi

    stage_skill "${name}" "${repository}" "${path}" "${revision}" "${excludes}"
    local target="${SKILLS_DIR}/${name}"

    if [[ "${MODE}" == "sync" ]]; then
        rm -rf "${target}"
        cp -R "${STAGE_ROOT}/${name}" "${target}"
        echo "synced ${name} from ${repository}@${revision:0:12}"
    elif diff -r -x .DS_Store "${STAGE_ROOT}/${name}" "${target}" >/dev/null 2>&1; then
        echo "ok ${name} (${repository}@${revision:0:12})"
    else
        echo "drift ${name}: differs from ${repository}@${revision:0:12}" >&2
        diff -r -x .DS_Store "${STAGE_ROOT}/${name}" "${target}" >&2 || true
        DRIFT=1
    fi
}

case "${MODE}" in
    check | sync) ;;
    *)
        usage
        exit 2
        ;;
esac

STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/agent-skills-stage.XXXXXX")"
trap 'rm -rf "${STAGE_ROOT}"' EXIT
DRIFT=0

while read -r name repository path revision excludes; do
    [[ -z "${name}" || "${name}" == \#* ]] && continue
    process_skill "${name}" "${repository}" "${path}" "${revision}" "${excludes:--}"
done <"${LOCK_FILE}"

if [[ "${DRIFT}" -ne 0 ]]; then
    echo "Vendored skills drifted from skills.lock; run scripts/sync-skills.sh sync or update the lock." >&2
    exit 1
fi
