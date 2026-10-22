#!/usr/bin/env python3
"""Merge a private repository PR only after its current CI checks succeed."""

import argparse
import json
import subprocess
import sys

from merge_checkout import Checkout
from merge_ci import REQUIRED_CHECKS, MainCI


class MergeGuard:
	def __init__(self, number):
		self.number = number
		self.checkout = Checkout()
		self.repository = self.query(
			"repo", "view", self.checkout.origin_url, "--json", "nameWithOwner,isPrivate"
		)
		self.merge_sha = None
		self.repo = self.repository["nameWithOwner"]

	def run(self, check_only=False, resume=False, ci_timeout=1800):
		self.ensure_private()
		pr = self.read_pr()
		if resume:
			self.confirm_merge(pr)
		else:
			self.validate_before_merge(pr)
			if check_only:
				print(f"PR #{self.number} at {pr['headRefOid']} passes merge safeguards.")
				return
		self.validate_push_destination()
		self.checkout.preflight()
		if not resume:
			print(f"Merging PR #{self.number} at {pr['headRefOid']}...", flush=True)
			subprocess.run(
				[
					"gh",
					"pr",
					"merge",
					str(self.number),
					"--repo",
					self.repo,
					"--merge",
					"--match-head-commit",
					pr["headRefOid"],
				],
				check=True,
			)
			pr = self.read_pr()
			self.confirm_merge(pr)
		print(f"PR #{self.number} is merged at {self.merge_sha}. Completing handoff...", flush=True)
		self.ensure_private()
		self.checkout.sync(self.merge_sha)
		for message in self.checkout.cleanup(pr, self.repo):
			print(message, flush=True)
		MainCI(self.query, self.repo, timeout=ci_timeout).wait(self.merge_sha)
		self.checkout.sync(self.merge_sha)
		self.ensure_private()
		print("Merge handoff complete; main is synced and the repository is private.")

	def validate_before_merge(self, pr):
		self.validate_pr(pr)
		base = self.query("api", f"repos/{self.repo}/git/ref/heads/main")
		comparison = self.query(
			"api", f"repos/{self.repo}/compare/{base['object']['sha']}...{pr['headRefOid']}"
		)
		if comparison["status"] not in {"ahead", "identical"}:
			raise ValueError("PR must include the latest main commit. Update the branch and rerun CI.")
		pages = self.query(
			"api",
			"--paginate",
			"--slurp",
			f"repos/{self.repo}/commits/{pr['headRefOid']}/check-runs?per_page=100",
		)
		self.validate_checks([check for page in pages for check in page["check_runs"]])

	def read_pr(self):
		return self.query(
			"pr",
			"view",
			str(self.number),
			"--repo",
			self.repo,
			"--json",
			"state,isDraft,baseRefName,headRefOid,mergeable,headRefName,headRepository,mergeCommit",
		)

	def ensure_private(self):
		if not self.query("repo", "view", self.repo, "--json", "isPrivate")["isPrivate"]:
			raise ValueError("Repository must remain private.")

	def validate_push_destination(self):
		push_repo = self.query("repo", "view", self.checkout.push_url, "--json", "nameWithOwner")
		if push_repo["nameWithOwner"].lower() != self.repo.lower():
			raise ValueError("Origin push URL must point to the same repository as its fetch URL.")

	def confirm_merge(self, pr):
		if pr["state"] != "MERGED" or pr["baseRefName"] != "main" or not pr.get("mergeCommit"):
			raise ValueError("A confirmed merged PR targeting main is required to complete the handoff.")
		self.merge_sha = pr["mergeCommit"]["oid"]

	@staticmethod
	def query(*arguments):
		result = subprocess.run(["gh", *arguments], check=True, capture_output=True, text=True, timeout=60)
		return json.loads(result.stdout)

	@staticmethod
	def validate_pr(pr):
		if pr["state"] != "OPEN" or pr["isDraft"] or pr["baseRefName"] != "main":
			raise ValueError("An open, non-draft PR targeting main is required.")
		if pr["mergeable"] != "MERGEABLE":
			raise ValueError("GitHub has not confirmed that this PR is mergeable.")

	@staticmethod
	def validate_checks(checks):
		for name in sorted(REQUIRED_CHECKS):
			matches = [check for check in checks if check["name"] == name]
			if len(matches) != 1:
				raise ValueError(f"Expected exactly one {name} check on the current PR head.")
			check = matches[0]
			if check.get("app", {}).get("slug") != "github-actions":
				raise ValueError(f"{name} must come from GitHub Actions.")
			if check["status"] != "completed" or check["conclusion"] != "success":
				raise ValueError(f"{name} must complete successfully before merging.")


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("pr", type=int, help="Pull request number in the current repository")
	mode = parser.add_mutually_exclusive_group()
	mode.add_argument("--check-only", action="store_true", help="Validate without merging or cleanup")
	mode.add_argument("--resume", action="store_true", help="Complete handoff for an already merged PR")
	parser.add_argument(
		"--ci-timeout", type=int, default=1800, help="Seconds to wait for main CI (default 1800)"
	)
	arguments = parser.parse_args()
	if arguments.ci_timeout <= 0:
		parser.error("CI timeout must be positive")
	if arguments.pr <= 0:
		parser.error("PR number must be positive")
	guard = None
	try:
		guard = MergeGuard(arguments.pr)
		guard.run(arguments.check_only, arguments.resume, arguments.ci_timeout)
	except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
		print(f"Merge workflow failed: {error}", file=sys.stderr)
		if guard and guard.merge_sha:
			print(
				f"PR is already merged at {guard.merge_sha}. Retry with --resume after fixing the error.",
				file=sys.stderr,
			)
		else:
			print(
				"If a merge was attempted, confirm its state before retrying; use --resume once merged.",
				file=sys.stderr,
			)
		if isinstance(error, subprocess.CalledProcessError) and error.stderr:
			print(error.stderr, file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
