"""Verify rendered private-app assets before bootstrap writes or publishes them."""

import ast
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from private_app_bootstrap.render import KIT_TOOLS, render

ROOT = Path(__file__).resolve().parent.parent
PINS = {
    "kit_revision": "a" * 40,
    "skills_revision": "b" * 40,
    "semgrep_revision": "c" * 40,
}


def config(app_name="orbit_tracker", title="Orbit Tracker"):
    return {
        "app_name": app_name,
        "title": title,
        "module_name": title.lower().replace(" ", "_"),
        "description": "Example private application",
        "publisher": "Example Maintainer",
        "email": "maintainer@example.com",
        "license": "mit",
        "github_owner": "example",
        "repo_name": app_name,
        "dev_site": f"{app_name}-dev.localhost",
        "test_site": f"{app_name}-test.localhost",
        "frappe_version": "v16.51.0",
        "bench_version": "5.31.0",
        "python_version": "3.14",
        "node_version": "24",
        "semgrep_version": "1.172.0",
        "precommit_version": "4.3.0",
        **PINS,
    }


class RenderTests(unittest.TestCase):
    def test_two_distinct_apps_render_without_reference_identity(self):
        for values in [config(), config("water_meter", "WaterMeter")]:
            with self.subTest(app=values["app_name"]):
                before = copy.deepcopy(values)
                files = render(values, ROOT)
                self.assertEqual(values, before)
                for name, data in files.items():
                    self.assertFalse(Path(name).is_absolute())
                    self.assertNotIn("..", Path(name).parts)
                    self.assertIsNone(re.search(rb"__[A-Z][A-Z0-9_]*__", data), name)
                    for reference in (
                        b"SolarModel",
                        b"solar_model",
                        b"solar-model",
                        b"SOLARMODEL_ROOT",
                    ):
                        self.assertNotIn(reference, data, name)
                self.assertIn(f"{values['app_name']}/tests/test_installation.py", files)
                self.assertIn(f".codex/rules/{values['app_name']}.rules", files)
                self.assertIn(values["title"].encode(), files["AGENTS.md"])
                self.assertIn(values["module_name"].encode(), files["AGENTS.md"])

    def test_all_generated_python_json_and_yaml_parse(self):
        for name, data in render(config(), ROOT).items():
            with self.subTest(path=name):
                if name.endswith(".py"):
                    ast.parse(data, filename=name)
                elif name.endswith(".json"):
                    json.loads(data)
                elif name.endswith((".yml", ".yaml")):
                    yaml.safe_load(data)

    def test_ci_contains_pinned_tools_and_exact_job_names(self):
        values = config()
        files = render(values, ROOT)
        workflow = yaml.load(files[".github/workflows/ci.yml"], Loader=yaml.BaseLoader)
        self.assertEqual(
            {job["name"] for job in workflow["jobs"].values()},
            {"Lint", "Agent kit", "Server"},
        )
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["env"]["SITE"], values["test_site"])
        self.assertEqual(workflow["env"]["FRAPPE_VERSION"], values["frappe_version"])
        text = files[".github/workflows/ci.yml"].decode()
        for version in (
            "frappe-bench==5.31.0",
            "pre-commit==4.3.0",
            "semgrep==1.172.0",
        ):
            self.assertIn(version, text)
        self.assertIn('python-version: "3.14"', text)
        self.assertIn("node-version: 24", text)
        self.assertIn("bench --site", text)
        self.assertNotIn("--no-verify", text)

    def test_kit_tools_are_byte_identical_and_skills_use_full_pins(self):
        files = render(config(), ROOT)
        for name in KIT_TOOLS:
            self.assertEqual(
                files[f"scripts/{name}"], (ROOT / "tools" / name).read_bytes()
            )
        lock = files["skills.lock"].decode()
        rows = [
            line.split()
            for line in lock.splitlines()
            if line and not line.startswith("#")
        ]
        self.assertEqual(
            len([row for row in rows if row[0] not in {"rule", "vendor"}]), 9
        )
        for row in rows:
            self.assertRegex(row[3], r"^[0-9a-f]{40}$")
        self.assertIn(f"rules/frappe.md {PINS['kit_revision']} AGENTS.md", lock)
        self.assertIn(
            f"rules/frappe.md@{PINS['kit_revision']}", files["AGENTS.md"].decode()
        )
        for target in ("docs/pull-requests.md", ".github/pull_request_template.md"):
            self.assertIn(PINS["kit_revision"].encode(), files[target])

    def test_smoke_test_uses_correct_installed_module(self):
        values = config()
        source = render(values, ROOT)[
            f"{values['app_name']}/tests/test_installation.py"
        ].decode()
        self.assertIn(f'get_doc("Module Def", "{values["title"]}")', source)
        self.assertIn(
            f'self.assertEqual(module.app_name, "{values["app_name"]}")', source
        )
        self.assertIn("IntegrationTestCase", source)

    def test_protection_rules_use_the_configured_sites(self):
        values = config()
        files = render(values, ROOT)
        claude = json.loads(files[".claude/settings.json"])
        codex = files[f".codex/rules/{values['app_name']}.rules"].decode()
        for site in (values["dev_site"], values["test_site"]):
            self.assertIn(site, codex)
            self.assertTrue(any(site in rule for rule in claude["permissions"]["deny"]))
        self.assertIn("site_config.json", json.dumps(claude))

    def test_rejects_unsafe_package_names_and_mutable_pins(self):
        for key, value in [
            ("app_name", "../outside"),
            ("kit_revision", "main"),
            ("skills_revision", "v1"),
        ]:
            with self.subTest(key=key):
                values = config()
                values[key] = value
                with self.assertRaises(ValueError):
                    render(values, ROOT)
        values = config()
        values["title"] = "First\nSecond"
        with self.assertRaises(ValueError):
            render(values, ROOT)

    def test_rejects_unknown_tokens_in_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = Path(directory)
            (kit / "templates/private-app").mkdir(parents=True)
            (kit / "templates/private-app/AGENTS.md").write_text("__UNKNOWN_TOKEN__")
            with self.assertRaisesRegex(ValueError, "Unresolved"):
                render(config(), kit)

    def test_sync_preserves_precomputed_rule_hashes_for_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for relative in (
                "rules/frappe.md",
                "templates/pull-requests.md",
                "templates/pull_request_template.md",
            ):
                destination = source / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.test",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-qm",
                    "Fixture",
                ],
                check=True,
            )
            sha = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip()
            cache = root / "cache"
            checkout = cache / "dee-pat/frappe-agent-kit" / sha
            checkout.parent.mkdir(parents=True)
            subprocess.run(
                ["git", "clone", "-q", str(source), str(checkout)], check=True
            )
            values = config()
            values["kit_revision"] = sha
            files = render(values, ROOT)
            app = root / "bench/apps/example"
            for name, data in files.items():
                target = app / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            rules = [
                line
                for line in files["skills.lock"].decode().splitlines()
                if line.startswith("rule ")
            ]
            (app / "skills.lock").write_text("\n".join(rules) + "\n")
            environment = dict(os.environ, AGENT_SKILLS_CACHE=str(cache))
            subprocess.run(
                ["bash", str(app / "scripts/sync-skills.sh"), "sync"],
                cwd=app,
                env=environment,
                check=True,
                capture_output=True,
            )
            for name in (
                "AGENTS.md",
                "docs/pull-requests.md",
                ".github/pull_request_template.md",
            ):
                self.assertEqual((app / name).read_bytes(), files[name])

    def test_generated_merge_guard_regression_suite_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            for name, data in render(config(), ROOT).items():
                target = app / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for test in (
                "test_merge_safeguards.py",
                "test_merge_checkout.py",
                "test_merge_ci.py",
                "test_merge_workflow.py",
            ):
                result = subprocess.run(
                    [sys.executable, str(app / "scripts" / test)],
                    cwd=app,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
