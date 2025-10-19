#!/usr/bin/env bash
set -euo pipefail
manifest="docs/Claudedocs/SeedSetup/manifests_seed_papers.csv"
dest="assets/papers"
mkdir -p "$dest"

tail -n +2 "$manifest" | while IFS=, read -r slug title doi pdf_url source_url domain dataset_hint notes; do
  if [ -z "${pdf_url// }" ]; then
    echo "SKIP: $slug (no direct PDF; use Unpaywall or save page as PDF)"
    continue
  fi
  out="$dest/${slug}.pdf"
  if [ -f "$out" ]; then
    echo "EXISTS: $slug"
  else
    echo "DOWNLOADING: $slug"
    curl -sSL "$pdf_url" -o "$out"
  fi
done
echo "Done."
