#!/usr/bin/env bash
# Runs inside the Dockerfile's builder stage: one `pip wheel` per package into /build.
#
# Env: PACKAGES (space separated, name or name==version), FIND_LINKS (our index page for this distro).
# Each package is built from source (--no-binary for that package only); its dependencies may come as wheels
# from PyPI or our index, and the publish step keeps only what PyPI does not have.
set -euo pipefail
# shellcheck source=scripts/lib.sh
source /wheelie/lib.sh

if [[ -z "${PACKAGES:-}" ]]; then
  echo "PACKAGES is empty" >&2
  exit 1
fi

retry 3 20 pip install --no-cache-dir -U pip setuptools wheel cython
mkdir -p /build
# Unquoted on purpose: one iteration per package (upstream quoted it, which ran a single pip wheel over the
# whole list and leaked the numpy flag to every package).
for spec in ${PACKAGES}; do
  name="${spec%%[=<>!~ ]*}"
  flags=()
  if [[ "${name,,}" == "numpy" ]]; then
    flags+=(--config-settings=setup-args=-Dallow-noblas=true)
  fi
  echo "**** Building ${spec} ****"
  retry 3 20 pip wheel --wheel-dir=/build --find-links="${FIND_LINKS}" --no-cache-dir -v \
    --no-binary="${name}" "${flags[@]}" "${spec}"
done
echo "**** Wheels in /build ****"
ls -l /build
