"""Check that relative Markdown links, their anchors and named skills resolve.

Usage: python3 test_doc_links.py [-v]

Copied into an app's scripts/ and run from its lint gate. Paths are relative to
the repository root (the parent of this file's directory), so it runs from any
directory. It checks:

1. every relative link in the root, nested (`*/AGENTS.md`) and `docs/*.md`
   guidance points to an existing file;
2. every `#anchor` matches a heading in the target file (GitHub slug rules);
3. every skill named in backticks in the `## Read by task` table of the root
   `AGENTS.md` exists under `.agents/skills/`. Skipped when there is no table.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    path
    for pattern in ("AGENTS.md", "*/AGENTS.md", "docs/*.md")
    for path in sorted(ROOT.glob(pattern))
    if "node_modules" not in path.parts
]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"#{1,6}\s+(.+?)\s*#*$")


def prose_lines(path):
    """Yield (number, line) outside fenced code blocks."""
    in_fence = False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            yield number, line


def slug(heading):
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path):
    """Yield each heading's anchor, numbering repeats as GitHub does."""
    seen = {}
    for _, line in prose_lines(path):
        if match := HEADING.match(line):
            base = slug(match.group(1))
            count = seen.get(base, 0)
            seen[base] = count + 1
            yield base if count == 0 else f"{base}-{count}"


def broken_links(docs):
    """Return one message per relative link whose file or anchor is missing."""
    broken = []
    for doc in docs:
        for number, line in prose_lines(doc):
            for target in LINK.findall(line):
                if re.match(r"[a-z][a-z0-9+.-]*:", target):
                    continue
                file_part, _, anchor = target.partition("#")
                path = (doc.parent / file_part).resolve() if file_part else doc
                where = f"{doc.relative_to(ROOT)}:{number}: {target}"
                if not path.exists():
                    broken.append(f"{where} (missing file)")
                elif anchor and path.suffix == ".md" and anchor not in set(anchors(path)):
                    broken.append(f"{where} (missing anchor)")
    return broken


def read_by_task_skills(agents_md):
    """Return the skill names in backticks inside the Read by task table."""
    parts = agents_md.read_text().split("## Read by task", 1)
    if len(parts) == 1:
        return set()
    rows = [line for line in parts[1].split("\n## ", 1)[0].splitlines() if line.startswith("|")]
    return {name for row in rows for name in re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`", row)}


class DocLinkTests(unittest.TestCase):
    def test_relative_links_and_anchors_resolve(self):
        self.assertEqual(broken_links(DOCS), [])

    def test_read_by_task_skills_exist(self):
        skills = read_by_task_skills(ROOT / "AGENTS.md")
        if not skills:
            self.skipTest("no Read by task table with skills in AGENTS.md")
        missing = sorted(name for name in skills if not (ROOT / ".agents/skills" / name / "SKILL.md").is_file())
        self.assertEqual(missing, [])


class SlugTests(unittest.TestCase):
    def test_slug_follows_github_rules(self):
        self.assertEqual(slug("Sites and credentials"), "sites-and-credentials")
        self.assertEqual(slug("`ignore_permissions=True`"), "ignore_permissionstrue")
        self.assertEqual(slug("Client/server contract"), "clientserver-contract")
        self.assertEqual(slug("Review [guide](x.md) — setup"), "review-guide--setup")


if __name__ == "__main__":
    unittest.main()
