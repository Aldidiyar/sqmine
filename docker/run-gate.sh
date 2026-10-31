#!/bin/sh
# The whole quality gate, in the order that fails cheapest first: style, then
# types, then the test suite. Written as a script rather than a chain of RUN
# instructions so that it executes when the container runs, not when the image
# is built. That distinction matters: a test that fails during a build takes
# its layer down with it, and the JUnit report dies inside the discarded
# layer. Run it instead and the report survives in a stopped container, where
# continuous integration can copy it out and show the failure.
set -eu

REPORTS="${REPORTS:-/reports}"
mkdir -p "$REPORTS"

echo "--- ruff check -------------------------------------------------------"
ruff check --output-format=concise .

echo "--- ruff format ------------------------------------------------------"
ruff format --check .

echo "--- mypy -------------------------------------------------------------"
python -m mypy

echo "--- pytest -----------------------------------------------------------"
python -m pytest -q \
    --cov=sqmine \
    --cov-report=term-missing \
    --cov-report=xml:"$REPORTS/coverage.xml" \
    --junitxml="$REPORTS/junit.xml" \
    --cov-fail-under=90

echo "--- documented pipeline ----------------------------------------------"
python -c "import secrets, pathlib; pathlib.Path('/tmp/k').write_bytes(secrets.token_bytes(32))"
sqmine ingest examples/crm_sample.csv --adapter crm-csv --tenant gate \
    --key-file /tmp/k --out /tmp/episodes.jsonl --fail-under 0.8
sqmine features /tmp/episodes.jsonl --out /tmp/features.csv --stats
sqmine agreement examples/labels_sample.csv --col-a annotator_a --col-b annotator_b

if grep -qE 'CL-[0-9]+|OP-[0-9]+' /tmp/episodes.jsonl; then
    echo "FAIL: a raw identifier reached the canonical output" >&2
    exit 1
fi
echo "no raw identifiers in the canonical output"

echo "--- gate passed ------------------------------------------------------"
