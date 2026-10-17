#!/bin/sh
# Packs UnNetHack for av: dist/unnethack-<target>.tar.gz, from the list in
# asciiverse/archive/unnethack.txt: one file per line, relative to the
# repo root, all placed side by side at the top of the archive; "src ->
# name" renames. (The same script as the BSD games', which pack several
# titles from one repo.)
#
#   asciiverse/package.sh x86_64-unknown-linux-musl
set -eu
cd "$(dirname "$0")/.."
target="$1"
case "$target" in *windows*) exe=.exe ;; *) exe= ;; esac
mkdir -p dist
for list in asciiverse/archive/*.txt; do
  id=$(basename "$list" .txt)
  stage="stage/$id"
  rm -rf "$stage" && mkdir -p "$stage"
  grep -v '^#' "$list" | while read -r src arrow name; do
    [ -n "$src" ] || continue
    case "$src" in out/*) [ -f "$src$exe" ] && src="$src$exe" ;; esac
    if [ "$arrow" = "->" ]; then cp "$src" "$stage/$name"; else cp "$src" "$stage/"; fi
  done
  if [ -n "$exe" ]; then
    (cd "$stage" && zip -qr "../../dist/$id-$target.zip" .)
  else
    tar -czf "dist/$id-$target.tar.gz" -C "$stage" .
  fi
done
ls dist
