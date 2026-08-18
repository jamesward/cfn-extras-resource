#!/usr/bin/env bash
# Build the minimal Lambda deployment package: just the cfn_extras package plus
# its one runtime dependency (crhelper). boto3/botocore are provided by the
# Lambda runtime and must NOT be bundled (they'd bloat the zip and, worse,
# shadow the runtime's newer SDK - breaking services like codeconnections).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
ZIP="$DIST/cfn-extras-resource.zip"
PYTHON="${PYTHON:-python3}"

rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD" "$DIST"

# Runtime deps only (crhelper); --no-deps keeps boto3/botocore out.
"$PYTHON" -m pip install -r "$ROOT/requirements.txt" -t "$BUILD" --no-deps --quiet

# The handlers.
cp -r "$ROOT/cfn_extras" "$BUILD/cfn_extras"

# Strip everything not needed at runtime.
find "$BUILD" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$BUILD" -type d -name 'tests' -prune -exec rm -rf {} +
find "$BUILD" -type d -name '*.dist-info' -prune -exec rm -rf {} +
find "$BUILD" -type d -name '*.egg-info' -prune -exec rm -rf {} +
find "$BUILD" -type f -name '*.pyc' -delete
# Type stubs aren't used at runtime.
find "$BUILD" -type f \( -name '*.pyi' -o -name 'py.typed' \) -delete

# Deterministic zip (sorted entries, fixed timestamps) via stdlib - no external
# `zip` binary needed, and identical inputs produce byte-identical artifacts.
"$PYTHON" - "$BUILD" "$ZIP" <<'PY'
import os, sys, zipfile
build, zippath = sys.argv[1], sys.argv[2]
files = sorted(
    os.path.relpath(os.path.join(r, f), build)
    for r, _, fs in os.walk(build) for f in fs
)
with zipfile.ZipFile(zippath, "w", zipfile.ZIP_DEFLATED) as z:
    for arc in files:
        zi = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        with open(os.path.join(build, arc), "rb") as fh:
            z.writestr(zi, fh.read())
PY

echo "Built $ZIP ($(du -h "$ZIP" | cut -f1))"
"$PYTHON" -c "import zipfile,sys; [print(n) for n in zipfile.ZipFile(sys.argv[1]).namelist()]" "$ZIP"
