import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

from tests.helpers import CONFIG, FIXTURES, gaps, index_fetch, pypi_fetch

ALPINE = CONFIG["distros"]["alpine-3.24"]
ALPINE_312 = CONFIG["distros"]["alpine-3.23"]
NOBLE = CONFIG["distros"]["ubuntu-noble"]


class Compatible(unittest.TestCase):
    def test_libc_family(self):
        musl = "cffi-2.1.1-cp314-cp314-musllinux_1_2_x86_64.whl"
        many = "cffi-2.1.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        self.assertTrue(gaps.compatible(musl, ALPINE, "x86_64"))
        self.assertFalse(gaps.compatible(musl, ALPINE, "aarch64"))
        self.assertFalse(gaps.compatible(many, ALPINE_312, "x86_64"))
        self.assertTrue(gaps.compatible(many, NOBLE, "x86_64"))

    def test_libc_version(self):
        self.assertFalse(gaps.compatible("x-1-cp312-cp312-manylinux_2_40_x86_64.whl", NOBLE, "x86_64"))
        self.assertTrue(gaps.compatible("x-1-cp312-cp312-manylinux_2_39_x86_64.whl", NOBLE, "x86_64"))
        self.assertFalse(gaps.compatible("x-1-cp314-cp314-musllinux_1_3_x86_64.whl", ALPINE, "x86_64"))
        self.assertTrue(gaps.compatible("x-1-cp312-cp312-manylinux1_x86_64.whl", NOBLE, "x86_64"))

    def test_interpreter(self):
        self.assertFalse(gaps.compatible("x-1-cp312-cp312-musllinux_1_2_x86_64.whl", ALPINE, "x86_64"))
        self.assertFalse(gaps.compatible("x-1-cp314-cp314t-musllinux_1_2_x86_64.whl", ALPINE, "x86_64"))
        self.assertTrue(gaps.compatible("x-1-cp311-abi3-musllinux_1_2_x86_64.whl", ALPINE, "x86_64"))
        self.assertFalse(gaps.compatible("x-1-cp315-abi3.abi3t-musllinux_1_2_x86_64.whl", ALPINE, "x86_64"))
        self.assertTrue(gaps.compatible("x-1-py3-none-musllinux_1_1_x86_64.whl", ALPINE, "x86_64"))
        self.assertTrue(gaps.compatible("x-1-py3-none-any.whl", ALPINE, "aarch64"))
        self.assertFalse(gaps.compatible("x-1-py315-none-any.whl", ALPINE, "aarch64"))
        self.assertFalse(gaps.compatible("x-1-pp311-pypy311_pp73-musllinux_1_2_x86_64.whl", ALPINE, "x86_64"))

    def test_linux_tag_only_in_our_index(self):
        wheel = "bluepy-1.3.0-cp314-cp314-linux_x86_64.whl"
        self.assertFalse(gaps.compatible(wheel, ALPINE, "x86_64"))
        self.assertTrue(gaps.compatible(wheel, ALPINE, "x86_64", allow_linux=True))

    def test_build_tag_and_garbage(self):
        self.assertTrue(gaps.compatible("x-1-2build-py3-none-any.whl", ALPINE, "x86_64"))
        self.assertFalse(gaps.compatible("x-1.tar.gz", ALPINE, "x86_64"))


class RequiresPython(unittest.TestCase):
    def test_specifiers(self):
        self.assertTrue(gaps.python_satisfies(None, "3.12"))
        self.assertTrue(gaps.python_satisfies("!=3.9.0,!=3.9.1,>=3.9", "3.12"))
        self.assertFalse(gaps.python_satisfies(">=3.13", "3.12"))
        self.assertFalse(gaps.python_satisfies("<3.14", "3.14"))
        self.assertTrue(gaps.python_satisfies("==3.12.*", "3.12"))
        self.assertFalse(gaps.python_satisfies("!=3.14.*", "3.14"))
        self.assertTrue(gaps.python_satisfies("~=3.10", "3.14"))


