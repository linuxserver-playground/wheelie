#!/usr/bin/env python3
"""Move the legacy index entries off wheels.linuxserver.io.

The index pages carry the entries upstream's wheelie published to its S3 bucket. Most of them are copies of
PyPI files: pip gets those from PyPI, so their entries are dropped. The rest are wheels PyPI never had; they are
downloaded from the legacy host into `--download/<index>/`, listed in `--plan` as `<tag>\\t<path>` for the
upload step (release `index-<index>`, as publish.py), and their entries are repointed at the release asset.

Only the indexes in `distros.json` are migrated (`--indexes` narrows that). Entries already on our releases are
left alone. Run it locally, upload the plan with `gh release upload`, then commit `docs/` (Pages deploys on
push):

    migrate.py --indexes alpine-3.24 --download wheels --plan upload.tsv --repo linuxserver-playground/wheelie
    while IFS=$'\t' read -r tag path; do gh release upload "$tag" "$path"; done < upload.tsv
    migrate.py --dry-run --repo linuxserver-playground/wheelie     # classify only
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from gaps import ROOT, USER_AGENT, http_fetch, index_links, load_config, parse_wheel
from publish import asset_url, pypi_filenames, release_tag

LEGACY = "https://wheels.linuxserver.io/"


def classify(links: dict[str, str], repo: str, fetch=http_fetch, workers: int = 16) -> dict[str, list[str]]:
    """Split an index page's legacy entries into `pypi` (exact PyPI filenames) and `keep` (the rest)."""
    ours = f"https://github.com/{repo}/releases/download/"
    legacy = sorted(f for f, href in links.items() if not href.startswith(ours))
    pairs = {(w["name"], w["version"]) for f in legacy if (w := parse_wheel(f))}
    cache: dict = {}
    with ThreadPoolExecutor(workers) as pool:
        # Fill the cache; pypi_filenames stores each (name, version) once.
        list(pool.map(lambda p: pypi_filenames(p[0], p[1], fetch, cache), sorted(pairs)))
    result: dict[str, list[str]] = {"pypi": [], "keep": []}
    for filename in legacy:
        wheel = parse_wheel(filename)
        on_pypi = wheel is not None and filename in pypi_filenames(wheel["name"], wheel["version"], fetch, cache)
        result["pypi" if on_pypi else "keep"].append(filename)
    return result


def drop_entry(text: str, href: str) -> str:
    """Remove one `<a href=...>...</a>` entry with its `<br />` and the blank line after it."""
    pattern = (
        r"^[ \t]*<a href=(['\"])" + re.escape(href) + r"\1>[^<]*</a>[ \t]*\n"
        r"(?:[ \t]*<br\s*/?>[ \t]*\n)?(?:[ \t]*\n)?"
    )
    new, count = re.subn(pattern, "", text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"entry not found: {href}")
    return new


def repoint_entry(text: str, href: str, url: str) -> str:
    new, count = re.subn(
        r"""(href=)(['"])""" + re.escape(href) + r"\2",
        lambda m: f"{m.group(1)}{m.group(2)}{url}{m.group(2)}",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"entry not found: {href}")
    return new


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if not data.startswith(b"PK"):
        raise ValueError(f"{url} is not a wheel")
    dest.write_bytes(data)


def migrate(index: str, docs: Path, repo: str, download_dir: Path | None, fetch=http_fetch) -> dict:
    """Rewrite one index page; return what happened to its legacy entries."""
    page = docs / index / "index.html"
    text = page.read_text()
    links = index_links(text)
    groups = classify(links, repo, fetch)
    if download_dir is not None:
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda f: download(links[f], download_dir / index / f), groups["keep"]))
    for filename in groups["pypi"]:
        text = drop_entry(text, links[filename])
    for filename in groups["keep"]:
        text = repoint_entry(text, links[filename], asset_url(repo, index, filename))
    if download_dir is not None:
        page.write_text(text)
    return groups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--repo", required=True, help="owner/name, for the release asset URLs")
    parser.add_argument("--download", type=Path, help="download the kept wheels here (<dir>/<index>/<file>)")
    parser.add_argument("--plan", type=Path, help="write <tag>\\t<path> lines here")
    parser.add_argument("--dry-run", action="store_true", help="classify and report; change nothing")
    parser.add_argument("--indexes", help="space or comma separated index names; default every index in distros.json")
    parser.add_argument("--config", type=Path, default=ROOT / "distros.json")
    args = parser.parse_args(argv)
    if not args.dry_run and (args.download is None or args.plan is None):
        parser.error("--download and --plan are required unless --dry-run")

    indexes = list(dict.fromkeys(d["index"] for d in load_config(args.config)["distros"].values()))
    if args.indexes:
        wanted = re.split(r"[\s,]+", args.indexes.strip())
        unknown = [i for i in wanted if i not in indexes]
        if unknown:
            parser.error(f"unknown index(es): {', '.join(unknown)}")
        indexes = [i for i in indexes if i in wanted]
    plan = []
    for index in indexes:
        if not (args.docs / index / "index.html").exists():
            continue
        groups = migrate(index, args.docs, args.repo, None if args.dry_run else args.download)
        print(f"{index}: {len(groups['keep'])} migrated, {len(groups['pypi'])} dropped as PyPI copies", file=sys.stderr)
        for filename in groups["keep"]:
            print(f"  keep {filename}", file=sys.stderr)
            plan.append(f"{release_tag(index)}\t{args.download / index / filename if args.download else filename}\n")
    if args.plan and not args.dry_run:
        args.plan.write_text("".join(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
