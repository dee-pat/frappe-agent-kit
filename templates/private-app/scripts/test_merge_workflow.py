"""Verify guarded merge sequencing without changing GitHub."""

import contextlib
import io
import unittest
from unittest.mock import patch

from test_merge_safeguards import BASE, HEAD, MERGE, passing_checks, valid_pr


class MergeExecutionTests(unittest.TestCase):
	def setUp(self):
		self.checkout_patch = patch.object(MERGE, "Checkout")
		self.checkout = self.checkout_patch.start().return_value
		self.addCleanup(self.checkout_patch.stop)
		self.checkout.origin_url = "https://github.com/example/app.git"
		self.checkout.push_url = self.checkout.origin_url
		self.checkout.cleanup.return_value = []
		self.ci_patch = patch.object(MERGE, "MainCI")
		self.ci = self.ci_patch.start()
		self.addCleanup(self.ci_patch.stop)
		self.private = True
		self.comparison = "ahead"
		self.resume = False
		self.push_repo = "example/app"
		self.reads = 0
		self.merged_sha = "c" * 40

	def query(self, *args):
		if args[:2] == ("repo", "view"):
			if args[-1] == "isPrivate":
				return {"isPrivate": self.private}
			return {
				"nameWithOwner": self.push_repo if args[-1] == "nameWithOwner" else "example/app",
				"isPrivate": self.private,
			}
		if args[:2] == ("pr", "view"):
			self.reads += 1
			pr = valid_pr()
			pr.update(headRefName="feature", headRepository={"nameWithOwner": "example/app"})
			if self.resume or self.reads > 1:
				pr.update(state="MERGED", mergeCommit={"oid": self.merged_sha})
			return pr
		if "/compare/" in args[-1]:
			return {"status": self.comparison}
		if "/git/ref/" in args[-1]:
			return {"object": {"sha": BASE}}
		if "/check-runs" in args[-1]:
			return [{"check_runs": passing_checks()[:1]}, {"check_runs": passing_checks()[1:]}]
		raise AssertionError(args)

	def run_guard(self, **options):
		with patch.object(MERGE.MergeGuard, "query", side_effect=self.query) as query:
			with patch.object(MERGE.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
				guard = MERGE.MergeGuard(12)
				guard.run(**options)
		return guard, query, run

	def test_check_only_does_not_merge_sync_or_cleanup(self):
		_, query, run = self.run_guard(check_only=True)
		run.assert_not_called()
		self.checkout.preflight.assert_not_called()
		self.checkout.sync.assert_not_called()
		self.checkout.cleanup.assert_not_called()
		self.ci.assert_not_called()
		self.assertTrue(any(f"{BASE}...{HEAD}" in call.args[-1] for call in query.call_args_list))

	def test_merge_matches_head_and_completes_handoff(self):
		guard, query, run = self.run_guard(ci_timeout=50)
		run.assert_called_once_with(
			["gh", "pr", "merge", "12", "--repo", "example/app", "--merge", "--match-head-commit", HEAD],
			check=True,
		)
		self.assertEqual(guard.merge_sha, self.merged_sha)
		self.assertEqual(self.checkout.sync.call_count, 2)
		self.checkout.sync.assert_called_with(self.merged_sha)
		self.checkout.cleanup.assert_called_once()
		self.ci.assert_called_once_with(query, "example/app", timeout=50)
		self.ci.return_value.wait.assert_called_once_with(self.merged_sha)

	def test_resume_does_not_merge_again(self):
		self.resume = True
		_, _, run = self.run_guard(resume=True)
		run.assert_not_called()
		self.checkout.sync.assert_called_with(self.merged_sha)
		self.ci.return_value.wait.assert_called_once_with(self.merged_sha)

	def test_resume_rejects_open_pr(self):
		with self.assertRaisesRegex(ValueError, "confirmed merged PR"):
			self.run_guard(resume=True)
		self.checkout.preflight.assert_not_called()

	def test_rejects_public_repository_without_merging(self):
		self.private = False
		with self.assertRaisesRegex(ValueError, "private"):
			self.run_guard()
		self.checkout.preflight.assert_not_called()

	def test_rejects_outdated_base(self):
		for comparison in ["behind", "diverged"]:
			self.reads = 0
			self.comparison = comparison
			with self.subTest(comparison=comparison), self.assertRaisesRegex(ValueError, "latest main"):
				self.run_guard()
		self.checkout.preflight.assert_not_called()

	def test_mismatched_push_destination_prevents_merge(self):
		self.push_repo = "other/repository"
		with self.assertRaisesRegex(ValueError, "same repository"):
			self.run_guard()
		self.checkout.preflight.assert_not_called()

	def test_ci_failure_is_not_reported_as_success(self):
		self.ci.return_value.wait.side_effect = ValueError("CI failed")
		with self.assertRaisesRegex(ValueError, "CI failed"):
			self.run_guard()
		self.checkout.cleanup.assert_called_once()
		self.assertEqual(self.checkout.sync.call_count, 1)

	def test_dirty_checkout_prevents_merge(self):
		self.checkout.preflight.side_effect = ValueError("dirty")
		with patch.object(MERGE.subprocess, "run") as run, self.assertRaisesRegex(ValueError, "dirty"):
			with patch.object(MERGE.MergeGuard, "query", side_effect=self.query):
				MERGE.MergeGuard(12).run()
		run.assert_not_called()

	def test_privacy_is_rechecked_after_handoff(self):
		def visibility_changes(_sha):
			self.private = False

		self.ci.return_value.wait.side_effect = visibility_changes
		with self.assertRaisesRegex(ValueError, "private"):
			self.run_guard()
		self.assertEqual(self.checkout.sync.call_count, 2)

	def test_post_merge_failure_reports_already_merged(self):
		with (
			patch.object(MERGE, "MergeGuard") as guard,
			patch.object(MERGE.sys, "argv", ["merge-pr.py", "12"]),
		):
			guard.return_value.merge_sha = self.merged_sha
			guard.return_value.run.side_effect = TimeoutError("CI timed out")
			with contextlib.redirect_stderr(io.StringIO()) as output:
				self.assertEqual(MERGE.main(), 1)
		self.assertIn("already merged", output.getvalue())
		self.assertIn("--resume", output.getvalue())


if __name__ == "__main__":
	unittest.main()
