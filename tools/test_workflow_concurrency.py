"""Pin a workflow's concurrency contract and exercise its event-context matrix.

Usage: python3 test_workflow_concurrency.py [-v] [WORKFLOW.yml ...]

Without paths it reads .github/workflows/ci.yml from the current directory, so
an app can copy this file into scripts/ unchanged.
"""

import re
import sys
import unittest
from pathlib import Path

WORKFLOWS = [Path(arg) for arg in sys.argv[1:] if arg.endswith((".yml", ".yaml"))]
sys.argv[1:] = [arg for arg in sys.argv[1:] if not arg.endswith((".yml", ".yaml"))]
WORKFLOWS = WORKFLOWS or [Path(".github/workflows/ci.yml")]

CONTEXTS = (
    ("pull_request", "refs/pull/42/merge", 42, 100),
    ("pull_request", "refs/pull/42/merge", 42, 101),
    ("pull_request", "refs/pull/43/merge", 43, 102),
    ("push", "refs/heads/main", None, 103),
    ("push", "refs/heads/main", None, 104),
    ("push", "refs/heads/version-16", None, 105),
    ("push", "refs/heads/version-16", None, 106),
    ("workflow_dispatch", "refs/heads/main", None, 107),
    ("workflow_dispatch", "refs/heads/main", None, 108),
    ("workflow_dispatch", "refs/heads/version-16", None, 109),
    ("workflow_dispatch", "refs/heads/version-16", None, 110),
)


class WorkflowConcurrencyTests(unittest.TestCase):
    def test_pr_supersession_and_independent_non_pr_runs(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=str(workflow)):
                source = workflow.read_text()
                name = re.search(r"^name: (.+)$", source, re.MULTILINE).group(1)
                group = re.search(r"^  group: (.+)$", source, re.MULTILINE).group(1)
                # Only superseded pull request runs cancel; push and manual runs keep their own group.
                cancel = re.search(r"^  cancel-in-progress: (.+)$", source, re.MULTILINE).group(1)
                self.assertEqual(cancel, "${{ github.event_name == 'pull_request' }}")
                groups = [
                    concurrency_group(
                        group,
                        {
                            "github": {
                                "workflow": name,
                                "event_name": event,
                                "ref": ref,
                                "run_id": run_id,
                                "sha": f"sha{run_id}",
                                "event": {"number": number, "pull_request": {"number": number}} if number else {},
                            }
                        },
                    )
                    for event, ref, number, run_id in CONTEXTS
                ]
                # The two runs of PR 42 share a group; every other run has its own.
                self.assertEqual(groups[0], groups[1])
                self.assertEqual(len(set(groups)), len(groups) - 1)


def concurrency_group(template, context):
    """Evaluate only context lookups and OR; missing event properties are empty.

    Fail on other syntax rather than pretend to implement the Actions engine.
    """

    def expression(match):
        for operand in match[1].split("||"):
            operand = operand.strip()
            if not re.fullmatch(r"github\.[A-Za-z_.]+", operand):
                raise AssertionError(f"Unsupported concurrency expression: {operand}")
            value = context
            for key in operand.split("."):
                value = value.get(key, "") if isinstance(value, dict) else ""
            if value:
                return str(value)
        return ""

    return re.sub(r"\$\{\{(.*?)\}\}", expression, template)


if __name__ == "__main__":
    unittest.main()
