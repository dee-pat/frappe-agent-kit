"""Pin a workflow's concurrency contract and exercise its event-context matrix.

Usage: python3 test_workflow_concurrency.py [-v] [WORKFLOW.yml ...]

A workflow triggered only by pull_request may group by ref and always cancel;
any other trigger mix must cancel only pull request runs and give every push,
scheduled and manual run its own group.

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
    ("schedule", "refs/heads/main", None, 111),
    ("schedule", "refs/heads/main", None, 112),
)


class WorkflowConcurrencyTests(unittest.TestCase):
    def test_pr_supersession_and_independent_non_pr_runs(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=str(workflow)):
                check_workflow(self, workflow.read_text())


class CheckWorkflowTests(unittest.TestCase):
    """Pin the checker itself on inline workflows, independent of the paths given."""

    HEADER = "name: Example\n\non:\n{on}\npermissions:\n  contents: read\n\n"

    def workflow(self, on, group, cancel):
        concurrency = f"concurrency:\n  group: {group}\n  cancel-in-progress: {cancel}\n"
        return self.HEADER.format(on=on) + concurrency

    def assert_fails(self, source):
        with self.assertRaises(AssertionError):
            check_workflow(self, source)

    def test_pull_request_only_workflow_may_group_by_ref(self):
        for cancel in ("true", "${{ github.event_name == 'pull_request' }}"):
            with self.subTest(cancel=cancel):
                check_workflow(self, self.workflow("  pull_request:\n", "${{ github.workflow }}-${{ github.ref }}", cancel))

    def test_pull_request_only_inline_trigger_forms(self):
        for on in (" pull_request\n", " [pull_request]\n"):
            with self.subTest(on=on):
                source = self.workflow("", "${{ github.workflow }}-${{ github.ref }}", "true").replace("on:\n", f"on:{on}")
                self.assertEqual(triggers(source), {"pull_request"})
                check_workflow(self, source)

    def test_pull_request_only_workflow_must_separate_pull_requests(self):
        self.assert_fails(self.workflow("  pull_request:\n", "${{ github.workflow }}", "true"))

    def test_pull_request_only_workflow_must_cancel_superseded_runs(self):
        self.assert_fails(self.workflow("  pull_request:\n", "${{ github.workflow }}-${{ github.ref }}", "false"))

    def test_mixed_trigger_workflow_grouped_by_ref_fails(self):
        on = "  schedule:\n    - cron: \"17 2 * * *\"\n  workflow_dispatch:\n  pull_request:\n"
        for cancel in ("true", "${{ github.event_name == 'pull_request' }}"):
            with self.subTest(cancel=cancel):
                self.assert_fails(self.workflow(on, "${{ github.workflow }}-${{ github.ref }}", cancel))

    def test_commented_triggers_do_not_count(self):
        on = "  schedule:\n    - cron: \"17 2 * * *\"\n  # pull_request:\n  #   paths:\n"
        source = self.workflow(on, "${{ github.workflow }}-${{ github.ref }}", "true")
        self.assertEqual(triggers(source), {"schedule"})
        self.assert_fails(source)

    def test_mixed_trigger_workflow_grouped_by_run_passes(self):
        on = "  schedule:\n    - cron: \"17 2 * * *\"\n  workflow_dispatch:\n  pull_request:\n"
        group = "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
        check_workflow(self, self.workflow(on, group, "${{ github.event_name == 'pull_request' }}"))


def triggers(source):
    """Return the event names under the top-level `on:` key, ignoring comments."""
    match = re.search(r"^on:(.*)$", source, re.MULTILINE)
    inline = match.group(1).split("#")[0].strip()
    if inline:
        return {event.strip() for event in inline.strip("[]").split(",")}
    events = set()
    for line in source[match.end() :].splitlines()[1:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        if event := re.match(r"^  ([A-Za-z_]+):", line):
            events.add(event.group(1))
    return events


def check_workflow(test, source):
    name = re.search(r"^name: (.+)$", source, re.MULTILINE).group(1)
    group = re.search(r"^  group: (.+)$", source, re.MULTILINE).group(1)
    cancel = re.search(r"^  cancel-in-progress: (.+)$", source, re.MULTILINE).group(1)
    pull_request_only = triggers(source) == {"pull_request"}
    if pull_request_only:
        # Every run is a pull request run, so grouping by ref and always cancelling is correct.
        test.assertIn(cancel, ("true", "${{ github.event_name == 'pull_request' }}"))
        contexts = [context for context in CONTEXTS if context[0] == "pull_request"]
    else:
        # Only superseded pull request runs cancel; push, scheduled and manual runs keep their own group.
        test.assertEqual(cancel, "${{ github.event_name == 'pull_request' }}")
        contexts = CONTEXTS
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
        for event, ref, number, run_id in contexts
    ]
    # The two runs of PR 42 share a group; every other run has its own.
    test.assertEqual(groups[0], groups[1])
    test.assertEqual(len(set(groups)), len(groups) - 1)


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
