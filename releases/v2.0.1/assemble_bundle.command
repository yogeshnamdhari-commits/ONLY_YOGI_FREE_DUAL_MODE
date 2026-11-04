#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

ARCHIVE="ONLY_YOGI_SIGNAL_ENGINE_PORT_8508.zip"
cat bundle.part*.b64 | tr -d '\n' | base64 -D > "$ARCHIVE"

echo "Checking SHA-256..."
echo "5f2381e825c7c4886152ccd35852ebf8f5a119ed301099b96f0aefd08e8148ac  $ARCHIVE" | shasum -a 256 -c -

echo "Checking ZIP integrity..."
unzip -t "$ARCHIVE"

echo
echo "Package reconstructed successfully:"
pwd
echo "$ARCHIVE"
