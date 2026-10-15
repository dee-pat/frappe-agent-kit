"""Exercise sync-skills.sh against a local pinned repository in temporary apps."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RULES_BEGIN = "<!-- BEGIN synced-rules: acme/kit/rules/shared.md@"
RULES_END = "<!-- END synced-rules: acme/kit/rules/shared.md -->"


def git(*args, cwd):
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Sync Test",
            "-c",
            "user.email=sync-test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class SyncSkillsTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="bond-sync-skills-")
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)

        self.remote = root / "remotes" / "acme" / "kit.git"
        (self.remote / "skills" / "demo" / "evals").mkdir(parents=True)
        (self.remote / "rules").mkdir()
        (self.remote / "skills" / "demo" / "SKILL.md").write_text("pinned skill\n")
        (self.remote / "skills" / "demo" / "evals" / "case.md").write_text("excluded\n")
        (self.remote / "rules" / "shared.md").write_text("pinned rule\n")
        git("init", "-q", cwd=self.remote)
        git("add", "-A", cwd=self.remote)
        git("commit", "-q", "-m", "pin", cwd=self.remote)
        self.revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.remote, check=True, capture_output=True, text=True
        ).stdout.strip()

        self.app = root / "bench" / "apps" / "demo"
        (self.app / "scripts").mkdir(parents=True)
        (self.app / ".agents" / "skills").mkdir(parents=True)
        # The script sits beside this test in both the app and the kit.
        script = Path(__file__).resolve().parent / "sync-skills.sh"
        shutil.copy2(script, self.app / "scripts" / "sync-skills.sh")
        (self.app / "skills.lock").write_text(
            f"demo  acme/kit  skills/demo      {self.revision}  evals\n"
            f"rule  acme/kit  rules/shared.md  {self.revision}  AGENTS.md\n"
        )
        (self.app / "AGENTS.md").write_text(
            f"# Demo\n\n{RULES_BEGIN}unsynced -->\n{RULES_END}\n\nApp rule.\n"
        )

        self.cache = root / "cache"
        self.remote_base = f"file://{root / 'remotes'}"

    def run_sync(self, mode, remote_base=None):
        environment = os.environ | {
            "AGENT_SKILLS_CACHE": str(self.cache),
            "AGENT_SKILLS_REMOTE_BASE": remote_base or self.remote_base,
        }
        return subprocess.run(
            ["bash", str(self.app / "scripts" / "sync-skills.sh"), mode],
            cwd=self.app,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
        )

    def cache_entry(self):
        return self.cache / "acme" / "kit" / self.revision

    def vendored_skill(self):
        return self.app / ".agents" / "skills" / "demo"

    def test_sync_vendors_pinned_files_and_check_passes(self):
        result = self.run_sync("sync")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.vendored_skill() / "SKILL.md").read_text(), "pinned skill\n")
        self.assertFalse((self.vendored_skill() / "evals").exists())
        agents = (self.app / "AGENTS.md").read_text()
        self.assertIn(f"{RULES_BEGIN}{self.revision} -->\npinned rule\n{RULES_END}", agents)
        self.assertTrue(agents.endswith("App rule.\n"))

        result = self.run_sync("check")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_check_fails_when_a_vendored_copy_is_edited(self):
        self.assertEqual(self.run_sync("sync").returncode, 0)
        (self.vendored_skill() / "SKILL.md").write_text("edited\n")
        agents = self.app / "AGENTS.md"
        agents.write_text(agents.read_text().replace("pinned rule", "edited rule"))

        result = self.run_sync("check")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("drift demo", result.stdout)
        self.assertIn("drift rules acme/kit/rules/shared.md", result.stdout)

    def test_dirty_cached_worktree_never_reaches_vendored_copies(self):
        self.assertEqual(self.run_sync("sync").returncode, 0)
        # Older script versions left a worktree in the cache; edit and delete
        # pinned files there.
        git("checkout", "-q", "--detach", self.revision, cwd=self.cache_entry())
        (self.cache_entry() / "skills" / "demo" / "SKILL.md").write_text("tampered\n")
        (self.cache_entry() / "rules" / "shared.md").unlink()
        shutil.rmtree(self.vendored_skill())

        result = self.run_sync("sync")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.vendored_skill() / "SKILL.md").read_text(), "pinned skill\n")
        self.assertIn("pinned rule\n", (self.app / "AGENTS.md").read_text())
        self.assertEqual(self.run_sync("check").returncode, 0)

    def test_failed_fetch_caches_nothing(self):
        result = self.run_sync("check", remote_base=f"file://{self.cache.parent / 'missing'}")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("nothing was cached", result.stdout)
        self.assertFalse(self.cache_entry().exists())

        self.assertEqual(self.run_sync("sync").returncode, 0)

    def test_broken_cache_entry_is_replaced(self):
        self.cache_entry().mkdir(parents=True)
        git("init", "-q", cwd=self.cache_entry())

        result = self.run_sync("sync")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.vendored_skill() / "SKILL.md").read_text(), "pinned skill\n")


if __name__ == "__main__":
    unittest.main()
