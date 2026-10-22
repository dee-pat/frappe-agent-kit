"""Validate bootstrap inputs and resolve immutable version defaults."""

import json
import re
import subprocess
from pathlib import Path

REQUIRED = {
    "app_name",
    "title",
    "description",
    "publisher",
    "email",
    "github_owner",
    "bench_path",
}
OPTIONAL = {
    "repo_name",
    "license",
    "module_name",
    "dev_site",
    "test_site",
    "kit_revision",
    "admin_password_env",
    "db_root_password_env",
    "db_root_username",
    "ci_timeout",
}
LICENSES = {
    "agpl-3.0",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "bsl-1.0",
    "cc0-1.0",
    "epl-2.0",
    "gpl-2.0",
    "gpl-3.0",
    "lgpl-2.1",
    "mit",
    "mpl-2.0",
    "unlicense",
}


def load_config(path, kit_root):
    """Read configuration without network access or filesystem mutation."""
    supplied = json.loads(Path(path).read_text())
    if not isinstance(supplied, dict):
        raise ValueError("Configuration must be a JSON object.")
    pins = json.loads(Path(__file__).with_name("versions.json").read_text())
    unknown = supplied.keys() - REQUIRED - OPTIONAL - pins.keys()
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    missing = REQUIRED - supplied.keys()
    if missing:
        raise ValueError(f"Missing configuration keys: {', '.join(sorted(missing))}")
    config = {**pins, **supplied}
    for key, value in config.items():
        if key != "ci_timeout" and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} must be a non-empty string.")
        if isinstance(value, str) and any(
            ord(char) < 32 or ord(char) == 127 for char in value
        ):
            raise ValueError(f"{key} contains a control character.")
    validate_identity(config)
    config.setdefault("repo_name", config["app_name"])
    config.setdefault("license", "mit")
    module = config["title"].lower().replace(" ", "_")
    if "module_name" in supplied and supplied["module_name"] != module:
        raise ValueError("module_name must match the scrubbed app title.")
    config["module_name"] = module
    prefix = config["app_name"].replace("_", "-")
    config.setdefault("dev_site", f"{prefix}-dev.localhost")
    config.setdefault("test_site", f"{prefix}-test.localhost")
    config.setdefault("admin_password_env", "FRAPPE_BOOTSTRAP_ADMIN_PASSWORD")
    config.setdefault("db_root_password_env", "FRAPPE_BOOTSTRAP_DB_ROOT_PASSWORD")
    config.setdefault("db_root_username", "root")
    config.setdefault("ci_timeout", 1800)
    if "kit_revision" not in config:
        config["kit_revision"] = subprocess.check_output(
            ["git", "-C", str(kit_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    validate_resolved(config)
    return config


def validate_identity(config):
    require_pattern(config, "app_name", r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
    require_pattern(config, "title", r"[A-Za-z][A-Za-z0-9_ ]*")
    require_pattern(
        config, "github_owner", r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    )
    require_pattern(config, "email", r"[^\s@]+@[^\s@]+\.[^\s@]+")
    bench = Path(config["bench_path"]).expanduser()
    if not bench.is_absolute():
        raise ValueError("bench_path must be absolute.")
    config["bench_path"] = str(bench.resolve())


def validate_resolved(config):
    require_pattern(config, "repo_name", r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
    if config["license"] not in LICENSES:
        raise ValueError("license must be a supported Frappe license identifier.")
    for key in ("dev_site", "test_site"):
        require_pattern(config, key, r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.localhost")
    if config["dev_site"] == config["test_site"]:
        raise ValueError("Development and test sites must be distinct.")
    for key in ("kit_revision", "skills_revision", "semgrep_revision"):
        require_pattern(config, key, r"[0-9a-f]{40}")
    require_pattern(config, "frappe_version", r"v16\.\d+\.\d+")
    for key in ("bench_version", "semgrep_version", "precommit_version"):
        require_pattern(config, key, r"\d+\.\d+\.\d+")
    require_pattern(config, "python_version", r"3\.14\.\d+")
    require_pattern(config, "node_version", r"\d+\.\d+\.\d+")
    for key in ("admin_password_env", "db_root_password_env"):
        require_pattern(config, key, r"[A-Z_][A-Z0-9_]*")
    require_pattern(config, "db_root_username", r"[A-Za-z_][A-Za-z0-9_-]*")
    timeout = config["ci_timeout"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("ci_timeout must be a positive integer.")


def require_pattern(config, key, pattern):
    if not re.fullmatch(pattern, config[key]):
        raise ValueError(f"Invalid {key}.")
