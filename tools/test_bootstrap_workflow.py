"""Exercise bootstrap boundaries without live sites, repositories or network calls."""

import contextlib
import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from private_app_bootstrap.commands import Commands
from private_app_bootstrap.local import LocalSetup
from private_app_bootstrap.state import Journal
from private_app_bootstrap.workflow import PHASES, Bootstrap

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 40


def configuration(root):
    config = json.loads(
        (ROOT / "tools/private_app_bootstrap/versions.json").read_text()
    )
    config.update(
        app_name="sample_app",
        title="Sample App",
        module_name="sample_app",
        description="Example app",
        publisher="Example",
        email="dev@example.test",
        github_owner="example",
        repo_name="sample_app",
        bench_path=str(root / "bench"),
        dev_site="sample-dev.localhost",
        test_site="sample-test.localhost",
        kit_revision=SHA,
        license="mit",
        admin_password_env="BOOTSTRAP_TEST_ADMIN",
        db_root_password_env="BOOTSTRAP_TEST_DB",
        db_root_username="root",
        ci_timeout=10,
    )
    return config


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = configuration(self.root)

    def test_dry_run_cli_does_not_call_commands_or_create_resources(self):
        path = self.root / "configuration.json"
        path.write_text(json.dumps(self.config))
        before = {str(p.relative_to(self.root)) for p in self.root.rglob("*")}
        with patch.object(
            Commands, "run", side_effect=AssertionError("external command")
        ) as command:
            with patch.object(
                sys,
                "argv",
                ["bootstrap-private-app.py", "--config", str(path), "--dry-run"],
            ):
                with (
                    contextlib.redirect_stdout(io.StringIO()) as output,
                    self.assertRaises(SystemExit) as exit,
                ):
                    runpy.run_path(
                        str(ROOT / "tools/bootstrap-private-app.py"),
                        run_name="__main__",
                    )
        self.assertEqual(exit.exception.code, 0)
        self.assertIn("Dry-run", output.getvalue())
        command.assert_not_called()
        self.assertEqual(
            before, {str(p.relative_to(self.root)) for p in self.root.rglob("*")}
        )

    def test_failed_phase_is_journaled_and_resume_skips_completed_actions(self):
        workflow = Bootstrap(self.config, ROOT)
        methods = {
            "bench": (workflow.local, "bench_setup"),
            "app": (workflow.local, "scaffold"),
            "sites": (workflow.local, "sites"),
            "repository": (workflow.publisher, "repository"),
            "configure": (workflow.local, "configure"),
            "checks": (workflow.local, "checks"),
            "pull_request": (workflow.publisher, "pull_request"),
            "merge": (workflow.publisher, "merge"),
            "verify": (workflow.publisher, "verify_final"),
        }
        mocks = {}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(workflow, "preflight"))
            validation = stack.enter_context(patch.object(workflow, "revalidate"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            for phase, (owner, name) in methods.items():
                mocks[phase] = stack.enter_context(patch.object(owner, name))
            mocks["configure"].side_effect = ValueError("interrupted")
            with self.assertRaisesRegex(ValueError, "interrupted"):
                workflow.run()
            recorded = json.loads(workflow.j.path.read_text())
            self.assertEqual(recorded["current"], "configure")
            self.assertEqual(recorded["completed"], list(PHASES[:4]))
            mocks["configure"].side_effect = None
            workflow.run(resume=True)
        for phase in PHASES[:4]:
            self.assertEqual(mocks[phase].call_count, 1)
        self.assertEqual(mocks["configure"].call_count, 2)
        self.assertEqual(validation.call_count, 4)
        self.assertEqual(
            json.loads(workflow.j.path.read_text())["completed"], list(PHASES)
        )

    def test_resume_restarts_bench_redis_services(self):
        workflow = Bootstrap(self.config, ROOT)
        with (
            patch.object(workflow.local, "verify_bench") as verify,
            patch.object(workflow.local, "redis") as redis,
        ):
            workflow.revalidate("bench")
        verify.assert_called_once()
        redis.assert_called_once()

    def test_foreign_local_app_and_site_are_never_adopted(self):
        workflow = Bootstrap(self.config, ROOT)
        workflow.local.app.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "not owned"):
            workflow.local.scaffold()
        site = Path(self.config["bench_path"]) / "sites" / self.config["dev_site"]
        site.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "not owned"):
            workflow.local.sites()

    def test_generated_file_reconciles_before_after_but_preserves_user_edits(self):
        journal = Journal(self.config)
        local = LocalSetup(self.config, journal, Mock(), ROOT)
        local.app.mkdir(parents=True)
        target = local.app / "AGENTS.md"
        target.write_bytes(b"before")
        with journal.acquire():
            journal.data["files"]["AGENTS.md"] = {
                "before": hashlib.sha256(b"before").hexdigest(),
                "after": hashlib.sha256(b"after").hexdigest(),
            }
            journal.save()
            local.write_managed("AGENTS.md", b"after")
            local.write_managed("AGENTS.md", b"after")
            target.write_bytes(b"user changes")
            with self.assertRaisesRegex(ValueError, "changed"):
                local.write_managed("AGENTS.md", b"after")
        self.assertEqual(target.read_bytes(), b"user changes")

    def test_generated_files_refuse_symlink_ancestors(self):
        journal = Journal(self.config)
        local = LocalSetup(self.config, journal, Mock(), ROOT)
        local.app.mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        (local.app / "docs").symlink_to(outside, target_is_directory=True)
        with journal.acquire(), self.assertRaisesRegex(ValueError, "symlink"):
            local.write_managed("docs/guide.md", b"generated")
        self.assertEqual(list(outside.iterdir()), [])

    def test_preexisting_temporary_name_is_not_overwritten(self):
        journal = Journal(self.config)
        local = LocalSetup(self.config, journal, Mock(), ROOT)
        local.app.mkdir(parents=True)
        existing = local.app / "AGENTS.md.bootstrap-tmp"
        existing.write_bytes(b"user file")
        with journal.acquire():
            local.write_managed("AGENTS.md", b"generated")
        self.assertEqual(existing.read_bytes(), b"user file")
        self.assertEqual((local.app / "AGENTS.md").read_bytes(), b"generated")

    def test_resume_refuses_owned_app_or_site_replaced_by_symlink(self):
        workflow = Bootstrap(self.config, ROOT)
        outside = self.root / "outside"
        outside.mkdir()
        workflow.local.app.parent.mkdir(parents=True)
        workflow.local.app.symlink_to(outside, target_is_directory=True)
        workflow.j.data["resources"]["app"] = True
        with self.assertRaisesRegex(ValueError, "symlink"):
            workflow.local.scaffold()
        site = workflow.local.bench / "sites" / self.config["dev_site"]
        site.parent.mkdir()
        site.symlink_to(outside, target_is_directory=True)
        workflow.j.data["resources"][f"site:{self.config['dev_site']}"] = True
        with self.assertRaisesRegex(ValueError, "symlink"):
            workflow.local.sites()

    def test_secrets_are_redacted_and_not_in_child_environment(self):
        with patch.dict(
            os.environ,
            {"BOOTSTRAP_TEST_ADMIN": "admin-secret", "BOOTSTRAP_TEST_DB": "db-secret"},
        ):
            command = Commands(self.config, Journal(self.config))
        self.assertNotIn("BOOTSTRAP_TEST_ADMIN", command.env)
        self.assertNotIn("BOOTSTRAP_TEST_DB", command.env)
        failure = subprocess.CompletedProcess(["tool"], 1, "", "admin-secret db-secret")
        with patch(
            "private_app_bootstrap.commands.subprocess.run", return_value=failure
        ):
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaises(ValueError) as raised,
            ):
                command.run(["tool"])
        self.assertNotIn("admin-secret", str(raised.exception))
        self.assertNotIn("db-secret", str(raised.exception))
        self.assertIn("<redacted>", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
