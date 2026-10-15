#!/usr/bin/env bash
# Vendor the pinned skills and rules listed in skills.lock.
# Canonical copy: https://github.com/dee-pat/frappe-agent-kit/blob/main/tools/sync-skills.sh
#   check (default): exit non-zero when a vendored copy differs from its pin.
#   sync:            replace each vendored copy with its pinned upstream version.
#
# skills.lock lines:
#   <skill-name> <owner/repo> <path> <revision> <excludes or ->
#     copies <path> into .agents/skills/<skill-name>/, minus excludes.
#   rule <owner/repo> <path> <revision> <target>
#     writes the file at <path> into <target> between the markers
#     <!-- BEGIN synced-rules: <owner/repo>/<path>@<revision> -->
#     <!-- END synced-rules: <owner/repo>/<path> -->
#     which must already exist once each in <target>.

set -euo pipefail

MODE="${1:-check}"
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_ROOT="$(cd "${APP_ROOT}/../.." && pwd)"
LOCK_FILE="${APP_ROOT}/skills.lock"
SKILLS_DIR="${APP_ROOT}/.agents/skills"
CACHE_ROOT="${AGENT_SKILLS_CACHE:-${BENCH_ROOT}/.cache/agent-skills}"
REMOTE_BASE="${AGENT_SKILLS_REMOTE_BASE:-https://github.com}"
LOCK_TIMEOUT="${AGENT_SKILLS_LOCK_TIMEOUT:-120}"

usage() {
    echo "Usage: scripts/sync-skills.sh [check|sync]" >&2
}

cache_holds() {
    git --git-dir="$1/.git" cat-file -e "$2^{commit}" 2>/dev/null
}

pinned_checkout() {
    local repository="$1"
    local revision="$2"
    local checkout="${CACHE_ROOT}/${repository}/${revision}"

    # Callers run this in a command substitution, which does not inherit
    # errexit, so every step checks its own result. Files are later read from
    # the commit object, never the worktree, so local edits inside the cache
    # cannot leak into vendored copies.
    if cache_holds "${checkout}" "${revision}"; then
        printf '%s\n' "${checkout}"
        return 0
    fi

    # Stage beside the entry so publishing is a same-filesystem rename, and
    # fetch outside the lock so concurrent runs do not wait on the network.
    local parent staging lock="${checkout}.lock"
    parent="$(dirname "${checkout}")"
    mkdir -p "${parent}" || return 1
    staging="$(mktemp -d "${parent}/.staging.XXXXXX")" || return 1
    # Clean up explicitly on every path: bash 3.2 does not run an EXIT trap set
    # inside a command substitution.
    if ! git init -q "${staging}" ||
        ! git -C "${staging}" remote add origin "${REMOTE_BASE}/${repository}.git" ||
        ! git -C "${staging}" fetch -q --depth 1 origin "${revision}" ||
        ! cache_holds "${staging}" "${revision}"; then
        rm -rf "${staging}"
        echo "Could not fetch ${repository} at ${revision}; nothing was cached." >&2
        return 1
    fi

    # Publish under a lock and recheck first: another run may have published a
    # valid entry while this one fetched, and that entry may be in use. Only an
    # invalid entry is ever removed.
    local waited=0
    until mkdir "${lock}" 2>/dev/null; do
        if ((waited >= LOCK_TIMEOUT * 10)); then
            rm -rf "${staging}"
            echo "Timed out waiting for ${lock}; remove it if no sync is running." >&2
            return 1
        fi
        sleep 0.1
        waited=$((waited + 1))
    done
    if ! cache_holds "${checkout}" "${revision}"; then
        if ! rm -rf "${checkout}" || ! mv "${staging}" "${checkout}"; then
            rm -rf "${staging}"
            rmdir "${lock}"
            echo "Could not cache ${repository} at ${checkout}." >&2
            return 1
        fi
    fi
    rm -rf "${staging}"
    rmdir "${lock}"

    printf '%s\n' "${checkout}"
}