class FindGaps(unittest.TestCase):
    def run_gaps(self, packages, use_index=True, distros=None):
        return gaps.find_gaps(CONFIG, packages, index_fetch if use_index else None, pypi_fetch, distros)

    def test_pypi_wheels_need_nothing(self):
        self.assertEqual(self.run_gaps(["cryptography", "maturin"]), [])

    def test_sdist_only_package_builds_where_the_index_lacks_it(self):
        result = self.run_gaps(["bluepy"], distros=["alpine-3.24", "ubuntu-noble", "ubuntu-resolute"])
        self.assertEqual(result, [
            {"distro": "alpine-3.24", "arch": "arm64", "packages": ["bluepy==1.3.0"]},
            {"distro": "ubuntu-resolute", "arch": "amd64", "packages": ["bluepy==1.3.0"]},
            {"distro": "ubuntu-resolute", "arch": "arm64", "packages": ["bluepy==1.3.0"]},
        ])

    def test_missing_index_page_means_build(self):
        result = self.run_gaps(["bluepy"], distros=["alpine-3.21"])
        self.assertEqual([g["arch"] for g in result], ["amd64", "arm64"])

    def test_rebuild_ignores_the_index_not_pypi(self):
        result = self.run_gaps(["bluepy", "cryptography"], use_index=False, distros=["alpine-3.24"])
        self.assertEqual(result, [
            {"distro": "alpine-3.24", "arch": "amd64", "packages": ["bluepy==1.3.0"]},
            {"distro": "alpine-3.24", "arch": "arm64", "packages": ["bluepy==1.3.0"]},
        ])

    def test_old_version_in_index_does_not_count(self):
        page = (FIXTURES / "docs/alpine-3.24/index.html").read_text().replace("bluepy-1.3.0", "bluepy-1.2.0")
        result = gaps.find_gaps(CONFIG, ["bluepy"], lambda index: page, pypi_fetch, ["alpine-3.24"])
        self.assertEqual(len(result), 2)

    def test_pinned_version(self):
        self.assertEqual(self.run_gaps(["bluepy==1.3.0"], distros=["alpine-3.24"])[0]["packages"], ["bluepy==1.3.0"])
        with self.assertRaises(LookupError):
            self.run_gaps(["bluepy==0.1"])

    def test_requires_python_skips(self):
        data = json.loads((FIXTURES / "pypi/bluepy.json").read_text())
        data["info"]["requires_python"] = ">=3.13"
        fetch = lambda url: json.dumps(data).encode()
        result = gaps.find_gaps(CONFIG, ["bluepy"], None, fetch, ["alpine-3.23", "alpine-3.24"])
        self.assertEqual({g["distro"] for g in result}, {"alpine-3.24"})

    def test_unknown_distro(self):
        with self.assertRaises(ValueError):
            self.run_gaps(["bluepy"], distros=["alpine-3.19"])


class Cli(unittest.TestCase):
    def test_matrix(self):
        out = StringIO()
        with mock.patch.object(gaps, "http_fetch", pypi_fetch), redirect_stdout(out):
            gaps.main(["--packages", "bluepy, cryptography", "--distros", "ubuntu-resolute", "--rebuild", "--matrix", "-q"])
        matrix = json.loads(out.getvalue())
        self.assertEqual(matrix["include"][0], {
            "distro": "ubuntu-resolute", "arch": "amd64", "runner": "ubuntu-24.04",
            "image": "ghcr.io/linuxserver-playground/baseimage-ubuntu:resolute", "index": "ubuntu",
            "packages": "bluepy==1.3.0",
        })
        self.assertEqual(matrix["include"][1]["runner"], "ubuntu-24.04-arm")

    def test_index_dir(self):
        out = StringIO()
        with mock.patch.object(gaps, "http_fetch", pypi_fetch), redirect_stdout(out):
            gaps.main(["--packages", "bluepy", "--distros", "alpine-3.24", "--index-dir", str(FIXTURES / "docs"), "-q"])
        self.assertEqual(json.loads(out.getvalue()), [{"distro": "alpine-3.24", "arch": "arm64", "packages": ["bluepy==1.3.0"]}])


class Config(unittest.TestCase):
    def test_distros_are_complete(self):
        for name, distro in CONFIG["distros"].items():
            self.assertEqual(set(distro), {"image", "index", "python", "libc", "libc_version"}, name)
            self.assertTrue(distro["image"].startswith("ghcr.io/linuxserver-playground/baseimage-"), name)

    def test_packages_file(self):
        self.assertIn("bluepy", gaps.read_packages())


if __name__ == "__main__":
    unittest.main()
