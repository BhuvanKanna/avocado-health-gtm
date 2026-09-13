#!/usr/bin/env bash
# One-time setup. Creates a PRIVATE GitHub repo and pushes the initial commit.
#
#   ./scripts/setup_github.sh                 # default name
#   ./scripts/setup_github.sh my-repo-name
#
# Requires the GitHub CLI: https://cli.github.com  →  gh auth login
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="${1:-avocado-health-gtm}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI not found. Install it (brew install gh) then: gh auth login" >&2
  exit 1
fi
gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login" >&2; exit 1; }

# This repo holds named contacts with emails and direct phone numbers, plus
# MNDA-covered material. Private is not a preference here.
echo "Creating PRIVATE repository: $NAME"

if [ ! -d .git ]; then
  git init -b main
fi

git add -A
git commit -m "initial: Avocado Health GTM pipeline, context, tools and dashboard" || true

gh repo create "$NAME" --private --source=. --remote=origin --push

echo
echo "✓ Private repo created and pushed."
gh repo view --json nameWithOwner,visibility,url -q \
  '"  " + .nameWithOwner + "  (" + .visibility + ")\n  " + .url'

./scripts/install_hooks.sh || true

echo
echo "From here on, after every change:"
echo "  ./scripts/commit.sh \"what changed and why\""
echo
echo "Then point Claude Code at this directory:"
echo "  claude"
echo "It reads CLAUDE.md on start."
