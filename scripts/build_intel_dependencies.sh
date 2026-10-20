#!/usr/bin/env bash
# Explicit native build recipe. Changes invalidate the reusable library key.
set -euo pipefail
export MACOSX_DEPLOYMENT_TARGET=14.0
export OPENSSL_STATIC=1
export OPENSSL_DIR="$RUNNER_TEMP/openssl-install"
python_path="$PWD/.venv/bin/python"
(
  cd "$RUNNER_TEMP/openssl-build/upstream"
  ./Configure darwin64-x86_64-cc no-shared no-module --libdir=lib \
    --prefix="$OPENSSL_DIR" -mmacosx-version-min=14.0
  make -j3
  HARNESS_JOBS=3 make test
  make install_sw
)
uv build "$RUNNER_TEMP/crypto-build/source.tar.gz" --wheel --no-build-isolation \
  --python "$python_path" --out-dir "$RUNNER_TEMP/intel-wheel"
{
  rustc --version
  cargo --version
  clang --version
  "$OPENSSL_DIR/bin/openssl" version
  sw_vers
} > "$RUNNER_TEMP/intel-wheel/toolchain.txt"
