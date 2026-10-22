"""Create and revalidate bootstrap-owned local Frappe resources."""

import hashlib
import os
import re
import sys
from pathlib import Path

import tomllib

from .files import ManagedFiles
from .render import render


class LocalSetup:
    def __init__(self, config, journal, commands, kit_root):
        self.c, self.j, self.cmd = config, journal, commands
        self.kit = kit_root
        self.bench = Path(config["bench_path"])
        self.app = self.bench / "apps" / config["app_name"]
        self.files = ManagedFiles(self.app, self.bench, self.j)

    def bench_setup(self):
        c = self.c
        runtime = self.cmd.runtime
        if runtime.is_symlink():
            raise ValueError("Bootstrap runtime must not be a symlink.")
        if not (runtime / "bin/python").exists():
            self.cmd.run([sys.executable, "-m", "venv", runtime])
        self.cmd.run(
            [
                runtime / "bin/python",
                "-m",
                "pip",
                "install",
                f"frappe-bench=={c['bench_version']}",
            ]
        )
        if not self.bench.exists():
            self.j.data["resources"]["bench"] = True
            self.j.save()
            self.cmd.run(
                [
                    "bench",
                    "init",
                    "--frappe-branch",
                    c["frappe_version"],
                    "--skip-assets",
                    "--python",
                    sys.executable,
                    self.bench,
                ],
                cwd=self.bench.parent,
            )
        self.verify_bench()
        self.redis()

    def verify_bench(self):
        if not all(
            (self.bench / name).exists()
            for name in ("apps/frappe", "sites", "env/bin/python", "Procfile")
        ):
            raise ValueError(
                "Bench is incomplete; inspect it before resuming. No files were removed."
            )
        source = self.bench / "apps/frappe"
        head = self.cmd.run(["git", "rev-parse", "HEAD"], cwd=source).stdout.strip()
        pinned = self.cmd.run(
            ["git", "rev-parse", f"{self.c['frappe_version']}^{{commit}}"], cwd=source
        ).stdout.strip()
        if (
            head != pinned
            or self.cmd.run(["git", "status", "--porcelain"], cwd=source).stdout
        ):
            raise ValueError(
                "Existing Frappe checkout must be clean and match the exact configured tag."
            )

    def redis(self):
        for name in ("cache", "queue"):
            config = self.bench / f"config/redis_{name}.conf"
            match = re.search(r"^port\s+(\d+)$", config.read_text(), re.M)
            if not match:
                raise ValueError(f"Missing Redis port in {config}.")
            result = self.cmd.run(
                ["redis-cli", "-h", "127.0.0.1", "-p", match[1], "ping"], check=False
            )
            if result.returncode:
                self.cmd.run(
                    [
                        "redis-server",
                        config,
                        "--daemonize",
                        "yes",
                        "--logfile",
                        self.bench / f"logs/redis-{name}.log",
                    ],
                    cwd=self.bench,
                )
                self.cmd.run(["redis-cli", "-h", "127.0.0.1", "-p", match[1], "ping"])

    def scaffold(self):
        self.require_resource_path(self.app)
        if not self.app.exists():
            self.j.data["resources"]["app"] = True
            self.j.save()
            self.cmd.new_app()
        elif not self.j.data["resources"].get("app"):
            raise ValueError("Existing app is not owned by this bootstrap.")
        self.verify_app()
        resources = self.j.data["resources"]
        if not resources.get("scaffold_commit"):
            count = self.cmd.run(
                ["git", "rev-list", "--count", "HEAD"], cwd=self.app
            ).stdout.strip()
            dirty = self.cmd.run(["git", "status", "--porcelain"], cwd=self.app).stdout
            if count != "1" or dirty:
                raise ValueError(
                    "Unrecorded scaffold has user changes; inspect before resuming."
                )
            resources["scaffold_commit"] = self.cmd.run(
                ["git", "rev-parse", "HEAD"], cwd=self.app
            ).stdout.strip()
            self.j.save()
        self.cmd.run(["bench", "pip", "install", "-e", str(self.app)], cwd=self.bench)
        self.cmd.run(["bench", "build", "--app", self.c["app_name"]], cwd=self.bench)

    def verify_app(self):
        self.require_resource_path(self.app)
        project = tomllib.loads((self.app / "pyproject.toml").read_text())
        if (
            project["project"]["name"] != self.c["app_name"]
            or not (self.app / ".git").exists()
        ):
            raise ValueError(
                "App scaffold identity does not match the bootstrap journal."
            )

    def sites(self):
        for key in ("dev_site", "test_site"):
            site = self.c[key]
            path = self.bench / "sites" / site
            self.require_resource_path(path)
            claim = f"site:{site}"
            if not path.exists():
                self.j.data["resources"][claim] = True
                self.j.save()
                args = [
                    "bench",
                    "new-site",
                    site,
                    "--db-root-username",
                    self.c["db_root_username"],
                    "--admin-password",
                    os.environ[self.c["admin_password_env"]],
                ]
                password = os.environ.get(self.c["db_root_password_env"])
                if password:
                    args.extend(["--db-root-password", password])
                self.cmd.run(args, cwd=self.bench, input_text="\n")
            elif not self.j.data["resources"].get(claim):
                raise ValueError(
                    f"Existing site {site} is not owned by this bootstrap."
                )
            installed = self.site_apps(site)
            if self.c["app_name"] not in installed:
                self.cmd.run(
                    ["bench", "--site", site, "install-app", self.c["app_name"]],
                    cwd=self.bench,
                )
            flag = "developer_mode" if key == "dev_site" else "allow_tests"
            self.cmd.run(
                ["bench", "--site", site, "set-config", flag, "true"], cwd=self.bench
            )
            self.cmd.run(["bench", "--site", site, "migrate"], cwd=self.bench)
        self.verify_sites()

    def site_apps(self, site):
        self.require_resource_path(self.bench / "sites" / site)
        return self.cmd.json(
            ["bench", "--site", site, "list-apps", "--format", "json"], cwd=self.bench
        )[site]

    def verify_sites(self):
        for key in ("dev_site", "test_site"):
            if self.c["app_name"] not in self.site_apps(self.c[key]):
                raise ValueError(
                    "Completed site installation no longer matches the journal."
                )

    def configure(self):
        branch = "codex/bootstrap-private-app"
        current = self.cmd.run(
            ["git", "branch", "--show-current"], cwd=self.app
        ).stdout.strip()
        if not self.j.data["resources"].get("setup_branch"):
            if self.cmd.run(["git", "status", "--porcelain"], cwd=self.app).stdout:
                raise ValueError(
                    "App has user changes before configuration; nothing was overwritten."
                )
            exists = self.cmd.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                cwd=self.app,
                check=False,
            )
            if exists.returncode == 0:
                raise ValueError(
                    "Setup branch already exists without recorded ownership."
                )
            self.j.data["resources"]["setup_branch"] = branch
            self.j.save()
        if current != branch:
            exists = self.cmd.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                cwd=self.app,
                check=False,
            )
            self.cmd.run(
                ["git", "switch", branch]
                if exists.returncode == 0
                else ["git", "switch", "-c", branch],
                cwd=self.app,
            )
        outputs = render(self.c, self.kit)
        hooks = self.app / self.c["app_name"] / "hooks.py"
        outputs[f"{self.c['app_name']}/hooks.py"] = (
            hooks.read_text().rstrip() + "\n"
        ).encode()
        if not self.j.data["files"]:
            for relative, content in outputs.items():
                target = self.safe_target(relative)
                self.j.data["files"][relative] = {
                    "before": hashlib.sha256(target.read_bytes()).hexdigest()
                    if target.exists()
                    else None,
                    "after": hashlib.sha256(content).hexdigest(),
                }
            self.j.save()
        for relative, content in outputs.items():
            self.write_managed(relative, content)
        self.cmd.run(["bash", "scripts/sync-skills.sh", "sync"], cwd=self.app)
        self.cmd.run(["bash", "scripts/install-hooks.sh"], cwd=self.app)
        link = self.app / ".claude/skills"
        if link.is_symlink():
            if link.readlink().as_posix() != "../.agents/skills":
                raise ValueError("Existing Claude skills link points elsewhere.")
        elif link.exists():
            raise ValueError("Existing Claude skills directory was preserved.")
        else:
            link.symlink_to("../.agents/skills", target_is_directory=True)
        paths = [*outputs, ".agents", "semgrep", ".claude/skills"]
        self.cmd.run(["git", "add", "--", *paths], cwd=self.app)

    def write_managed(self, relative, content):
        self.files.write_managed(relative, content)

    def require_resource_path(self, target):
        self.files.require_resource_path(target)

    def safe_target(self, relative):
        return self.files.safe_target(relative)

    def verify_configured(self):
        self.files.verify_configured()
        self.cmd.run(["bash", "scripts/sync-skills.sh", "check"], cwd=self.app)

    def checks(self):
        c = self.c
        self.cmd.run(
            [
                "bench",
                "pip",
                "install",
                f"pre-commit=={c['precommit_version']}",
                f"semgrep=={c['semgrep_version']}",
            ],
            cwd=self.bench,
        )
        self.cmd.run(["bash", "scripts/lint.sh"], cwd=self.app)
        self.cmd.run(
            ["bench", "--site", c["test_site"], "run-tests", "--app", c["app_name"]],
            cwd=self.bench,
        )
