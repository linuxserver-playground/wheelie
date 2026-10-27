# AGENTS.md - wheelie

## Purpose

A Python wheel index for LinuxServer images, built only for what PyPI does not provide. Image Dockerfiles use
it with `pip install --find-links https://linuxserver-playground.github.io/wheelie/<index>/ ...`.

It is the slim GitHub Actions rebuild of `linuxserver/wheelie`. The original rebuilt every package in
`packages.txt` for every distro whenever its index lacked the newest version, and re-hosted whatever pip
produced on S3. Today the packages it lists (cffi, cryptography, maturin, PyYAML, sabctools, ujson) all ship
musllinux and manylinux wheels for x86_64 and aarch64 on PyPI, so most of that was copying PyPI (54 of the 56
wheels in the alpine-3.24 index). What is left is real: sdist-only packages such as bluepy, and the window
after a distro moves to a new CPython before upstream projects publish wheels for it. No Jenkins, no S3, no
Home Assistant or SCI variants (their schedulers had been off since 2024 and 2023).

## The gap rule

`scripts/gaps.py` decides, per package, distro and arch, with HTTP only (no Docker, no runner; control will run
the same logic hourly and dispatch `build.yml`). A build is needed when the version pip would install (the
newest on PyPI, or a pinned `name==version`) has

1. no compatible wheel on PyPI, and
2. no compatible wheel in our index page for that distro (skipped by a rebuild, see `packages` below).

Compatible means the platform is `any`, or the distro's libc family for the arch (musllinux on Alpine,
manylinux on Ubuntu) at or below its libc version, or, in our index only, `linux_<arch>`; and the interpreter
is the distro's CPython exactly, the stable ABI (`abi3`) at or below it, or a pure `py3`/`py3X` tag. A
release whose Requires-Python excludes the distro is skipped (pip would install an older one).

The distros' CPython and libc versions live in `distros.json`, read from the base images
(`python3 -V`, `apk list -I musl`, `ldd --version`), so the check never starts a container. Update them when a
base image moves to a new release. Only Alpine versions the playground publishes as base images are listed.

| Distro | Base image | Index | CPython | libc |
| --- | --- | --- | --- | --- |
| alpine-3.21 | `baseimage-alpine:3.21` | `alpine-3.21` | 3.12 | musl 1.2 |
| alpine-3.22 | `baseimage-alpine:3.22` | `alpine-3.22` | 3.12 | musl 1.2 |
| alpine-3.23 | `baseimage-alpine:3.23` | `alpine-3.23` | 3.12 | musl 1.2 |
| alpine-3.24 | `baseimage-alpine:3.24` | `alpine-3.24` | 3.14 | musl 1.2 |
| ubuntu-noble | `baseimage-ubuntu:noble` | `ubuntu` | 3.12 | glibc 2.39 |
| ubuntu-resolute | `baseimage-ubuntu:resolute` | `ubuntu` | 3.14 | glibc 2.43 |

Alpine indexes are per release (a wheel can link a library version that changes between releases); Ubuntu
shares one index, and on a filename both releases build, the older one (listed first) wins.

## Layout

| Path | What |
| --- | --- |
| `packages.txt` | The packages to keep wheels for. |
| `distros.json` | The distros, their base images, index names, CPython and libc versions; the arches and runners. |
| `scripts/gaps.py` | The gap check. `--index-dir docs` reads a checkout, else the Pages index; `--matrix` for the workflow. |
| `scripts/publish.py` | Picks the built wheels to publish and updates the index pages. |
| `scripts/migrate.py` | One-off, run locally per index: drops legacy entries that are PyPI copies, re-hosts the rest on the release and repoints them. Done for `alpine-3.24`. |
| `scripts/build.sh` | One distro and arch: `docker buildx build --output type=local` into `out/`. |
| `scripts/build-wheels.sh` | Inside the build: one `pip wheel --no-binary <pkg>` per package, with retries. |
| `scripts/lib.sh` | `retry_ghcr` and `retry`, vendored from `workflows/scripts/lib.sh`; keep them in step. |
| `Dockerfile` | Build dependencies on the base image; exports `/build` from a scratch stage. |
| `docs/` | The index pages, served by Pages. Entries from before the move still link `wheels.linuxserver.io`, except on `alpine-3.24` (migrated). |
| `tests/` | Unit tests with PyPI and index fixtures. |
| `.github/workflows/build.yml` | Gap check, build per distro and arch, publish. |
| `.github/workflows/pages.yml` | Deploys `docs/` to Pages (on push and when the build calls it). |
| `.github/workflows/check.yml` | Tests and shellcheck on push and pull request. |

## The build workflow

`build.yml` is `workflow_dispatch` only for now; control will dispatch it. One run at a time (concurrency group
`wheelie-build`, queued, not cancelled). Inputs:

- `packages`: build these (space separated, `name` or `name==version`) instead of `packages.txt`, ignoring
  our index but not PyPI. Use it to rebuild: the package is compiled even where our index has it, and a legacy
  entry with the same filename is repointed at the new build. A package PyPI has wheels for is still skipped.
- `distros`: only these distros from `distros.json`.
- `parallel`: the most build jobs at once (default 4). Mind the org's 20 concurrent jobs.

Jobs: **Gap check** makes the matrix (an empty one ends the run green). **Build** runs per distro and arch on
native runners (`ubuntu-24.04`, `ubuntu-24.04-arm`), compiles each package from source and uploads the wheels
as an artifact. **Publish** (main only) keeps the wheels that are not `none-any`, not files PyPI has, and not
already listed, uploads them to the GitHub Release `index-<index>` (created when missing), appends them to
`docs/<index>/index.html` with their asset download URLs, and commits `[skip ci]` with `GITHUB_TOKEN`.
**Pages** then deploys, because that push triggers no workflow. A failed leg does not stop the others from
publishing; the run still shows red.

## How to validate

```sh
python3 -m unittest discover -s tests -t .
shellcheck scripts/*.sh                                  # or: docker run --rm -v "$PWD":/mnt -w /mnt koalaman/shellcheck:v0.10.0 -x scripts/*.sh
actionlint                                               # or: docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.7
python3 scripts/gaps.py --index-dir docs                 # what a run would build now
IMAGE=ghcr.io/linuxserver-playground/baseimage-alpine:3.24 INDEX=alpine-3.24 PACKAGES=bluepy ./scripts/build.sh
```

Live: check the org's load (`gh run list`), then
`gh workflow run build.yml -R linuxserver-playground/wheelie -f packages=bluepy -f distros=alpine-3.24 -f parallel=2`,
and prove the result with
`docker run --rm --entrypoint sh ghcr.io/linuxserver-playground/baseimage-alpine:3.24 -c 'apk add -q py3-pip && python3 -m venv /tmp/v && /tmp/v/bin/pip install --only-binary :all: --find-links https://linuxserver-playground.github.io/wheelie/alpine-3.24/ bluepy'`.

## What you may edit

Everything except what the workflow writes: the wheel links in `docs/` are added by Publish, never by hand
(remove a bad one by hand only together with its release asset). Adding a distro: add it to `distros.json`
with versions read from the base image; the first run builds its index. Adding a package: add it to
`packages.txt` and its build dependencies to the `Dockerfile`, and build it locally first.

## Pull request rules

Disclose AI use in the description. Commit subjects are short imperative sentences without prefixes, emoji or
trailers. Nothing may name a namespace other than `linuxserver-playground` (the legacy
`wheels.linuxserver.io` links in `docs/` are history).
