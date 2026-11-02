#!/bin/bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source_file="${1:-$root/Sources/App/Services/AssemblyAIStreamingClient.swift}"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/blablabla-streaming-tests.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

# Compile in one file so the tests can inspect private connection state without
# adding test-only accessors or dependencies to the app.
cat "$source_file" "$root/Tests/StreamingSessionTests.swift" > "$scratch/main.swift"
swiftc -swift-version 5 "$scratch/main.swift" -o "$scratch/streaming-tests"
"$scratch/streaming-tests"
