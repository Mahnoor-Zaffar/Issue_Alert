#!/usr/bin/env bash
# Build docs/ for GitHub Pages from static/ with relative asset paths.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

rm -rf docs
mkdir -p docs/css docs/js

cp static/css/styles.css docs/css/
cp static/js/app.js docs/js/

sed \
  -e 's|href="/static/css/styles.css"|href="css/styles.css"|g' \
  -e 's|src="/static/js/app.js"|src="js/app.js"|g' \
  static/index.html > docs/index.html

touch docs/.nojekyll

echo "Built docs/ for GitHub Pages"
