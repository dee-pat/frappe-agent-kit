"""Exercise private publication and CI recovery without contacting GitHub."""

import contextlib
import io
import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from private_app_bootstrap.publish import Publisher
from private_app_bootstrap.state import Journal
from test_bootstrap_workflow import configuration

SHA = "a" * 40


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = configuration(self.root)
        self.journal = Journal(self.config)
        self.command = Mock()
        self.publisher = Publisher(
            self.config, self.journal, self.command, Mock(app=self.root)
        )
        self.journal.data["resources"].update(
            repository_id=10, setup_commit=SHA, pr_number=4
        )

    def test_existing_repository_is_not_adopted_without_recorded_identity(self):
        self.journal.data["resources"].pop("repository_id")
        self.command.run.return_value = subprocess.CompletedProcess([], 0, "{}", "")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.publisher.repository()
        self.command.json.assert_not_called()
        self.assertNotIn("repository_id", self.journal.data["resources"])

    def test_authentication_errors_are_not_treated_as_missing_repositories(self):
        self.journal.data["resources"].pop("repository_id")
        self.command.run.return_value = subprocess.CompletedProcess(
            [], 1, "", "HTTP 401 authentication failed"
        )
        self.command.redact.side_effect = lambda value: value
        with self.assertRaisesRegex(ValueError, "absence"):
            self.publisher.repository()
        self.command.json.assert_not_called()

    def test_confirmed_absence_creates_only_a_private_repository(self):
        self.journal.data["resources"].pop("repository_id")

        def command(args, **_options):
            if args[:2] == ["gh", "api"]:
                return subprocess.CompletedProcess(args, 1, "", "HTTP 404 Not Found")
            output = SHA if args[:3] == ["git", "rev-parse", "HEAD"] else ""
            return subprocess.CompletedProcess(args, 0, output, "")

        self.command.run.side_effect = command
        self.command.json.side_effect = [
            {"login": "example"},
            {"id": 10},
            {"private": True, "id": 10, "clone_url": "https://example.test/sample.git"},
        ]
        with self.journal.acquire(), patch.object(self.publisher, "verify_origin"):
            self.publisher.repository()
        creation = self.command.json.call_args_list[1].args[0]
        self.assertIn("private=true", creation)
        self.assertEqual(creation[3:5], ["POST", "user/repos"])
        self.assertEqual(self.journal.data["resources"]["repository_id"], 10)

    def test_resume_refuses_unrelated_staged_files_before_committing(self):
        def command(args, **_options):
            if args[:3] == ["git", "diff", "--cached"]:
                return subprocess.CompletedProcess(args, 0, "notes.py\0", "")
            if args[:2] == ["git", "push"]:
                raise AssertionError("Unrelated staged content reached publication")
            return subprocess.CompletedProcess(args, 0, "", "")

        self.journal.data["resources"].pop("setup_commit")
        self.journal.data["resources"]["initial_commit"] = SHA
        self.command.run.side_effect = command
        with (
            patch.object(self.publisher, "verify_repository"),
            patch.object(self.publisher, "verify_origin"),
        ):
            with self.assertRaisesRegex(ValueError, "unrelated"):
                self.publisher.pull_request()
        self.assertFalse(
            any(
                call.args[0][:2] == ["git", "commit"]
                for call in self.command.run.call_args_list
            )
        )

    def test_repository_must_remain_private_and_keep_its_recorded_id(self):
        for metadata in [{"private": False, "id": 10}, {"private": True, "id": 99}]:
            with self.subTest(metadata=metadata):
                self.command.json.return_value = metadata
                with self.assertRaisesRegex(ValueError, "not private|identity"):
                    self.publisher.verify_repository()

    def test_merged_pr_resumes_handoff_instead_of_merging_again(self):
        with (
            patch.object(self.publisher, "verify_repository"),
            patch.object(self.publisher, "verify_origin", create=True),
        ):
            self.command.json.return_value = {"state": "MERGED", "headRefOid": SHA}
            self.publisher.merge()
        args = self.command.run.call_args.args[0]
        self.assertEqual(args[:3], ["python3", "scripts/merge-pr.py", "4"])
        self.assertIn("--resume", args)
        self.assertNotIn("gh", args)

    def wait(self, checks, **changes):
        pr = {
            "state": "OPEN",
            "headRefOid": SHA,
            "statusCheckRollup": checks,
            **changes,
        }
        self.command.json.return_value = pr
        with patch(
            "private_app_bootstrap.pr_ci.time.monotonic",
            side_effect=itertools.chain([0, 0, 0], itertools.repeat(20)),
        ):
            with patch("private_app_bootstrap.pr_ci.time.sleep"):
                self.publisher.wait_pr("4")

    def test_pending_ci_times_out_without_merging(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(TimeoutError):
            self.wait([])
        self.command.run.assert_not_called()

    def test_failed_ci_or_changed_head_stops_without_merging(self):
        with self.assertRaisesRegex(ValueError, "CI failed"):
            self.wait(
                [{"name": "Lint", "status": "COMPLETED", "conclusion": "FAILURE"}]
            )
        with self.assertRaisesRegex(ValueError, "changed"):
            self.wait([], headRefOid="b" * 40)
        self.command.run.assert_not_called()

    def test_all_required_successes_allow_guarded_merge_to_proceed(self):
        checks = [
            {"name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}
            for name in ("Lint", "Agent kit", "Server")
        ]
        self.wait(checks)
        self.command.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
