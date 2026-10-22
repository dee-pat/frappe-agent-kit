"""Publish a bootstrap-owned private repository and setup pull request."""

import tempfile

from .pr_ci import PullRequestCI
from .setup_commit import SetupCommit


class Publisher:
    def __init__(self, config, journal, commands, local):
        self.c, self.j, self.cmd, self.local = config, journal, commands, local
        self.repo = f"{config['github_owner']}/{config['repo_name']}"
        self.app = local.app

    def repository(self):
        resource = self.j.data["resources"]
        if resource.get("scaffold_commit"):
            head = self.cmd.run(
                ["git", "rev-parse", "HEAD"], cwd=self.app
            ).stdout.strip()
            if (
                head != resource["scaffold_commit"]
                or self.cmd.run(["git", "status", "--porcelain"], cwd=self.app).stdout
            ):
                raise ValueError(
                    "Scaffold changed before private publication; changes were preserved."
                )
        if not resource.get("repository_id"):
            existing = self.cmd.run(["gh", "api", f"repos/{self.repo}"], check=False)
            if existing.returncode == 0:
                raise ValueError(
                    "Repository already exists without recorded ownership; inspect manually."
                )
            if "404" not in existing.stderr:
                raise ValueError(
                    self.cmd.redact(
                        f"Cannot establish repository absence: {existing.stderr}"
                    )
                )
            login = self.cmd.json(["gh", "api", "user"])["login"]
            endpoint = (
                "user/repos"
                if login.lower() == self.c["github_owner"].lower()
                else f"orgs/{self.c['github_owner']}/repos"
            )
            created = self.cmd.json(
                [
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    endpoint,
                    "-f",
                    f"name={self.c['repo_name']}",
                    "-F",
                    "private=true",
                    "-f",
                    f"description={self.c['description']}",
                ]
            )
            resource["repository_id"] = created["id"]
            self.j.save()
        metadata = self.verify_repository()
        remotes = self.cmd.run(["git", "remote"], cwd=self.app).stdout.splitlines()
        if "origin" not in remotes:
            self.cmd.run(
                ["git", "remote", "add", "origin", metadata["clone_url"]], cwd=self.app
            )
        self.verify_origin()
        initial = resource.setdefault(
            "initial_commit",
            self.cmd.run(["git", "rev-parse", "HEAD"], cwd=self.app).stdout.strip(),
        )
        self.j.save()
        remote = self.cmd.run(
            ["git", "ls-remote", "--heads", "origin", "refs/heads/main"], cwd=self.app
        ).stdout.strip()
        if not remote:
            self.cmd.run(
                ["git", "push", "-u", "origin", f"{initial}:refs/heads/main"],
                cwd=self.app,
            )
        elif remote.split()[0] != initial:
            raise ValueError("Initial main differs from the bootstrap scaffold commit.")
        self.cmd.run(
            ["git", "branch", "--set-upstream-to", "origin/main", "main"], cwd=self.app
        )
        self.cmd.run(["gh", "repo", "edit", self.repo, "--default-branch", "main"])

    def verify_repository(self):
        metadata = self.cmd.json(["gh", "api", f"repos/{self.repo}"])
        if not metadata["private"] or metadata["id"] != self.j.data["resources"].get(
            "repository_id"
        ):
            raise ValueError(
                "Repository is not private or its identity differs from the journal."
            )
        return metadata

    def verify_origin(self):
        for flags in ([], ["--push"]):
            urls = self.cmd.run(
                ["git", "remote", "get-url", *flags, "--all", "origin"], cwd=self.app
            ).stdout.splitlines()
            if len(urls) != 1:
                raise ValueError(
                    "Origin must have exactly one fetch URL and one push URL."
                )
            identity = self.cmd.json(
                ["gh", "repo", "view", urls[0], "--json", "nameWithOwner"]
            )
            if identity["nameWithOwner"].lower() != self.repo.lower():
                raise ValueError("App origin points at another repository.")

    def pull_request(self):
        self.verify_repository()
        self.verify_origin()
        SetupCommit(self.local, self.j, self.cmd).validate()
        resource = self.j.data["resources"]
        branch = "codex/bootstrap-private-app"
        if not resource.get("setup_commit"):
            changed = self.cmd.run(
                ["git", "diff", "--cached", "--name-only"], cwd=self.app
            ).stdout
            if changed:
                self.cmd.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        "chore: configure private Frappe app workflow",
                    ],
                    cwd=self.app,
                )
            resource["setup_commit"] = self.cmd.run(
                ["git", "rev-parse", "HEAD"], cwd=self.app
            ).stdout.strip()
            self.j.save()
        if (
            self.cmd.run(["git", "rev-parse", "HEAD"], cwd=self.app).stdout.strip()
            != resource["setup_commit"]
        ):
            raise ValueError(
                "Setup branch changed since the recorded bootstrap commit."
            )
        self.cmd.run(["git", "push", "-u", "origin", branch], cwd=self.app)
        matches = self.cmd.json(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.repo,
                "--head",
                branch,
                "--base",
                "main",
                "--state",
                "all",
                "--json",
                "number,headRefOid,isCrossRepository",
            ]
        )
        if not matches:
            self.create_pr(branch)
            matches = self.cmd.json(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    self.repo,
                    "--head",
                    branch,
                    "--base",
                    "main",
                    "--state",
                    "all",
                    "--json",
                    "number,headRefOid,isCrossRepository",
                ]
            )
        if (
            len(matches) != 1
            or matches[0]["isCrossRepository"]
            or matches[0]["headRefOid"] != resource["setup_commit"]
        ):
            raise ValueError("Setup PR identity is ambiguous or its head changed.")
        resource["pr_number"] = matches[0]["number"]
        self.j.save()

    def create_pr(self, branch):
        body = SetupCommit(self.local, self.j, self.cmd).body()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", dir=self.j.path.parent
        ) as output:
            output.write(body)
            output.flush()
            self.cmd.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    self.repo,
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    "Configure private Frappe app workflow",
                    "--body-file",
                    output.name,
                ],
                cwd=self.app,
            )

    def merge(self):
        self.verify_repository()
        self.verify_origin()
        number = str(self.j.data["resources"]["pr_number"])
        pr = self.cmd.json(
            [
                "gh",
                "pr",
                "view",
                number,
                "--repo",
                self.repo,
                "--json",
                "state,headRefOid",
            ]
        )
        if pr["headRefOid"] != self.j.data["resources"]["setup_commit"]:
            raise ValueError("Setup PR head no longer matches the bootstrap commit.")
        args = [
            "python3",
            "scripts/merge-pr.py",
            number,
            "--ci-timeout",
            str(self.c["ci_timeout"]),
        ]
        if pr["state"] == "MERGED":
            args.append("--resume")
        else:
            self.wait_pr(number)
        self.cmd.run(
            args, cwd=self.app, timeout=self.c["ci_timeout"] + 600, stream=True
        )

    def wait_pr(self, number):
        PullRequestCI(self.c, self.j, self.cmd, self.repo).wait(number)

    def verify_final(self):
        self.verify_repository()
        self.verify_origin()
        head = self.cmd.run(["git", "rev-parse", "HEAD"], cwd=self.app).stdout.strip()
        if (
            self.cmd.run(
                ["git", "branch", "--show-current"], cwd=self.app
            ).stdout.strip()
            != "main"
        ):
            raise ValueError("Final checkout must be on main.")
        remote = self.cmd.json(["gh", "api", f"repos/{self.repo}/git/ref/heads/main"])[
            "object"
        ]["sha"]
        if (
            head != remote
            or self.cmd.run(["git", "status", "--porcelain"], cwd=self.app).stdout
        ):
            raise ValueError("Final checkout is dirty or differs from GitHub main.")
        branch = "codex/bootstrap-private-app"
        if self.cmd.run(
            ["git", "branch", "--list", branch], cwd=self.app
        ).stdout.strip():
            raise ValueError(
                "Bootstrap feature branch was preserved; inspect its unmerged work."
            )
        if self.cmd.run(
            ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
            cwd=self.app,
        ).stdout.strip():
            raise ValueError(
                "Remote bootstrap feature branch remains; inspect before deleting."
            )
        hook = (
            self.app
            / self.cmd.run(
                ["git", "rev-parse", "--git-path", "hooks/pre-push"], cwd=self.app
            ).stdout.strip()
        )
        if (
            not hook.exists()
            or hook.read_bytes() != (self.app / ".githooks/pre-push").read_bytes()
        ):
            raise ValueError("Final checkout is missing the expected main-push hook.")
