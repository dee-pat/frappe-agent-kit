"""Wait for the push-triggered CI run on an exact main commit."""

import time

REQUIRED_CHECKS = {"Lint", "Agent kit", "Server"}


class MainCI:
	def __init__(self, query, repo, timeout=1800):
		self.query = query
		self.repo = repo
		self.timeout = timeout

	def wait(self, sha):
		deadline = time.monotonic() + self.timeout
		while time.monotonic() < deadline:
			pages = self.query(
				"api",
				"--paginate",
				"--slurp",
				f"repos/{self.repo}/actions/workflows/ci.yml/runs?event=push&branch=main&head_sha={sha}&per_page=100",
			)
			runs = [
				run
				for page in pages
				for run in page["workflow_runs"]
				if run["head_sha"] == sha and run["head_branch"] == "main" and run["event"] == "push"
			]
			if runs:
				run = max(runs, key=lambda item: item["id"])
				if run["status"] == "completed":
					return self.verify(run)
				print(f"CI for {sha[:12]}: {run['status']} ({run['html_url']})", flush=True)
			else:
				print(f"Waiting for main CI to appear for {sha[:12]}...", flush=True)
			time.sleep(max(0, min(20, deadline - time.monotonic())))
		raise TimeoutError(f"Timed out waiting for main CI on {sha}; use --resume to retry.")

	def verify(self, run):
		if run["conclusion"] != "success":
			raise ValueError(f"Main CI did not succeed: {run['html_url']} ({run['conclusion']}).")
		pages = self.query(
			"api",
			"--paginate",
			"--slurp",
			f"repos/{self.repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100",
		)
		jobs = [job for page in pages for job in page["jobs"]]
		for name in sorted(REQUIRED_CHECKS):
			matches = [job for job in jobs if job["name"] == name]
			if len(matches) != 1:
				raise ValueError(f"Expected exactly one {name} job in main CI: {run['html_url']}.")
			if matches[0]["status"] != "completed" or matches[0]["conclusion"] != "success":
				raise ValueError(f"Main CI job {name} did not succeed: {run['html_url']}.")
		print(f"Main CI passed: {run['html_url']}", flush=True)
		return run["html_url"]
