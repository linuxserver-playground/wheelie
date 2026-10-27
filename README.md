# wheelie

Python wheels for LinuxServer images that PyPI does not provide, built on the playground's base images for
amd64 and arm64.

```sh
pip install --find-links https://linuxserver-playground.github.io/wheelie/alpine-3.24/ bluepy
```

Indexes: `alpine-3.21`, `alpine-3.22`, `alpine-3.23`, `alpine-3.24` and `ubuntu` (noble and resolute) at
https://linuxserver-playground.github.io/wheelie/. The wheels are GitHub Release assets (one release per
index, `index-<index>`); entries from before the move to GitHub Actions still link `wheels.linuxserver.io`.

Packages are listed in `packages.txt` and distros in `distros.json`. A wheel is built only when neither PyPI
nor the index has one that pip on that distro and arch would install; `scripts/gaps.py` makes that call and
`.github/workflows/build.yml` builds and publishes. See `AGENTS.md` for the details.
