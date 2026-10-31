# syntax=docker/dockerfile:1.7

# =============================================================================
# SQ-Mine container image.
#
# Three stages, and the split is the point. "builder" produces a wheel,
# "test" installs that wheel and runs the whole quality gate against it, and
# "runtime" is what ships: no compiler, no test fixtures, no source tree and
# no root user. Testing the built wheel rather than the working directory is
# deliberate - it is the only way a packaging mistake shows up before release
# rather than after it.
#
#   docker build --target test    -t sqmine:test .     # fails if a test fails
#   docker build --target runtime -t sqmine:latest .
#   docker run --rm sqmine:latest --help
# =============================================================================

ARG PYTHON_VERSION=3.12

# ------------------------------------------------------------- build the wheel
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src

# Only the files the build backend actually reads. Copying the whole tree here
# would invalidate this layer on every edit to a test or an example.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --upgrade pip build \
 && python -m build --wheel --outdir /dist \
 && ls -l /dist

# -------------------------------------------------------------- the gate stage
FROM builder AS test

COPY tests ./tests
COPY examples ./examples
COPY docker/run-gate.sh /usr/local/bin/run-gate

# The wheel plus the pinned development extra, so the versions used here are
# the same ones pyproject.toml pins for continuous integration.
RUN WHEEL="$(ls /dist/*.whl)" && python -m pip install "${WHEEL}[dev]" \
 && chmod +x /usr/local/bin/run-gate \
 && mkdir -p /reports

# Deliberately not run at build time. See the comment at the top of
# run-gate.sh: a gate that runs during the build destroys its own report when
# it fails. The image carries the gate; continuous integration runs it.
CMD ["run-gate"]

# ----------------------------------------------------------------- the shipped
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG VERSION=0.3.0
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="sqmine" \
      org.opencontainers.image.description="Service-quality episode processing for data-mining research" \
      org.opencontainers.image.source="https://github.com/Aldidiyar/sqmine" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# A fixed uid, so a volume written by the container stays readable when the
# image is rebuilt and the account is recreated.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin sqmine

COPY --from=builder /dist/*.whl /tmp/
RUN python -m pip install /tmp/*.whl && rm -f /tmp/*.whl

# Nothing in this image needs to write outside the working directory, and the
# pseudonymisation key is mounted read-only at run time.
USER sqmine
WORKDIR /work

ENTRYPOINT ["sqmine"]
CMD ["--help"]
