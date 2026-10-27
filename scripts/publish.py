#!/usr/bin/env python3
"""Choose the built wheels to publish and add them to the index pages.

Reads the build artifacts (`<wheels>/wheels-<distro>-<arch>/*.whl`), keeps each wheel that is

- not pure (`none-any` wheels come from PyPI as they are),
- not a file PyPI already has (pip downloads, for instance a dependency's wheel, are not ours to host),
- not on the index page already, unless it is a package that was asked for and the page still points at the
  legacy host (then the entry is repointed at our build),
- the first of its name: distros are taken in `distros.json` order, so on the shared ubuntu index the oldest
  release (and glibc) wins,

writes `<tag>\\t<path>` lines for the upload step, and updates `docs/<index>/index.html` to link each wheel's
GitHub Release asset (release `index-<index>`). The root page is regenerated from the index directories.

    publish.py --wheels wheels --docs docs --repo linuxserver-playground/wheelie --built "bluepy==1.3.0" --plan upload.tsv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

from gaps import ROOT, canonical, http_fetch, index_links, load_config, parse_wheel, split_spec, PYPI

PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
</head>
<body>
    <h1>{heading}</h1>

</body>
</html>
"""


def release_tag(index: str) -> str:
    return f"index-{index}"


def asset_url(repo: str, index: str, filename: str) -> str:
    return f"https://github.com/{repo}/releases/download/{release_tag(index)}/{filename}"


def pypi_filenames(name: str, version: str, fetch=http_fetch, cache: dict | None = None) -> set[str]:
    key = (canonical(name), version)
    if cache is not None and key in cache:
        return cache[key]
    raw = fetch(f"{PYPI}/{canonical(name)}/{version}/json")
    names = {f["filename"] for f in json.loads(raw).get("urls", [])} if raw else set()
    if cache is not None:
        cache[key] = names
    return names


def heading(index: str) -> str:
    distro, _, version = index.partition("-")
    return f"Precompiled wheels for {distro.capitalize()}{' ' + version if version else ''}"


def plan(config: dict, wheels: Path, docs: Path, repo: str, built: set[str], fetch=http_fetch) -> list[dict]:
    """Return [{index, path, filename, replaces}] for the wheels to upload, in upload order."""
    ours = f"https://github.com/{repo}/releases/download/"
    pages: dict[str, dict[str, str]] = {}
    chosen: dict[str, set[str]] = {}
    cache: dict = {}
    result = []
    for distro_name, distro in config["distros"].items():
        index = distro["index"]
        if index not in pages:
            page = docs / index / "index.html"
            pages[index] = index_links(page.read_text()) if page.exists() else {}
            chosen[index] = set()
        for arch in config["arches"]:
            folder = wheels / f"wheels-{distro_name}-{arch}"
            for path in sorted(folder.glob("*.whl")) if folder.is_dir() else []:
                wheel = parse_wheel(path.name)
                if wheel is None or all(abi == "none" and plat == "any" for _, abi, plat in wheel["tags"]):
                    continue
                if path.name in chosen[index]:
                    continue
                existing = pages[index].get(path.name)
                if existing is not None and (existing.startswith(ours) or wheel["name"] not in built):
                    continue
                if path.name in pypi_filenames(wheel["name"], wheel["version"], fetch, cache):
                    continue
                chosen[index].add(path.name)
                result.append({"index": index, "path": str(path), "filename": path.name, "replaces": existing})
    return result


def render(docs: Path, repo: str, entries: list[dict]) -> None:
    """Add (or repoint) each entry on its index page, keeping the page's history and layout."""
    by_index: dict[str, list[dict]] = {}
    for entry in entries:
        by_index.setdefault(entry["index"], []).append(entry)
    for index, items in by_index.items():
        page = docs / index / "index.html"
        if not page.exists():
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(PAGE.format(title="wheelie", heading=heading(index)))
        text = page.read_text()
        added = ""
        for entry in items:
            url = asset_url(repo, index, entry["filename"])
            if entry["replaces"]:
                text = re.sub(
                    r"""(href=)(['"])""" + re.escape(entry["replaces"]) + r"\2",
                    lambda m: f"{m.group(1)}{m.group(2)}{url}{m.group(2)}",
                    text,
                )
            else:
                added += f"    <a href='{escape(url)}'>{escape(entry['filename'])}</a>\n    <br />\n\n"
        text = text.replace("</body>", added + "</body>", 1)
        page.write_text(text)


def render_root(docs: Path) -> None:
    indexes = sorted(p.parent.name for p in docs.glob("*/index.html"))
    links = "".join(f"    <a href='{escape(name)}/'>{escape(name)}</a>\n    <br />\n\n" for name in indexes)
    (docs / "index.html").write_text(
        PAGE.format(title="wheelie", heading="Precompiled wheels for LinuxServer images").replace(
            "</body>", links + "</body>"
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wheels", type=Path, required=True, help="downloaded artifacts: wheels-<distro>-<arch>/")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--repo", required=True, help="owner/name, for the release asset URLs")
    parser.add_argument("--built", default="", help="the packages the run was asked to build")
    parser.add_argument("--plan", type=Path, required=True, help="write <tag>\\t<path> lines here")
    parser.add_argument("--config", type=Path, default=ROOT / "distros.json")
    args = parser.parse_args(argv)

    built = {canonical(split_spec(spec)[0]) for spec in re.split(r"[\s,]+", args.built) if spec}
    entries = plan(load_config(args.config), args.wheels, args.docs, args.repo, built, http_fetch)
    render(args.docs, args.repo, entries)
    render_root(args.docs)
    args.plan.write_text("".join(f"{release_tag(e['index'])}\t{e['path']}\n" for e in entries))
    for entry in entries:
        note = f" (repoints {entry['replaces']})" if entry["replaces"] else ""
        print(f"{entry['index']}: {entry['filename']}{note}", file=sys.stderr)
    if not entries:
        print("no new wheels to publish", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
