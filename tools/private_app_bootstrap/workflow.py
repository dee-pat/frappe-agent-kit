"""Orchestrate journaled private-app bootstrap phases."""

import os
import platform
import shutil
from pathlib import Path

from .commands import Commands
from .local import LocalSetup
from .publish import Publisher
from .state import Journal

PHASES = (
    "bench",
    "app",
    "sites",
    "repository",
    "configure",
    "checks",
    "pull_request",
    "merge",
    "verify",
)


class Bootstrap:
    def __init__(self, config, kit_root):
        self.c, self.kit = config, Path(kit_root)
        self.j = Journal(config)
        self.cmd = Commands(config, self.j)
        self.local = LocalSetup(config, self.j, self.cmd, self.kit)
        self.publisher = Publisher(config, self.j, self.cmd, self.local)

    def plan(self):
        print(f"Private app: {self.c['github_owner']}/{self.c['repo_name']}")
        print(f"Bench: {self.c['bench_path']}; app: {self.local.app}")
        print(f"Sites: {self.c['dev_site']} and {self.c['test_site']}")
        print(
            f"Pins: Frappe {self.c['frappe_version']}, bench {self.c['bench_version']}, kit {self.c['kit_revision']}"
        )
        print(f"Journal: {self.j.path}")
        for phase in PHASES:
            print(f"  {phase}")
        print("Dry-run: no files, network requests or external resources changed.")

    def run(self, resume=False):
        self.preflight(resume)
        actions = {
            "bench": self.local.bench_setup,
            "app": self.local.scaffold,
            "sites": self.local.sites,
            "repository": self.publisher.repository,
            "configure": self.local.configure,
            "checks": self.local.checks,
            "pull_request": self.publisher.pull_request,
            "merge": self.publisher.merge,
            "verify": self.publisher.verify_final,
        }
        with self.j.acquire(resume=resume):
            for phase in PHASES:
                if self.j.done(phase):
                    self.revalidate(phase)
                    continue
                print(f"Bootstrap phase: {phase}", flush=True)
                self.j.start(phase)
                actions[phase]()
                self.j.complete(phase)
        print(
            f"Private app bootstrap complete: https://github.com/{self.publisher.repo}"
        )

    def preflight(self, resume):
        if platform.python_version() != self.c["python_version"]:
            raise ValueError("Run the tool with the pinned Python version.")
        if (
            self.cmd.run(["git", "rev-parse", "HEAD"], cwd=self.kit).stdout.strip()
            != self.c["kit_revision"]
        ):
            raise ValueError("Kit checkout must match kit_revision exactly.")
        if self.cmd.run(["git", "status", "--porcelain"], cwd=self.kit).stdout:
            raise ValueError(
                "Commit the kit changes or use a clean pinned checkout before applying."
            )
        for name in ("git", "gh", "node", "yarn", "redis-server", "redis-cli"):
            if not shutil.which(name):
                raise ValueError(f"Missing prerequisite: {name}.")
        if (
            self.cmd.run(["node", "--version"]).stdout.strip()
            != f"v{self.c['node_version']}"
        ):
            raise ValueError("Node version does not match the configured pin.")
        if self.cmd.run(["yarn", "--version"]).stdout.strip() != "1.22.22":
            raise ValueError("Yarn 1.22.22 is required.")
        if os.environ.get("GH_HOST", "github.com") != "github.com":
            raise ValueError("This bootstrap supports github.com only; unset GH_HOST.")
        self.cmd.run(["gh", "auth", "status"])
        self.cmd.json(
            [
                "gh",
                "api",
                f"repos/dee-pat/frappe-agent-kit/git/commits/{self.c['kit_revision']}",
            ]
        )
        if (
            self.kit == self.local.bench
            or self.kit in self.local.bench.parents
            or self.local.bench in self.kit.parents
        ):
            raise ValueError("Bench and kit checkout paths must not overlap.")
        if not os.environ.get(self.c["admin_password_env"]):
            raise ValueError(
                f"Set {self.c['admin_password_env']} before applying; its value is never journaled."
            )
        if not Path(self.c["bench_path"]).parent.is_dir():
            raise ValueError("Bench parent directory must exist.")
        if not resume:
            conflicts = [self.local.app] + [
                self.local.bench / "sites" / self.c[key]
                for key in ("dev_site", "test_site")
            ]
            if any(path.exists() or path.is_symlink() for path in conflicts):
                raise ValueError(
                    "An app or site target already exists; no existing resources were adopted."
                )
            existing = self.cmd.run(
                ["gh", "api", f"repos/{self.publisher.repo}"], check=False
            )
            if existing.returncode == 0 or "404" not in existing.stderr:
                raise ValueError(
                    "Cannot establish an absent GitHub repository; no repository was adopted."
                )

    def revalidate(self, phase):
        if phase == "bench":
            self.local.verify_bench()
            self.local.redis()
        elif phase == "app":
            self.local.verify_app()
        elif phase == "sites":
            self.local.verify_sites()
        elif phase == "configure":
            self.local.verify_configured()
        elif phase in ("repository", "pull_request", "merge", "verify"):
            self.publisher.verify_repository()
            self.publisher.verify_origin()
        if phase == "merge":
            # Re-read exact main CI even if the prior run completed before a crash.
            self.publisher.merge()
            self.publisher.verify_final()
