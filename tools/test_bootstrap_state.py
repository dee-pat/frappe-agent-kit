"""Test configuration and restart journals without external services."""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from private_app_bootstrap.config import load_config
from private_app_bootstrap.state import Journal


class BootstrapStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.kit = self.root / "kit"
        self.kit.mkdir()
        subprocess.run(["git", "init", "-q", str(self.kit)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.kit),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--allow-empty",
                "-qm",
                "Fixture",
            ],
            check=True,
        )
        self.input = self.root / "config.json"
        self.values = {
            "app_name": "sample_app",
            "title": "Sample App",
            "description": "A sample app",
            "publisher": "Example",
            "email": "dev@example.com",
            "github_owner": "example",
            "bench_path": str(self.root / "bench"),
        }
        self.write_config()

    def write_config(self, changes=None):
        self.input.write_text(json.dumps({**self.values, **(changes or {})}))

    def config(self):
        return load_config(self.input, self.kit)

    def test_defaults_are_pinned_and_loading_is_read_only(self):
        before = set(self.root.rglob("*"))
        config = self.config()
        self.assertEqual(config["frappe_version"], "v16.51.0")
        self.assertEqual(config["bench_version"], "5.31.0")
        self.assertEqual(config["python_version"], "3.14.6")
        self.assertEqual(config["repo_name"], "sample_app")
        self.assertEqual(config["module_name"], "sample_app")
        self.assertEqual(config["dev_site"], "sample-app-dev.localhost")
        self.assertEqual(config["test_site"], "sample-app-test.localhost")
        self.assertRegex(config["kit_revision"], r"^[a-f0-9]{40}$")
        self.assertEqual(before, set(self.root.rglob("*")))
        json.dumps(config)

    def test_explicit_pins_and_sites_are_retained(self):
        self.write_config(
            {
                "kit_revision": "a" * 40,
                "frappe_version": "v16.52.1",
                "dev_site": "reader-dev.localhost",
                "test_site": "reader-test.localhost",
            }
        )
        config = self.config()
        self.assertEqual(config["kit_revision"], "a" * 40)
        self.assertEqual(config["frappe_version"], "v16.52.1")
        self.assertEqual(config["dev_site"], "reader-dev.localhost")

    def test_rejects_unknown_keys_and_raw_passwords(self):
        for key in ["unknown", "admin_password", "db_root_password"]:
            with self.subTest(key=key):
                self.write_config({key: "secret"})
                with self.assertRaisesRegex(ValueError, "Unknown configuration"):
                    self.config()

    def test_rejects_invalid_types_names_and_mutable_versions(self):
        invalid = {
            "app_name": [True, [], "../app", "Sample", "sample-app", "--app"],
            "title": [False, "bad/title", "1st App"],
            "github_owner": ["--owner", "owner/repo", "owner_"],
            "repo_name": ["../name", "--repo", "/name"],
            "email": ["invalid", "user@host", "user @example.com"],
            "bench_path": ["relative/bench", False],
            "license": ["unknown"],
            "frappe_version": ["main", "version-16", "v17.0.0"],
            "bench_version": ["latest", "5.31"],
            "python_version": ["3.13", "latest"],
            "node_version": ["lts", "24.x"],
            "kit_revision": ["main", "a" * 39],
            "skills_revision": ["latest", "A" * 40],
            "semgrep_revision": ["abc"],
            "admin_password_env": ["secret-value", "ENV\nOTHER"],
            "ci_timeout": [True, "1800", 0, -1],
            "module_name": ["unrelated"],
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.write_config({key: value})
                    with self.assertRaises(ValueError):
                        self.config()

    def test_rejects_control_characters_and_site_collisions(self):
        for key in ["publisher", "description", "title", "email"]:
            self.write_config({key: "valid\nN\n--force"})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.config()
        self.write_config({"dev_site": "same.localhost", "test_site": "same.localhost"})
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.config()

    def test_required_fields_and_object_shape(self):
        for value in [[], False, None, {"app_name": "only"}]:
            self.input.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.config()

    def test_constructor_does_not_create_state(self):
        journal = Journal(self.config())
        self.assertFalse(journal.path.exists())
        self.assertFalse(journal.directory.exists())
        with self.assertRaisesRegex(ValueError, "Acquire"):
            journal.save()

    def test_failed_phase_can_resume_without_storing_secrets(self):
        config = self.config()
        journal = Journal(config)
        with patch.dict(
            os.environ, {config["admin_password_env"]: "test-secret-value"}
        ):
            with self.assertRaisesRegex(RuntimeError, "Interrupted"):
                with journal.acquire():
                    journal.start("app")
                    journal.data["resources"]["app"] = "owned"
                    journal.save()
                    raise RuntimeError("Interrupted")
        self.assertNotIn("test-secret-value", journal.path.read_text())
        resumed = Journal(config)
        with resumed.acquire(resume=True):
            self.assertEqual(resumed.data["current"], "app")
            self.assertFalse(resumed.done("app"))
            resumed.complete("app")
            resumed.complete("app")
            self.assertEqual(resumed.data["completed"], ["app"])
        self.assertEqual(stat.S_IMODE(journal.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(journal.directory.stat().st_mode), 0o700)

    def test_resume_requires_existing_matching_schema_and_inputs(self):
        config = self.config()
        journal = Journal(config)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            with journal.acquire(resume=True):
                pass
        with journal.acquire():
            journal.complete("bench")
        with self.assertRaisesRegex(ValueError, "already exists"):
            with Journal(config).acquire():
                pass
        changed = {**config, "title": "Changed"}
        with self.assertRaisesRegex(ValueError, "differs"):
            with Journal(changed).acquire(resume=True):
                pass
        original = journal.path.read_text()
        for invalid in [[], {"schema_version": 2}, {**journal.data, "resources": []}]:
            journal.path.write_text(json.dumps(invalid))
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                with Journal(config).acquire(resume=True):
                    pass
        journal.path.write_text(original)

    def test_lock_serializes_apps_sharing_the_same_bench(self):
        config = self.config()
        first = Journal(config)
        other = Journal({**config, "app_name": "other_app"})
        with first.acquire():
            with self.assertRaisesRegex(ValueError, "bench lock"):
                with other.acquire():
                    pass
        with other.acquire():
            self.assertFalse(other.done("bench"))

    def test_atomic_write_preserves_previous_state_when_replace_fails(self):
        journal = Journal(self.config())
        with journal.acquire():
            before = journal.path.read_bytes()
            with patch(
                "private_app_bootstrap.state.os.replace",
                side_effect=OSError("disk error"),
            ):
                with self.assertRaises(OSError):
                    journal.start("app")
            self.assertEqual(journal.path.read_bytes(), before)
            self.assertFalse(list(journal.directory.glob(f".{journal.path.name}.*")))

    def test_journal_and_registry_symlinks_are_rejected(self):
        config = self.config()
        journal = Journal(config)
        target = self.root / "unrelated"
        target.mkdir()
        journal.directory.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            with journal.acquire():
                pass
        journal.directory.unlink()
        journal.directory.mkdir()
        journal.path.symlink_to(self.input)
        before = self.input.read_bytes()
        with self.assertRaisesRegex(ValueError, "symlink"):
            with journal.acquire():
                pass
        self.assertEqual(self.input.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
