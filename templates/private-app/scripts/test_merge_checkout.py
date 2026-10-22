"""Verify checkout synchronization and cleanup in temporary repositories."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get("PRIVATE_APP_ROOT", Path(__file__).resolve().parent.parent))
HELPER = Path(os.environ.get("MERGE_CHECKOUT_PATH", ROOT / "scripts/merge_checkout.py"))
SPEC = importlib.util.spec_from_file_location("merge_checkout", HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CheckoutTests(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.root = Path(self.directory.name)
		self.remote = self.root / "remote.git"
		self.local = self.root / "local"
		self.git("init", "--bare", "--initial-branch=main", str(self.remote))
		self.git("clone", str(self.remote), str(self.local))
		self.configure(self.local)
		self.commit(self.local, "Initial")
		self.git("-C", str(self.local), "push", "-u", "origin", "main")
		previous = Path.cwd()
		os.chdir(self.local)
		self.addCleanup(os.chdir, previous)
		self.checkout = MODULE.Checkout()
		self.pr = {"headRefName": "feature", "headRepository": {"nameWithOwner": "example/app"}}

	def git(self, *arguments):
		return subprocess.run(["git", *arguments], capture_output=True, text=True, check=True).stdout.strip()

	def configure(self, root):
		for key, value in [
			("user.name", "Test"),
			("user.email", "test@example.com"),
			("commit.gpgsign", "false"),
		]:
			self.git("-C", str(root), "config", key, value)

	def commit(self, root, message):
		self.git("-C", str(root), "commit", "--allow-empty", "-m", message)
		return self.git("-C", str(root), "rev-parse", "HEAD")

	def merged_pr(self):
		self.git("-C", str(self.local), "switch", "-c", "feature")
		self.pr["headRefOid"] = self.commit(self.local, "Feature")
		self.git("-C", str(self.local), "push", "-u", "origin", "feature")
		peer = self.root / "peer"
		self.git("clone", str(self.remote), str(peer))
		self.configure(peer)
		self.git("-C", str(peer), "merge", "--no-ff", "origin/feature", "-m", "Merge feature")
		merge = self.git("-C", str(peer), "rev-parse", "HEAD")
		self.git("-C", str(peer), "push", "origin", "main")
		return merge

	def test_multiple_push_urls_are_rejected(self):
		self.git("-C", str(self.local), "remote", "set-url", "--add", "--push", "origin", str(self.remote))
		self.git("-C", str(self.local), "remote", "set-url", "--add", "--push", "origin", "elsewhere")
		with self.assertRaisesRegex(ValueError, "exactly one"):
			_ = self.checkout.push_url

	def test_preflight_preserves_dirty_work(self):
		(self.local / "untracked.txt").write_text("Keep me")
		with self.assertRaisesRegex(ValueError, "clean worktree"):
			self.checkout.preflight()
		self.assertEqual((self.local / "untracked.txt").read_text(), "Keep me")

	def test_preflight_preserves_ahead_main(self):
		tip = self.commit(self.local, "Unpublished")
		with self.assertRaisesRegex(ValueError, "cannot fast-forward"):
			self.checkout.preflight()
		self.assertEqual(self.checkout.ref_tip("main"), tip)

	def test_preflight_rejects_main_in_other_worktree(self):
		self.git("-C", str(self.local), "switch", "-c", "feature")
		self.git("-C", str(self.local), "worktree", "add", str(self.root / "other"), "main")
		with self.assertRaisesRegex(ValueError, "another worktree"):
			self.checkout.preflight()

	def test_sync_fast_forwards_and_cleans_merged_branches(self):
		merge = self.merged_pr()
		self.checkout.preflight()
		self.checkout.sync(merge)
		self.assertEqual(self.checkout.ref_tip("HEAD"), merge)
		self.assertEqual(self.checkout.cleanup(self.pr, "example/app"), [])
		self.assertIsNone(self.checkout.ref_tip("refs/heads/feature"))
		self.assertEqual(self.git("ls-remote", "--heads", str(self.remote), "refs/heads/feature"), "")
		self.assertEqual(self.checkout.cleanup(self.pr, "example/app"), [])

	def test_sync_creates_missing_local_main(self):
		merge = self.merged_pr()
		self.git("-C", str(self.local), "branch", "-D", "main")
		self.checkout.sync(merge)
		self.assertEqual(self.checkout.ref_tip("main"), merge)

	def test_sync_refuses_missing_merge_commit(self):
		with self.assertRaisesRegex(ValueError, "merge commit"):
			self.checkout.sync("a" * 40)

	def test_local_new_work_is_preserved_independently(self):
		merge = self.merged_pr()
		tip = self.commit(self.local, "New local work")
		self.checkout.sync(merge)
		messages = self.checkout.cleanup(self.pr, "example/app")
		self.assertIn("Preserved local feature", messages[0])
		self.assertEqual(self.checkout.ref_tip("feature"), tip)
		self.assertEqual(self.git("ls-remote", "--heads", str(self.remote), "refs/heads/feature"), "")

	def test_remote_new_work_is_preserved(self):
		merge = self.merged_pr()
		self.checkout.sync(merge)
		self.git("-C", str(self.local), "switch", "feature")
		tip = self.commit(self.local, "New shared work")
		self.git("-C", str(self.local), "push", "origin", "feature")
		self.git("-C", str(self.local), "switch", "main")
		messages = self.checkout.cleanup(self.pr, "example/app")
		self.assertEqual(len(messages), 2)
		self.assertIn("Preserved remote feature", messages[1])
		self.assertTrue(
			self.git("ls-remote", "--heads", str(self.remote), "refs/heads/feature").startswith(tip)
		)

	def test_branch_in_other_worktree_preserves_local_and_remote(self):
		merge = self.merged_pr()
		self.checkout.sync(merge)
		self.git("-C", str(self.local), "worktree", "add", str(self.root / "other"), "feature")
		messages = self.checkout.cleanup(self.pr, "example/app")
		self.assertIn("checked out", messages[0])
		self.assertEqual(self.checkout.ref_tip("feature"), self.pr["headRefOid"])
		self.assertTrue(self.git("ls-remote", "--heads", str(self.remote), "refs/heads/feature"))

	def test_remote_lease_preserves_concurrent_push(self):
		merge = self.merged_pr()
		self.checkout.sync(merge)
		self.git("-C", str(self.local), "switch", "-c", "concurrent", "feature")
		new_tip = self.commit(self.local, "Concurrent work")
		self.git("-C", str(self.local), "push", "origin", "concurrent")
		self.git("-C", str(self.local), "switch", "main")
		original = self.checkout.git

		def race(*arguments, **kwargs):
			if arguments[0] == "push":
				self.git("--git-dir", str(self.remote), "update-ref", "refs/heads/feature", new_tip)
			return original(*arguments, **kwargs)

		with (
			patch.object(self.checkout, "git", side_effect=race),
			self.assertRaises(subprocess.CalledProcessError),
		):
			self.checkout.cleanup(self.pr, "example/app")
		self.assertTrue(
			self.git("ls-remote", "--heads", str(self.remote), "refs/heads/feature").startswith(new_tip)
		)

	def test_foreign_head_and_main_are_preserved(self):
		merge = self.merged_pr()
		self.checkout.sync(merge)
		for repository in [None, {"nameWithOwner": "other/widget"}]:
			with self.subTest(repository=repository):
				self.pr["headRepository"] = repository
				self.assertIn("foreign", self.checkout.cleanup(self.pr, "example/app")[0])
		self.pr.update(headRepository={"nameWithOwner": "example/app"}, headRefName="main")
		self.assertIn("never", self.checkout.cleanup(self.pr, "example/app")[0])
		self.assertEqual(self.checkout.ref_tip("main"), merge)


if __name__ == "__main__":
	unittest.main()