stage_skill() {
    local name="$1" repository="$2" path="$3" revision="$4" excludes="$5"
    local checkout
    checkout="$(pinned_checkout "${repository}" "${revision}")"

    local git_dir="${checkout}/.git"
    if [[ "$(git --git-dir="${git_dir}" cat-file -t "${revision}:${path}" 2>/dev/null)" != "tree" ]]; then
        echo "${repository}@${revision} has no ${path}." >&2
        exit 1
    fi

    mkdir "${STAGE_ROOT}/${name}"
    git --git-dir="${git_dir}" archive --format=tar "${revision}:${path}" |
        tar -x -f - -C "${STAGE_ROOT}/${name}"
    if [[ "${excludes}" != "-" ]]; then
        local exclude
        for exclude in ${excludes//,/ }; do
            rm -rf "${STAGE_ROOT:?}/${name}/${exclude}"
        done
    fi
}

require_revision() {
    if [[ ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
        echo "skills.lock: $1 needs a full 40-character revision." >&2
        exit 1
    fi
}

render_rules() {
    local target="$1" source="$2" label="$3" revision="$4" output="$5"

    awk -v begin_prefix="<!-- BEGIN synced-rules: ${label}@" \
        -v begin_line="<!-- BEGIN synced-rules: ${label}@${revision} -->" \
        -v end_line="<!-- END synced-rules: ${label} -->" \
        -v source="${source}" '
        index($0, begin_prefix) == 1 {
            begins++
            if (inside) broken = 1
            print begin_line
            while ((getline line < source) > 0) print line
            close(source)
            inside = 1
            next
        }
        $0 == end_line {
            ends++
            if (!inside) broken = 1
            inside = 0
            print
            next
        }
        !inside { print }
        END { if (begins != 1 || ends != 1 || inside || broken) exit 3 }
    ' "${target}" >"${output}"
}

process_rule() {
    local repository="$1" path="$2" revision="$3" target="$4"
    local label="${repository}/${path}"

    require_revision "rule ${label}" "${revision}"
    if [[ "${target}" == "-" || "${target}" == /* || "${target}" == *..* ]]; then
        echo "skills.lock: rule ${label} needs a target path inside the app." >&2
        exit 1
    fi

    local checkout
    checkout="$(pinned_checkout "${repository}" "${revision}")"
    local git_dir="${checkout}/.git"
    if [[ "$(git --git-dir="${git_dir}" cat-file -t "${revision}:${path}" 2>/dev/null)" != "blob" ]]; then
        echo "${repository}@${revision} has no ${path}." >&2
        exit 1
    fi

    local stem="${STAGE_ROOT}/rule-$(printf '%s' "${label}" | tr '/' '_')"
    local source="${stem}.source"
    local rendered="${stem}.rendered"
    git --git-dir="${git_dir}" cat-file blob "${revision}:${path}" >"${source}"

    local target_file="${APP_ROOT}/${target}"
    if [[ ! -f "${target_file}" ]] ||
        ! render_rules "${target_file}" "${source}" "${label}" "${revision}" "${rendered}"; then
        echo "${target} needs exactly one BEGIN/END synced-rules marker pair for ${label}." >&2
        exit 1
    fi

    if [[ "${MODE}" == "sync" ]]; then
        cat "${rendered}" >"${target_file}"
        echo "synced rules ${label} into ${target} at ${revision:0:12}"
    elif cmp -s "${rendered}" "${target_file}"; then
        echo "ok rules ${label} in ${target} (${revision:0:12})"
    else
        echo "drift rules ${label}: ${target} differs from ${repository}@${revision:0:12}" >&2
        diff "${rendered}" "${target_file}" >&2 || true
        DRIFT=1
    fi
}

process_skill() {
    local name="$1" repository="$2" path="$3" revision="$4" excludes="$5"

    require_revision "${name}" "${revision}"
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
    if [[ "${name}" == "rule" ]]; then
        process_rule "${repository}" "${path}" "${revision}" "${excludes:--}"
    else
        process_skill "${name}" "${repository}" "${path}" "${revision}" "${excludes:--}"
    fi
done <"${LOCK_FILE}"

if [[ "${DRIFT}" -ne 0 ]]; then
    echo "Vendored copies drifted from skills.lock; run scripts/sync-skills.sh sync or update the lock." >&2
    exit 1
fi
