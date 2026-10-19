"""Keep the kit's default GitHub PR template aligned with its shared source."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PrTemplateTests(unittest.TestCase):
    def test_default_template_matches_shared_source(self):
        self.assertEqual(
            (ROOT / ".github/pull_request_template.md").read_bytes(),
            (ROOT / "templates/pull_request_template.md").read_bytes(),
            "Refresh the default GitHub template from templates/pull_request_template.md",
        )


if __name__ == "__main__":
    unittest.main()
