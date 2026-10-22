"""Render reproducible app guidance and workflow files without writing them."""

import re
from pathlib import Path, PurePosixPath

TOKENS = {
    "APP_NAME": "app_name",
    "APP_TITLE": "title",
    "MODULE_NAME": "module_name",
    "DEV_SITE": "dev_site",
    "TEST_SITE": "test_site",
    "FRAPPE_VERSION": "frappe_version",
    "BENCH_VERSION": "bench_version",
    "PYTHON_VERSION": "python_version",
    "NODE_VERSION": "node_version",
    "KIT_REVISION": "kit_revision",
    "SKILLS_REVISION": "skills_revision",
    "SEMGREP_REVISION": "semgrep_revision",
    "SEMGREP_VERSION": "semgrep_version",
    "PRECOMMIT_VERSION": "precommit_version",
}
KIT_TOOLS = (
    "sync-skills.sh",
    "semgrep-pr.sh",
    "test_deny_rules.py",
    "test_doc_links.py",
    "test_workflow_concurrency.py",
)
UPSTREAM_SKILLS = ("frappe-app-dev", "code-style", "frappe-code-review")
KIT_SKILLS = (
    "frappe-migration",
    "grilling",
    "pr-review-threads",
    "frappe-pr-review",
    "frappe-debugging",
    "frappe-spa-client",
)
UNRESOLVED = re.compile(r"__[A-Z][A-Z0-9_]*__")


def render(config: dict, kit_root: Path) -> dict[str, bytes]:
    """Return app-relative files; callers own collision checks and persistence."""
    values = dict(config)
    values.setdefault("module_name", str(values["title"]).lower().replace(" ", "_"))
    if not re.fullmatch(r"[a-z][a-z0-9_]*", values["app_name"]):
        raise ValueError("app_name must be a lowercase Python package name")
    for name in ("kit_revision", "skills_revision", "semgrep_revision"):
        if not re.fullmatch(r"[0-9a-f]{40}", values[name]):
            raise ValueError(f"{name} must be an immutable 40-character SHA")
    result = {}
    for source in sorted((kit_root / "templates/private-app").rglob("*")):
        if not source.is_file() or source.name == "versions.json":
            continue
        if source.is_symlink():
            raise ValueError(f"Template symlinks are not supported: {source}")
        target = substitute(
            source.relative_to(kit_root / "templates/private-app").as_posix(), values
        )
        path = PurePosixPath(target)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Rendered path escapes the app: {target}")
        result[target] = substitute(source.read_text(), values).encode()
    blocks = {
        "AGENTS.md": "rules/frappe.md",
        "docs/pull-requests.md": "templates/pull-requests.md",
        ".github/pull_request_template.md": "templates/pull_request_template.md",
    }
    for target, source in blocks.items():
        label = f"dee-pat/frappe-agent-kit/{source}"
        begin = f"<!-- BEGIN synced-rules: {label}@{values['kit_revision']} -->"
        end = f"<!-- END synced-rules: {label} -->"
        body = (kit_root / source).read_text().rstrip("\n") + "\n"
        text = result[target].decode()
        pattern = re.escape(begin) + r"\n.*?" + re.escape(end)
        replacement = begin + "\n" + body + end
        text, count = re.subn(
            pattern, lambda _, value=replacement: value, text, flags=re.S
        )
        if count != 1:
            raise ValueError(f"Expected one managed rules block in {target}")
        result[target] = text.encode()
    result["skills.lock"] = skill_lock(values).encode()
    for name in KIT_TOOLS:
        result[f"scripts/{name}"] = (kit_root / "tools" / name).read_bytes()
    return result


def substitute(text: str, values: dict) -> str:
    for token, key in TOKENS.items():
        value = str(values[key])
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} must be a single-line value")
        text = text.replace(f"__{token}__", value)
    if unresolved := UNRESOLVED.search(text):
        raise ValueError(f"Unresolved bootstrap template token: {unresolved[0]}")
    return text


def skill_lock(config: dict) -> str:
    lines = [
        "# Immutable upstream pins. Update deliberately, then run scripts/sync-skills.sh sync.",
        "# Vendored kit tools are copied unchanged from the same kit revision.",
    ]
    for name in UPSTREAM_SKILLS:
        lines.append(
            f"{name} frappe/skills skills/{name} {config['skills_revision']} -"
        )
    for name in KIT_SKILLS:
        lines.append(
            f"{name} dee-pat/frappe-agent-kit skills/{name} {config['kit_revision']} -"
        )
    lines.extend(
        [
            f"rule dee-pat/frappe-agent-kit rules/frappe.md {config['kit_revision']} AGENTS.md",
            f"vendor frappe/semgrep-rules rules {config['semgrep_revision']} semgrep/frappe",
            f"vendor dee-pat/frappe-agent-kit semgrep/kit {config['kit_revision']} semgrep/kit",
            f"rule dee-pat/frappe-agent-kit templates/pull-requests.md {config['kit_revision']} docs/pull-requests.md",
            f"rule dee-pat/frappe-agent-kit templates/pull_request_template.md {config['kit_revision']} .github/pull_request_template.md",
        ]
    )
    return "\n".join(lines) + "\n"
