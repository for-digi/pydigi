# Build pydigi's wheel in an isolated image.
#
# pydigi is pure Python and ships a wheel only (no sdist). The build never
# touches your host Python. Run it via scripts/docker-build.sh, or directly with
# BuildKit's filesystem export:
#
#   DOCKER_BUILDKIT=1 docker build --target export \
#       --output type=local,dest=./dist .
#
# The final `export` stage is FROM scratch, so `--output` drops exactly the
# wheel into ./dist and nothing else.

# --- build stage: produce the wheel ---------------------------------------
FROM python:3.12-slim AS build

WORKDIR /src

# 'build' is the PEP 517 front-end; it creates its own isolated build env.
RUN pip install --no-cache-dir build==1.2.2

# Copy sources (see .dockerignore for what stays out) and build the wheel.
COPY . .
RUN python -m build --wheel --outdir /artifacts \
    && ls -l /artifacts

# --- export stage: nothing but the wheel ----------------------------------
FROM scratch AS export
COPY --from=build /artifacts/ /
