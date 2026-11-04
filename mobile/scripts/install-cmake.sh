
#!/usr/bin/env bash
set -euo pipefail

if [ "${EAS_BUILD_PLATFORM:-}" != "android" ]; then
  exit 0
fi

SDK_ROOT="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"

if [ -z "$SDK_ROOT" ]; then
  echo "ERROR: Android SDK location not found"
  exit 1
fi

SDKMANAGER="$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"

if [ ! -x "$SDKMANAGER" ]; then
  SDKMANAGER="$(command -v sdkmanager || true)"
fi

if [ -z "$SDKMANAGER" ] || [ ! -x "$SDKMANAGER" ]; then
  echo "ERROR: sdkmanager not found"
  exit 1
fi

echo "Checking Android SDK licenses..."

set +o pipefail
yes | "$SDKMANAGER" --sdk_root="$SDK_ROOT" --licenses >/dev/null
LICENSE_STATUS=${PIPESTATUS[1]}
set -o pipefail

if [ "$LICENSE_STATUS" -ne 0 ]; then
  echo "ERROR: Android SDK license acceptance failed"
  exit "$LICENSE_STATUS"
fi

echo "Installing CMake 3.31.6..."

"$SDKMANAGER" --sdk_root="$SDK_ROOT" "cmake;3.31.6"

echo "Verifying CMake installation..."

test -x "$SDK_ROOT/cmake/3.31.6/bin/cmake"

"$SDK_ROOT/cmake/3.31.6/bin/cmake" --version

echo "CMake 3.31.6 installation completed successfully."
