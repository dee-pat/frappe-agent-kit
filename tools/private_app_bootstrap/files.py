"""Persist generated files without overwriting user changes or following links."""

import hashlib
import os
import tempfile
from pathlib import Path


class ManagedFiles:
    def __init__(self, app, bench, journal):
        self.app, self.bench, self.j = app, bench, journal

    def write_managed(self, relative, content):
        target = self.safe_target(relative)
        after = hashlib.sha256(content).hexdigest()
        before = (
            hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        )
        recorded = self.j.data["files"].get(relative)
        if recorded and (
            recorded["after"] != after or before not in (recorded["before"], after)
        ):
            raise ValueError(
                f"Generated file changed: {relative}. Inspect before resuming."
            )
        if not recorded:
            self.j.data["files"][relative] = {"before": before, "after": after}
            self.j.save()
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.bootstrap-", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        if relative.startswith("scripts/") or relative == ".githooks/pre-push":
            target.chmod(0o755)

    def require_resource_path(self, target):
        for parent in (target, *target.parents):
            if parent.is_symlink():
                raise ValueError(f"Resource path must not contain symlinks: {target}.")
            if parent == self.bench:
                break

    def safe_target(self, relative):
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Managed path must stay within the app.")
        target = self.app / path
        self.require_resource_path(self.app)
        for parent in (target, *target.parents):
            if parent.is_symlink():
                raise ValueError(f"Refusing symlink in managed path: {relative}.")
            if parent == self.app:
                break
        if not target.resolve().is_relative_to(self.app.resolve()):
            raise ValueError("Managed path escapes the app.")
        return target

    def verify_configured(self):
        link = self.app / ".claude/skills"
        if not link.is_symlink() or link.readlink().as_posix() != "../.agents/skills":
            raise ValueError("Generated Claude skills link changed.")
        for relative, hashes in self.j.data["files"].items():
            target = self.safe_target(relative)
            if (
                target.is_symlink()
                or not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != hashes["after"]
            ):
                raise ValueError(f"Generated file changed: {relative}.")
