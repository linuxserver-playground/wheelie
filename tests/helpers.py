import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gaps  # noqa: E402

CONFIG = gaps.load_config(ROOT / "distros.json")


def pypi_fetch(url: str):
    """Serve tests/fixtures/pypi/<name>.json for https://pypi.org/pypi/<name>[/<version>]/json."""
    parts = url.removeprefix(gaps.PYPI + "/").split("/")
    path = FIXTURES / "pypi" / f"{gaps.canonical(parts[0])}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if len(parts) == 3 and parts[1] != data["info"]["version"]:
        return None
    return path.read_bytes()


def index_fetch(index: str):
    page = FIXTURES / "docs" / index / "index.html"
    return page.read_text() if page.exists() else None
