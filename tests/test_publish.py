import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import CONFIG, FIXTURES, gaps, pypi_fetch  # noqa: F401  (helpers puts scripts/ on the path)

import publish  # noqa: E402

REPO = "linuxserver-playground/wheelie"


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.docs = self.tmp / "docs"
        shutil.copytree(FIXTURES / "docs", self.docs)
        self.wheels = self.tmp / "wheels"

    def wheel(self, distro, arch, filename):
        folder = self.wheels / f"wheels-{distro}-{arch}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_bytes(b"wheel")

    def plan(self, built=("bluepy",)):
        return publish.plan(CONFIG, self.wheels, self.docs, REPO, set(built), pypi_fetch)

    def test_filters(self):
        self.wheel("alpine-3.24", "arm64", "bluepy-1.3.0-cp314-cp314-linux_aarch64.whl")
        self.wheel("alpine-3.24", "arm64", "pycparser-2.23-py3-none-any.whl")
        self.wheel("alpine-3.24", "arm64", "cryptography-50.0.2-cp311-abi3-musllinux_1_2_aarch64.whl")
        self.wheel("alpine-3.24", "arm64", "cffi-2.0.0-cp314-cp314-musllinux_1_2_x86_64.whl")
        self.wheel("alpine-3.24", "arm64", "gevent-25.1-cp314-cp314-linux_aarch64.whl")
        names = [e["filename"] for e in self.plan()]
        # pure wheel, a PyPI file and a wheel already listed (a dependency) are all left out
        self.assertEqual(names, ["bluepy-1.3.0-cp314-cp314-linux_aarch64.whl", "gevent-25.1-cp314-cp314-linux_aarch64.whl"])

    def test_repoint_only_requested_packages(self):
        self.wheel("alpine-3.24", "amd64", "bluepy-1.3.0-cp314-cp314-linux_x86_64.whl")
        self.assertEqual(self.plan(built=()), [])
        [entry] = self.plan()
        self.assertTrue(entry["replaces"].startswith("https://wheels.linuxserver.io/"))

    def test_first_distro_wins_on_a_shared_index(self):
        self.wheel("ubuntu-noble", "amd64", "thing-1-cp312-abi3-linux_x86_64.whl")
        self.wheel("ubuntu-resolute", "amd64", "thing-1-cp312-abi3-linux_x86_64.whl")
        [entry] = self.plan()
        self.assertIn("wheels-ubuntu-noble-amd64", entry["path"])

    def test_render(self):
        self.wheel("alpine-3.24", "amd64", "bluepy-1.3.0-cp314-cp314-linux_x86_64.whl")
        self.wheel("alpine-3.24", "arm64", "bluepy-1.3.0-cp314-cp314-linux_aarch64.whl")
        self.wheel("alpine-3.21", "amd64", "bluepy-1.3.0-cp312-cp312-linux_x86_64.whl")
        entries = self.plan()
        publish.render(self.docs, REPO, entries)
        publish.render_root(self.docs)
        base = f"https://github.com/{REPO}/releases/download"
        links = gaps.index_links((self.docs / "alpine-3.24/index.html").read_text())
        self.assertEqual(links["bluepy-1.3.0-cp314-cp314-linux_x86_64.whl"], f"{base}/index-alpine-3.24/bluepy-1.3.0-cp314-cp314-linux_x86_64.whl")
        self.assertEqual(links["bluepy-1.3.0-cp314-cp314-linux_aarch64.whl"], f"{base}/index-alpine-3.24/bluepy-1.3.0-cp314-cp314-linux_aarch64.whl")
        self.assertIn("cffi-2.0.0-cp314-cp314-musllinux_1_2_x86_64.whl", links)
        self.assertEqual(len(links), 3)
        new_page = (self.docs / "alpine-3.21/index.html").read_text()
        self.assertIn("Precompiled wheels for Alpine 3.21", new_page)
        self.assertEqual(list(gaps.index_links(new_page)), ["bluepy-1.3.0-cp312-cp312-linux_x86_64.whl"])
        root = (self.docs / "index.html").read_text()
        self.assertIn("href='alpine-3.21/'", root)
        self.assertIn("href='ubuntu/'", root)

    def test_render_is_stable(self):
        self.wheel("alpine-3.24", "arm64", "bluepy-1.3.0-cp314-cp314-linux_aarch64.whl")
        publish.render(self.docs, REPO, self.plan())
        self.assertEqual(self.plan(), [])

    def test_main_writes_plan(self):
        self.wheel("alpine-3.24", "arm64", "bluepy-1.3.0-cp314-cp314-linux_aarch64.whl")
        plan = self.tmp / "upload.tsv"
        with mock.patch.object(publish, "http_fetch", pypi_fetch), mock.patch("sys.stderr"):
            publish.main(["--wheels", str(self.wheels), "--docs", str(self.docs), "--repo", REPO,
                          "--built", "bluepy==1.3.0", "--plan", str(plan)])
        tag, path = plan.read_text().strip().split("\t")
        self.assertEqual(tag, "index-alpine-3.24")
        self.assertTrue(path.endswith("bluepy-1.3.0-cp314-cp314-linux_aarch64.whl"))


if __name__ == "__main__":
    unittest.main()
