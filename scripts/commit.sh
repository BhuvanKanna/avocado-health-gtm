#!/usr/bin/env bash
# Stage, commit and push. Run after every change.
#
#   ./scripts/commit.sh "data: add 2026-09-17 edition"
#
# Rebuilds the dashboard first when data or template changed, so dist/ never
# drifts from its source. Refuses to push a repo that is not private.
set -euo pipefail
cd "$(dirname "$0")/.."

MSG="${1:-}"
if [ -z "$MSG" ]; then
  echo "usage: ./scripts/commit.sh \"what changed and why\"" >&2
  exit 1
fi

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files -o --exclude-standard)" ]; then
  echo "nothing to commit"
  exit 0
fi

# Rebuild if anything the dashboard depends on moved.
if ! git diff --quiet -- data dashboard/dashboard_template.html 2>/dev/null \
   || git ls-files -o --exclude-standard -- data | grep -q .; then
  echo "→ data or template changed, rebuilding dashboard"
  python data/real_data.py >/dev/null && python scripts/build_dashboard.py
fi

# Guard: never push this repo to a public remote.
if command -v gh >/dev/null 2>&1 && git remote get-url origin >/dev/null 2>&1; then
  VIS=$(gh repo view --json visibility -q .visibility 2>/dev/null || echo UNKNOWN)
  if [ "$VIS" = "PUBLIC" ]; then
    echo "REFUSING TO PUSH: remote is PUBLIC." >&2
    echo "This repo holds named contacts with emails and phone numbers, plus" >&2
    echo "MNDA-covered material. Run: gh repo edit --visibility private" >&2
    exit 1
  fi
fi

git add -A
git commit -m "$MSG"

# No remote yet is the state a fresh clone-less setup is in. Say so plainly
# rather than surfacing git's "please specify which branch" wall of text.
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "✓ committed locally: $MSG"
  echo
  echo "No remote configured yet. Run ./scripts/setup_github.sh to create the"
  echo "private GitHub repo and push everything."
  exit 0
fi

# First push needs upstream tracking; subsequent ones do not.
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git push
else
  git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
fi
echo "✓ pushed: $MSG"
