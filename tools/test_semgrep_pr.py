"""Exercise semgrep-pr.sh against a temporary app repository.

Needs Semgrep: set SEMGREP_BIN, or put semgrep on PATH (for example the bench's
env/bin). The tests are skipped, not passed, when it is unavailable.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SEMGREP = os.environ.get("SEMGREP_BIN") or shutil.which("semgrep")

RULE = """rules:
  - id: no-commit
    languages: [python]
    message: Do not commit inside a request.
    pattern: frappe.db.commit()
    severity: ERROR
"""


def git(*args, cwd):
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Semgrep Test",
            "-c",
            "user.email=semgrep-test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@unittest.skipUnless(SEMGREP, "Semgrep is unavailable; set SEMGREP_BIN")
class SemgrepPrTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="semgrep-pr-")
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)

        self.app = root / "bench" / "apps" / "demo"
        (self.app / "scripts").mkdir(parents=True)
        (self.app / "semgrep" / "frappe").mkdir(parents=True)
        shutil.copy2(Path(__file__).resolve().parent / "semgrep-pr.sh", self.app / "scripts" / "semgrep-pr.sh")
        (self.app / "semgrep" / "frappe" / "rules.yml").write_text(RULE)
        (self.app / "debt.py").write_text("import frappe\n\nfrappe.db.commit()\n")
        git("init", "-q", "-b", "main", cwd=self.app)
        git("add", "-A", cwd=self.app)
        git("commit", "-q", "-m", "base", cwd=self.app)

        git("switch", "-q", "-c", "feature", cwd=self.app)
        (self.app / "change.py").write_text("import frappe\n\n\ndef save():\n    frappe.db.commit()\n")
        git("add", "-A", cwd=self.app)
        git("commit", "-q", "-m", "change", cwd=self.app)

    def run_script(self, *args):
        return subprocess.run(
            [str(self.app / "scripts" / "semgrep-pr.sh"), *args],
            cwd=self.app,
            env=os.environ | {"SEMGREP_BIN": SEMGREP},
            capture_output=True,
            text=True,
        )

    def test_reports_only_findings_the_change_introduces(self):
        result = self.run_script("main")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("change.py", result.stdout)
        self.assertNotIn("debt.py", result.stdout)
        self.assertIn("1 new finding(s)", result.stdout)

    def test_fail_on_new_sets_the_exit_status(self):
        self.assertEqual(self.run_script("--fail-on-new", "main").returncode, 1)
        self.assertEqual(self.run_script("--fail-on-new", "main", "main").returncode, 0)

    def test_measures_from_the_merge_base(self):
        # A finding added on the base branch after the fork is not the PR's.
        git("switch", "-q", "main", cwd=self.app)
        (self.app / "later.py").write_text("import frappe\n\nfrappe.db.commit()\n")
        git("add", "-A", cwd=self.app)
        git("commit", "-q", "-m", "later", cwd=self.app)
        git("switch", "-q", "feature", cwd=self.app)

        result = self.run_script("main")

        self.assertNotIn("later.py", result.stdout)
        self.assertIn("1 new finding(s)", result.stdout)

    def test_leaves_the_checkout_untouched(self):
        (self.app / "change.py").write_text("uncommitted\n")
        (self.app / "untracked.py").write_text("import frappe\n\nfrappe.db.commit()\n")
        status_before = git("status", "--porcelain", cwd=self.app)

        result = self.run_script("main")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uncommitted changes are not scanned", result.stderr)
        self.assertIn("1 new finding(s)", result.stdout)
        self.assertNotIn("untracked.py", result.stdout)
        self.assertEqual(git("status", "--porcelain", cwd=self.app), status_before)
        self.assertEqual((self.app / "change.py").read_text(), "uncommitted\n")
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.app), "feature")

    def test_writes_json_copy(self):
        output = self.app.parent / "results.json"

        self.assertEqual(self.run_script("--json", str(output), "main").returncode, 0)

        results = json.loads(output.read_text())["results"]
        self.assertEqual([finding["path"] for finding in results], ["change.py"])

    def test_rejects_unknown_revision(self):
        result = self.run_script("no-such-branch")

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown revision", result.stderr)


if __name__ == "__main__":
    unittest.main()
