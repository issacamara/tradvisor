#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
spec="$repo_root/frontend/src/api/generated/openapi.json"
types="$repo_root/frontend/src/api/generated/schema.d.ts"
temporary_spec="$(mktemp)"
temporary_types="$(mktemp)"
trap 'rm -f "$temporary_spec" "$temporary_types"' EXIT

cd "$repo_root"
python3 -m backend.openapi --check
npm --prefix scripts/generate-client ci --ignore-scripts --no-audit --no-fund
npm --prefix scripts/generate-client exec -- openapi-typescript "$spec" --output "$temporary_types"
cmp "$types" "$temporary_types"
