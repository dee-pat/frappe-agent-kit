"""Safely synchronize a checkout and remove merged PR branches."""

import subprocess
from pathlib import Path


class Checkout:
	def __init__(self):
		result = subprocess.run(
			["git", "rev-parse", "--show-toplevel"],
			capture_output=True,
			text=True,
			check=True,
		)
		self.root = Path(result.stdout.strip()).resolve()

	@property
	def origin_url(self):
		return self.git("remote", "get-url", "origin").stdout.strip()

	@property
	def push_url(self):
		urls = self.git("remote", "get-url", "--push", "--all", "origin").stdout.splitlines()
		if len(urls) != 1:
			raise ValueError("origin must have exactly one push URL.")
		return urls[0]

	def preflight(self):
		self.require_clean()
		self.git("fetch", "origin")
		self.require_main_available()

	def sync(self, merge_sha):
		self.require_clean()
		self.git("fetch", "origin")
		self.require_main_available()
		if not self.is_ancestor(merge_sha, "refs/remotes/origin/main"):
			raise ValueError("The confirmed merge commit is not contained in origin/main.")
		if self.ref_tip("refs/heads/main"):
			self.git("switch", "main")
		else:
			self.git("switch", "--track", "-c", "main", "origin/main")
		self.git("merge", "--ff-only", "origin/main")
		self.require_synced_main()

	def cleanup(self, pr, repo):
		self.require_synced_main()
		branch = pr["headRefName"]
		head_repo = pr.get("headRepository") or {}
		if head_repo.get("nameWithOwner") != repo:
			return ["Preserved PR branches: head repository is foreign or unavailable."]
		if branch == "main":
			return ["Preserved main: it is never a cleanup target."]
		ref = f"refs/heads/{branch}"
		if self.git("check-ref-format", ref, check=False).returncode:
			raise ValueError("PR head branch is not a valid Git ref.")
		if self.branch_worktrees(branch):
			return [f"Preserved {branch}: branch is checked out in a worktree."]
		messages = []
		local_tip = self.ref_tip(ref)
		if local_tip:
			if self.is_ancestor(local_tip, "refs/heads/main"):
				self.git("branch", "-d", "--", branch)
			else:
				messages.append(f"Preserved local {branch}: tip is not merged into main.")
		self.cleanup_remote(branch, messages)
		self.git("fetch", "--prune", "origin")
		self.require_synced_main()
		return messages

	def cleanup_remote(self, branch, messages):
		ref = f"refs/heads/{branch}"
		lines = self.git("ls-remote", "--heads", "origin", ref).stdout.splitlines()
		if not lines:
			return
		if len(lines) != 1 or lines[0].split()[1] != ref:
			raise ValueError("Remote branch lookup was ambiguous.")
		tip = lines[0].split()[0]
		if self.git("cat-file", "-e", f"{tip}^{{commit}}", check=False).returncode:
			self.git("fetch", "origin", ref)
		if not self.is_ancestor(tip, "refs/heads/main"):
			messages.append(f"Preserved remote {branch}: tip is not merged into main.")
			return
		self.git("push", f"--force-with-lease={ref}:{tip}", "origin", f":{ref}")

	def require_clean(self):
		if self.git("status", "--porcelain=v1").stdout:
			raise ValueError("A clean worktree is required; local changes were preserved.")

	def require_main_available(self):
		if not self.ref_tip("refs/remotes/origin/main"):
			raise ValueError("origin/main does not exist.")
		other = [path for path in self.branch_worktrees("main") if path != self.root]
		if other:
			raise ValueError("main is checked out in another worktree.")
		local = self.ref_tip("refs/heads/main")
		if local and not self.is_ancestor(local, "refs/remotes/origin/main"):
			raise ValueError("Local main cannot fast-forward; local commits were preserved.")

	def require_synced_main(self):
		self.require_clean()
		branch = self.git("branch", "--show-current").stdout.strip()
		if branch != "main" or self.ref_tip("HEAD") != self.ref_tip("refs/remotes/origin/main"):
			raise ValueError("Checkout must be on main and match origin/main.")

	def branch_worktrees(self, branch):
		paths = []
		for block in self.git("worktree", "list", "--porcelain").stdout.split("\n\n"):
			lines = block.splitlines()
			if f"branch refs/heads/{branch}" in lines:
				paths.extend(
					Path(line.removeprefix("worktree ")).resolve()
					for line in lines
					if line.startswith("worktree ")
				)
		return paths

	def ref_tip(self, ref):
		result = self.git("rev-parse", "--verify", "--quiet", ref, check=False)
		return result.stdout.strip() if result.returncode == 0 else None

	def is_ancestor(self, ancestor, descendant):
		return self.git("merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0

	def git(self, *arguments, check=True):
		return subprocess.run(
			["git", "-C", str(self.root), *arguments],
			capture_output=True,
			text=True,
			check=check,
		)
