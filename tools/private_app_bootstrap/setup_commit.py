"""Restrict a resumed setup commit to the bootstrap's verified file set."""


class SetupCommit:
    def __init__(self, local, journal, commands):
        self.local, self.j, self.cmd, self.app = local, journal, commands, local.app

    def validate(self):
        self.local.verify_configured()
        resource = self.j.data["resources"]
        allowed = {*self.j.data["files"], ".claude/skills"}
        for args in (
            ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                "-z",
                resource["initial_commit"],
                "HEAD",
            ],
        ):
            paths = self.cmd.run(args, cwd=self.app).stdout.split("\0")
            unexpected = [
                path
                for path in paths
                if path
                and path not in allowed
                and not path.startswith((".agents/skills/", "semgrep/"))
            ]
            if unexpected:
                raise ValueError(
                    "Refusing unrelated setup changes: " + ", ".join(unexpected)
                )
        if self.cmd.run(["git", "diff", "--name-only"], cwd=self.app).stdout:
            raise ValueError(
                "Unstaged setup edits were preserved; inspect before resuming."
            )
        if self.cmd.run(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=self.app
        ).stdout:
            raise ValueError(
                "Untracked user files were preserved; inspect before resuming."
            )
        branch = self.cmd.run(
            ["git", "branch", "--show-current"], cwd=self.app
        ).stdout.strip()
        if branch != "codex/bootstrap-private-app":
            raise ValueError("Setup checkout is not on its recorded feature branch.")
        self.cmd.run(
            ["git", "merge-base", "--is-ancestor", resource["initial_commit"], "HEAD"],
            cwd=self.app,
        )

    def body(self):
        sha = self.j.data["resources"]["setup_commit"]
        return f"""## Summary

Configure pinned Frappe CI, agent guidance and local merge safeguards for this private app.
Before: scaffold only. After: isolated sites, tested CI and guarded PR handoff.

## Verification

- Risk classification and required gates: developer workflow; lint, kit checks and app tests.
- Local scripts/lint.sh, kit checks and installation smoke tests completed with exit 0.
- Reviewed head: `{sha}`.
- Required CI: pending; bootstrap waits for Lint, Agent kit and Server before merging.
- Local/CI differences: GitHub validates a fresh Ubuntu bench in addition to this local install.
- Domain documentation: generated verification and safeguard guides; no business rules changed.

## Risk and rollback

- Affected flows: development setup and PR merges; no existing apps/sites were replaced.
- No app data migration. Preserve created resources on error and rerun with --resume.
- GitHub Free local safeguards are bypassable and do not replace branch protection.

## Review status

- Not yet reviewed. CI validation is automated; semantic review is not claimed.
- Remaining follow-up: human review of app-specific business logic as it is added.
"""
