# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `Dockerfile` with three stages: a wheel build, a gate stage that runs the
  whole quality check against that wheel, and a runtime image with no build
  tools and a non-root user.
- `docker/run-gate.sh`, the gate itself, written as a script so that it runs
  when the container runs rather than when the image is built. A gate that
  fails during a build takes its own JUnit report down with the layer.
- `Jenkinsfile`: a seven-stage declarative pipeline covering checkout, test
  image, quality gate with test reporting, runtime image, smoke test, and
  optional registry push and Kubernetes deployment.
- `docker-compose.yml` and `jenkins/`: a Jenkins controller declared in
  Configuration as Code, with the `sqmine-ci` job created on first boot.
- `k8s/`: namespace, sample input, and a CronJob that runs the ingestion as a
  batch workload, plus `k8s/deploy.sh` for a local cluster.
- A `container` job in the GitHub Actions workflow that builds both image
  stages and runs the gate inside the container on every push.

### Changed
- Development tools are version-bounded in `pyproject.toml`. `ruff` is pinned
  exactly because its formatter rewrites source; the rest are capped below
  their next major version.

### Fixed
- The formatter check failed in CI while passing locally. Recent `ruff`
  versions format Python code blocks inside Markdown as well, and one block in
  `README.md` had eight spaces before an inline comment where the formatter
  wants two.

## [0.3.0] - 2026-03-12

### Added
- `sqmine agreement` command and `sqmine.agreement` module: observed agreement,
  Cohen's kappa, Landis and Koch bands, and a pass/fail gate at kappa 0.70.
- `--fail-under` on `sqmine ingest`, so a batch with too many rejected rows
  fails the pipeline instead of silently producing a short file.
- Command-line smoke test in CI that runs the exact commands the README shows.

### Changed
- `extract_features` now sorts its input by opening time instead of assuming it
  is sorted. Unsorted input previously produced plausible but wrong
  repeat-contact counts.
- Text redaction now recognises ten-digit local telephone numbers written
  without a country code.

### Fixed
- Twelve-digit national identification numbers were being labelled `[PHONE]`
  because the telephone pattern was evaluated first.

## [0.2.0] - 2026-02-24

### Added
- `ContactCentreJsonAdapter` for nested JSON call records.
- `LoadResult` and `Reject`: malformed rows are now collected with a reason
  rather than aborting the batch.
- `sqmine features` command and the feature extraction module.

### Changed
- Adapters are registered through `@register_adapter` and looked up by name,
  so the CLI no longer imports each adapter class explicitly.

## [0.1.0] - 2026-02-10

### Added
- Canonical `Episode` schema with validation and JSON round-tripping.
- `Pseudonymiser`: keyed HMAC-SHA256 references, deterministic and irreversible
  without the key.
- `CrmCsvAdapter` for the CSV transaction-log export.
- Project scaffolding: packaging, licence, linting, typing, CI.
