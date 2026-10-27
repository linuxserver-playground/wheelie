import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import FIXTURES, gaps  # noqa: F401  (helpers puts scripts/ on the path)

import migrate  # noqa: E402

REPO = "linuxserver-playground/wheelie"


def fetch(url):
    """PyPI has cffi 2.0.0's musllinux wheel; bluepy is sdist only."""
    if url == f"{gaps.PYPI}/cffi/2.0.0/json":
        return json.dumps({"urls": [{"filename": "cffi-2.0.0-cp314-cp314-musllinux_1_2_x86_64.whl"}]}).encode()
    if url == f"{gaps.PYPI}/bluepy/1.3.0/json":
        return (FIXTURES / "pypi" / "bluepy.json").read_bytes()
    return None


class Migrate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.docs = self.tmp / "docs"
        shutil.copytree(FIXTURES / "docs", self.docs)

    def test_drops_pypi_copies_and_repoints_the_rest(self):
        downloads = []
        original = migrate.download
        migrate.download = lambda url, dest: downloads.append((url, dest))
        self.addCleanup(setattr, migrate, "download", original)
        groups = migrate.migrate("alpine-3.24", self.docs, REPO, self.tmp / "wheels", fetch)
        self.assertEqual(groups["pypi"], ["cffi-2.0.0-cp314-cp314-musllinux_1_2_x86_64.whl"])
        self.assertEqual(groups["keep"], ["bluepy-1.3.0-cp314-cp314-linux_x86_64.whl"])
        self.assertEqual(downloads, [(
            "https://wheels.linuxserver.io/alpine-3.24/bluepy-1.3.0-cp314-cp314-linux_x86_64.whl",
            self.tmp / "wheels" / "alpine-3.24" / "bluepy-1.3.0-cp314-cp314-linux_x86_64.whl",
        )])
        text = (self.docs / "alpine-3.24" / "index.html").read_text()
        self.assertEqual(gaps.index_links(text), {
            "bluepy-1.3.0-cp314-cp314-linux_x86_64.whl":
                f"https://github.com/{REPO}/releases/download/index-alpine-3.24/bluepy-1.3.0-cp314-cp314-linux_x86_64.whl",
        })
        self.assertNotIn("cffi", text)
        self.assertNotIn("wheels.linuxserver.io", text)
        self.assertIn("</a>\n    <br />\n\n</body>", text)

    def test_dry_run_changes_nothing(self):
        before = (self.docs / "alpine-3.24" / "index.html").read_text()
        migrate.migrate("alpine-3.24", self.docs, REPO, None, fetch)
        self.assertEqual((self.docs / "alpine-3.24" / "index.html").read_text(), before)


if __name__ == "__main__":
    unittest.main()
