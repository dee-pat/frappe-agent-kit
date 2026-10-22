"""Wait for the generated setup PR checks without accepting a changed head."""

import time


class PullRequestCI:
    def __init__(self, config, journal, commands, repo):
        self.c, self.j, self.cmd, self.repo = config, journal, commands, repo

    def wait(self, number):
        deadline = time.monotonic() + self.c["ci_timeout"]
        required = {"Lint", "Agent kit", "Server"}
        while time.monotonic() < deadline:
            pr = self.cmd.json(
                [
                    "gh",
                    "pr",
                    "view",
                    number,
                    "--repo",
                    self.repo,
                    "--json",
                    "state,headRefOid,statusCheckRollup",
                ]
            )
            if (
                pr["state"] != "OPEN"
                or pr["headRefOid"] != self.j.data["resources"]["setup_commit"]
            ):
                raise ValueError("Setup PR changed or closed while waiting for CI.")
            checks = pr["statusCheckRollup"] or []
            selected = [check for check in checks if check.get("name") in required]
            if any(
                check.get("status") == "COMPLETED"
                and check.get("conclusion") != "SUCCESS"
                for check in selected
            ):
                raise ValueError("Setup PR CI failed; fix the cause before resuming.")
            if {check.get("name") for check in selected} == required and all(
                check.get("status") == "COMPLETED"
                and check.get("conclusion") == "SUCCESS"
                for check in selected
            ):
                return
            print("Waiting for setup PR Lint, Agent kit and Server...", flush=True)
            time.sleep(max(0, min(20, deadline - time.monotonic())))
        raise TimeoutError("Setup PR CI timed out; resume after the checks complete.")
