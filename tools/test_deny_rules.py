"""Check that every Codex deny prefix has a matching Claude Code deny rule.

Usage: python3 test_deny_rules.py [-v] [CODEX.rules ...] [CLAUDE_SETTINGS.json]

Without paths it reads .codex/rules/*.rules and .claude/settings.json from the
current directory, so an app can copy this file into scripts/ unchanged.
"""

import json
import re
import sys
import unittest
from pathlib import Path

CODEX_RULES = [Path(arg) for arg in sys.argv[1:] if arg.endswith(".rules")]
CLAUDE_SETTINGS = [Path(arg) for arg in sys.argv[1:] if arg.endswith(".json")]
sys.argv[1:] = [arg for arg in sys.argv[1:] if not arg.endswith((".rules", ".json"))]
CODEX_RULES = CODEX_RULES or sorted(Path(".codex/rules").glob("*.rules"))
CLAUDE_SETTINGS = CLAUDE_SETTINGS[0] if CLAUDE_SETTINGS else Path(".claude/settings.json")


class DenyRuleSyncTests(unittest.TestCase):
    def test_every_codex_prefix_has_a_claude_rule(self):
        self.assertTrue(CODEX_RULES, "no Codex rules file found")
        codex = set()
        for path in CODEX_RULES:
            rules = path.read_text()
            patterns = re.findall(r"pattern = (\[.*?\])", rules)
            count = rules.count("prefix_rule(")
            self.assertEqual(len(patterns), count, path)
            # Codex checks match and not_match examples when it loads the rules.
            self.assertEqual(len(re.findall(r"^\s*match = \[", rules, re.MULTILINE)), count, path)
            self.assertEqual(len(re.findall(r"^\s*not_match = \[", rules, re.MULTILINE)), count, path)
            codex |= {" ".join(json.loads(pattern)) for pattern in patterns}
        deny = json.loads(CLAUDE_SETTINGS.read_text())["permissions"]["deny"]
        # A trailing " *" also matches the bare command, so the rule covers the prefix:
        # https://code.claude.com/docs/en/permissions#wildcard-patterns
        claude = {rule[len("Bash(") : -1].removesuffix(" *") for rule in deny if rule.startswith("Bash(")}
        self.assertEqual(codex - claude, set())


if __name__ == "__main__":
    unittest.main()
