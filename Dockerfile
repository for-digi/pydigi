# Build pydigi's distributable artifacts (sdist + wheel) in an isolated image.
#
# The build never touches your host Python. Run it via scripts/docker-build.sh,
# or directly with BuildKit's filesystem export:
#
#   DOCKER_BUILDKIT=1 docker build --target export \
#       --output type=local,dest=./dist .
#
# The final `export` stage is FROM scratch, so `--output` drops exactly the two
# artifacts into ./dist and nothing else.

# --- build stage: produce the artifacts -----------------------------------
FROM python:3.12-slim AS build

WORKDIR /src

# 'build' is the PEP 517 front-end; it creates its own isolated build env.
RUN pip install --no-cache-dir build==1.2.2

# Copy sources (see .dockerignore for what stays out) and build.
COPY . .
RUN python -m build --sdist --wheel --outdir /artifacts \
    && ls -l /artifacts

# --- export stage: nothing but the artifacts ------------------------------
FROM scratch AS export
COPY --from=build /artifacts/ /
