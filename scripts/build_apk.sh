#!/usr/bin/env bash
# Build the KBOS debug APK locally (no EAS) and optionally install it.
#   scripts/build_apk.sh            # build
#   scripts/build_apk.sh --install  # build + adb install -r + grant permissions
#   scripts/build_apk.sh --release  # standalone APK with the JS bundle embedded (the demo build)
#   scripts/build_apk.sh --prebuild # regenerate app/android first (after native dep/app.json changes)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export JAVA_HOME="${JAVA_HOME_KBOS:-$(ls -d "$HOME"/.local/jdk/jdk-21* 2>/dev/null | head -1)}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
cd "$ROOT/app"

if [[ " $* " == *" --prebuild "* || ! -d android ]]; then
  CI=1 npx expo prebuild -p android --clean --no-install
fi
P=android/gradle.properties
sed -i 's/^org.gradle.jvmargs=.*/org.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=768m/' $P
sed -i 's/^reactNativeArchitectures=.*/reactNativeArchitectures=arm64-v8a/' $P
grep -q '^org.gradle.workers.max' $P || printf '\norg.gradle.workers.max=4\n' >> $P
grep -q '^org.gradle.java.home' $P || printf 'org.gradle.java.home=%s\norg.gradle.java.installations.paths=%s\norg.gradle.java.installations.auto-download=false\n' "$JAVA_HOME" "$JAVA_HOME" >> $P
echo "sdk.dir=$ANDROID_HOME" > android/local.properties

VARIANT=Debug
[[ " $* " == *" --release "* ]] && VARIANT=Release
(cd android && ./gradlew assemble$VARIANT --max-workers=4)
APK=android/app/build/outputs/apk/${VARIANT,,}/app-${VARIANT,,}.apk
ls -la "$APK"

if [[ " $* " == *" --install "* ]]; then
  adb install -r "$APK"
  for p in RECORD_AUDIO CAMERA POST_NOTIFICATIONS; do adb shell pm grant com.kbos.app android.permission.$p || true; done
fi
