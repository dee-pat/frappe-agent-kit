"""Exercise main CI selection and waiting without network access or real sleeps."""

import contextlib
import copy
import io
import itertools
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(os.environ.get("PRIVATE_APP_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT / "scripts"))
import merge_ci

SHA = "a" * 40
REPO = "example/app"


def workflow_run(**changes):
	run = {
		"id": 10,
		"head_sha": SHA,
		"head_branch": "main",
		"event": "push",
		"status": "completed",
		"conclusion": "success",
		"html_url": "https://example.test/runs/10",
	}
	run.update(changes)
	return run


def passing_jobs():
	return [
		{"name": name, "status": "completed", "conclusion": "success"}
		for name in sorted(merge_ci.REQUIRED_CHECKS)
	]


class MainCITests(unittest.TestCase):
	def setUp(self):
		self.output = contextlib.redirect_stdout(io.StringIO())
		self.output.__enter__()
		self.addCleanup(self.output.__exit__, None, None, None)
		clock = patch.object(merge_ci.time, "monotonic", side_effect=itertools.count())
		clock.start()
		self.addCleanup(clock.stop)
		sleep = patch.object(merge_ci.time, "sleep")
		self.sleep = sleep.start()
		self.addCleanup(sleep.stop)

	def test_pins_workflow_event_branch_and_commit(self):
		query = Mock(side_effect=[[{"workflow_runs": [workflow_run()]}], [{"jobs": passing_jobs()}]])
		url = merge_ci.MainCI(query, REPO).wait(SHA)
		self.assertEqual(url, "https://example.test/runs/10")
		self.assertEqual(
			query.call_args_list[0].args,
			(
				"api",
				"--paginate",
				"--slurp",
				f"repos/{REPO}/actions/workflows/ci.yml/runs?event=push&branch=main&head_sha={SHA}&per_page=100",
			),
		)
		self.assertIn("actions/runs/10/jobs?filter=latest", query.call_args_list[1].args[3])
		self.sleep.assert_not_called()

	def test_ignores_old_commit_wrong_branch_and_non_push_runs(self):
		for changes in [{"head_sha": "b" * 40}, {"head_branch": "feature"}, {"event": "pull_request"}]:
			with self.subTest(changes=changes):
				query = Mock(
					side_effect=[
						[{"workflow_runs": [workflow_run(**changes)]}],
						[{"workflow_runs": [workflow_run()]}],
						[{"jobs": passing_jobs()}],
					]
				)
				merge_ci.MainCI(query, REPO).wait(SHA)
				self.assertEqual(query.call_count, 3)

	def test_waits_for_run_to_appear_and_finish(self):
		query = Mock(
			side_effect=[
				[{"workflow_runs": []}],
				[{"workflow_runs": [workflow_run(status="in_progress", conclusion=None)]}],
				[{"workflow_runs": [workflow_run()]}],
				[{"jobs": passing_jobs()}],
			]
		)
		merge_ci.MainCI(query, REPO).wait(SHA)
		self.assertEqual(self.sleep.call_count, 2)
		self.assertEqual(query.call_count, 4)

	def test_selects_latest_run_instead_of_older_success(self):
		query = Mock(
			return_value=[
				{
					"workflow_runs": [
						workflow_run(id=9),
						workflow_run(id=11, conclusion="failure"),
					]
				}
			]
		)
		with self.assertRaisesRegex(ValueError, "failure"):
			merge_ci.MainCI(query, REPO).wait(SHA)
		query.assert_called_once()

	def test_supports_run_and_job_pagination(self):
		jobs = passing_jobs()
		query = Mock(
			side_effect=[
				[{"workflow_runs": [workflow_run(id=9)]}, {"workflow_runs": [workflow_run()]}],
				[{"jobs": jobs[:1]}, {"jobs": [*jobs[1:], {"name": "Extra"}]}],
			]
		)
		self.assertEqual(merge_ci.MainCI(query, REPO).wait(SHA), "https://example.test/runs/10")

	def test_rejects_unsuccessful_workflow_conclusions(self):
		for conclusion in ["failure", "cancelled", "skipped", "timed_out", None]:
			with self.subTest(conclusion=conclusion):
				query = Mock(return_value=[{"workflow_runs": [workflow_run(conclusion=conclusion)]}])
				with self.assertRaisesRegex(ValueError, "Main CI did not succeed"):
					merge_ci.MainCI(query, REPO).wait(SHA)
				query.assert_called_once()

	def test_rejects_missing_and_duplicate_required_jobs(self):
		for name in merge_ci.REQUIRED_CHECKS:
			jobs = passing_jobs()
			selected = next(job for job in jobs if job["name"] == name)
			for changed in [[job for job in jobs if job["name"] != name], [*jobs, selected]]:
				with self.subTest(name=name, count=len(changed)):
					query = Mock(return_value=[{"jobs": changed}])
					with self.assertRaisesRegex(ValueError, f"exactly one {name}"):
						merge_ci.MainCI(query, REPO).verify(workflow_run())

	def test_rejects_required_jobs_without_successful_completion(self):
		for name in merge_ci.REQUIRED_CHECKS:
			for status, conclusion in [
				("queued", None),
				("in_progress", None),
				("completed", "failure"),
				("completed", "cancelled"),
				("completed", "skipped"),
				("completed", "neutral"),
			]:
				with self.subTest(name=name, status=status, conclusion=conclusion):
					jobs = copy.deepcopy(passing_jobs())
					selected = next(job for job in jobs if job["name"] == name)
					selected.update(status=status, conclusion=conclusion)
					query = Mock(return_value=[{"jobs": jobs}])
					with self.assertRaisesRegex(ValueError, f"job {name} did not succeed"):
						merge_ci.MainCI(query, REPO).verify(workflow_run())

	def test_times_out_without_run_or_with_pending_run(self):
		for runs in [[], [workflow_run(status="queued", conclusion=None)]]:
			with self.subTest(runs=runs):
				query = Mock(return_value=[{"workflow_runs": runs}])
				with self.assertRaisesRegex(TimeoutError, "--resume"):
					merge_ci.MainCI(query, REPO, timeout=5).wait(SHA)
				self.assertEqual(query.call_count, 2)

	def test_propagates_api_errors_without_reporting_success(self):
		error = subprocess.CalledProcessError(1, ["gh", "api"])
		query = Mock(side_effect=error)
		with self.assertRaises(subprocess.CalledProcessError):
			merge_ci.MainCI(query, REPO).wait(SHA)
		query.assert_called_once()

	def test_propagates_job_api_errors(self):
		query = Mock(
			side_effect=[
				[{"workflow_runs": [workflow_run()]}],
				subprocess.TimeoutExpired(["gh", "api"], 60),
			]
		)
		with self.assertRaises(subprocess.TimeoutExpired):
			merge_ci.MainCI(query, REPO).wait(SHA)


if __name__ == "__main__":
	unittest.main()
