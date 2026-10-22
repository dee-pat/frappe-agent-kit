"""Exercise local Git and merge safeguards without changing GitHub."""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("PRIVATE_APP_ROOT", Path(__file__).resolve().parent.parent))
SPEC = importlib.util.spec_from_file_location("merge_pr", ROOT / "scripts/merge-pr.py")
MERGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGE)
HEAD = "a" * 40
BASE = "b" * 40


def passing_checks():
	return [
		{"name": name, "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}}
		for name in sorted(MERGE.REQUIRED_CHECKS)
	]


def valid_pr():
	return {
		"state": "OPEN",
		"isDraft": False,
		"baseRefName": "main",
		"baseRefOid": BASE,
		"headRefOid": HEAD,
		"mergeable": "MERGEABLE",
	}


class PushHookTests(unittest.TestCase):
	def run_hook(self, updates):
		return subprocess.run(
			["bash", str(ROOT / ".githooks/pre-push"), "origin", "unused"],
			input=updates,
			text=True,
			capture_output=True,
			check=False,
		)

	def test_rejects_every_update_targeting_main(self):
		for source, oid in [("refs/heads/main", HEAD), ("refs/heads/feature", HEAD), ("(delete)", "0" * 40)]:
			with self.subTest(source=source):
				result = self.run_hook(f"{source} {oid} refs/heads/main {BASE}\n")
				self.assertNotEqual(result.returncode, 0)
				self.assertIn("Direct updates to main are blocked", result.stderr)

	def test_rejects_main_among_multiple_updates(self):
		updates = f"refs/heads/feature {HEAD} refs/heads/feature {BASE}\n"
		updates += f"refs/heads/other {HEAD} refs/heads/main {BASE}\n"
		self.assertNotEqual(self.run_hook(updates).returncode, 0)

	def test_allows_non_main_updates_and_empty_push(self):
		for destination in ["refs/heads/feature", "refs/heads/main-backup", "refs/tags/main"]:
			with self.subTest(destination=destination):
				self.assertEqual(
					self.run_hook(f"refs/heads/main {HEAD} {destination} {BASE}\n").returncode, 0
				)
		self.assertEqual(self.run_hook("").returncode, 0)


class HookInstallationTests(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.root = Path(self.directory.name)
		subprocess.run(["git", "init", "-q", str(self.root)], check=True)
		for filename in ["scripts/install-hooks.sh", ".githooks/pre-push"]:
			target = self.root / filename
			target.parent.mkdir(parents=True, exist_ok=True)
			shutil.copyfile(ROOT / filename, target)
		self.target = self.root / ".git/hooks/pre-push"

	def install(self):
		return subprocess.run(
			["bash", str(self.root / "scripts/install-hooks.sh")],
			capture_output=True,
			text=True,
			check=False,
		)

	def test_installs_idempotently_and_preserves_other_hooks(self):
		other = self.root / ".git/hooks/pre-commit"
		other.write_text("existing pre-commit\n")
		self.assertEqual(self.install().returncode, 0)
		self.assertEqual(self.install().returncode, 0)
		self.assertEqual(self.target.read_bytes(), (ROOT / ".githooks/pre-push").read_bytes())
		self.assertTrue(os.access(self.target, os.X_OK))
		self.assertEqual(other.read_text(), "existing pre-commit\n")

	def test_preserves_conflicting_hook(self):
		self.target.write_text("existing pre-push\n")
		self.assertNotEqual(self.install().returncode, 0)
		self.assertEqual(self.target.read_text(), "existing pre-push\n")

	def test_git_push_blocks_main_but_allows_feature(self):
		remote = self.root / "remote.git"
		subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
		subprocess.run(
			[
				"git",
				"-C",
				str(self.root),
				"-c",
				"user.name=Test",
				"-c",
				"user.email=test@example.com",
				"-c",
				"commit.gpgsign=false",
				"commit",
				"--allow-empty",
				"-qm",
				"Test fixture",
			],
			check=True,
		)
		self.assertEqual(self.install().returncode, 0)
		for branch, expected in [("main", 1), ("feature", 0)]:
			with self.subTest(branch=branch):
				result = subprocess.run(
					["git", "-C", str(self.root), "push", str(remote), f"HEAD:refs/heads/{branch}"],
					capture_output=True,
					text=True,
					check=False,
				)
				self.assertEqual(result.returncode, expected)

	def test_preserves_custom_hooks_path(self):
		subprocess.run(["git", "-C", str(self.root), "config", "core.hooksPath", "custom-hooks"], check=True)
		self.assertNotEqual(self.install().returncode, 0)
		self.assertFalse(self.target.exists())


class MergeValidationTests(unittest.TestCase):
	def test_rejects_invalid_pr_state(self):
		for field, value in [
			("state", "CLOSED"),
			("state", "MERGED"),
			("isDraft", True),
			("baseRefName", "develop"),
			("mergeable", "UNKNOWN"),
			("mergeable", "CONFLICTING"),
		]:
			with self.subTest(field=field, value=value):
				pr = valid_pr()
				pr[field] = value
				with self.assertRaises(ValueError):
					MERGE.MergeGuard.validate_pr(pr)

	def test_accepts_valid_pr_and_checks(self):
		MERGE.MergeGuard.validate_pr(valid_pr())
		MERGE.MergeGuard.validate_checks(passing_checks())

	def test_rejects_missing_or_duplicate_checks(self):
		for name in MERGE.REQUIRED_CHECKS:
			checks = passing_checks()
			selected = next(check for check in checks if check["name"] == name)
			for changed in [[check for check in checks if check["name"] != name], [*checks, selected]]:
				with self.subTest(name=name, count=len(changed)), self.assertRaises(ValueError):
					MERGE.MergeGuard.validate_checks(changed)

	def test_rejects_checks_without_successful_completion(self):
		for name in MERGE.REQUIRED_CHECKS:
			for status, conclusion in [
				("queued", None),
				("in_progress", None),
				("completed", "failure"),
				("completed", "skipped"),
				("completed", "cancelled"),
				("completed", "neutral"),
			]:
				with self.subTest(name=name, status=status, conclusion=conclusion):
					checks = passing_checks()
					selected = next(check for check in checks if check["name"] == name)
					selected.update(status=status, conclusion=conclusion)
					with self.assertRaises(ValueError):
						MERGE.MergeGuard.validate_checks(checks)

	def test_rejects_wrong_check_provider(self):
		for app in [{"slug": "third-party"}, {}]:
			with self.subTest(app=app):
				checks = passing_checks()
				checks[0]["app"] = app
				with self.assertRaises(ValueError):
					MERGE.MergeGuard.validate_checks(checks)


if __name__ == "__main__":
	unittest.main()
