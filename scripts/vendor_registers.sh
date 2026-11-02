#!/usr/bin/env bash
# Vendor the research schemas (finding/source/protection) and the disease vocabulary
# (diseases.json: the five diseases and their 25 causes) from a pinned release of
# github.com/demitonapp/registers, which is their source of truth (spec 09 P4, SM070/P1).
#
#   scripts/vendor_registers.sh v1
#
# Dev-time only - CI validates against the committed vendored copy, it never fetches
# the registers repo itself. Bumping the pin is this script plus an ordinary PR.
set -euo pipefail
tag="${1:?usage: vendor_registers.sh <tag, e.g. v1>}"
dest="$(cd "$(dirname "$0")/.." && pwd)/vendor/registers-research"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

gh release download "$tag" --repo demitonapp/registers --pattern "registers-research-*.tar.gz" --dir "$tmp" --clobber
asset="$(ls "$tmp"/registers-research-*.tar.gz)"
rm -rf "$dest"
mkdir -p "$dest"
tar -xzf "$asset" -C "$tmp" research vocab/diseases.json
cp "$tmp"/research/*.schema.json "$tmp/vocab/diseases.json" "$dest/"

echo "$tag" > "$dest/VENDORED_TAG"
count="$(ls "$dest"/*.schema.json | wc -l | tr -d ' ')"
echo "vendored registers $tag research/ -> $dest ($count schemas)"
