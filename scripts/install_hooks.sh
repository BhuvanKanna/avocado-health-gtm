#!/usr/bin/env bash
# Installs a pre-commit hook that rebuilds the dashboard when its inputs change,
# so dist/ can never be committed stale. Optional but recommended.
set -euo pipefail
cd "$(dirname "$0")/.."

# mkdir -p .git/hooks would happily create a fake .git directory in a
# non-repo, and every later git command would then behave strangely for a
# reason nobody would connect back to this script.
if [ ! -d .git ]; then
  echo "Not a git repository yet." >&2
  echo "Run ./scripts/setup_github.sh first — it inits the repo and pushes." >&2
  exit 1
fi
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
if git diff --cached --name-only | grep -qE '^(data/|dashboard/dashboard_template\.html)'; then
  echo "pre-commit: rebuilding dashboard"
  python data/real_data.py >/dev/null
  python scripts/build_dashboard.py
  git add dashboard/dist
fi
HOOK
chmod +x .git/hooks/pre-commit
echo "✓ pre-commit hook installed"
