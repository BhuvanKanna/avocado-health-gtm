# Start here

```bash
cd avocado-health-gtm
./scripts/setup_github.sh     # creates a PRIVATE GitHub repo, pushes, installs hooks
claude                        # Claude Code reads CLAUDE.md automatically
```

That is the whole setup. `setup_github.sh` needs the GitHub CLI
(`brew install gh` then `gh auth login`).

**No GitHub yet?** Skip it. `claude` works on the directory as-is; run
`./scripts/setup_github.sh` whenever you are ready.

## After every change

```bash
./scripts/commit.sh "data: add 2026-09-17 edition, 3 new VA contacts"
```

Rebuilds the dashboard if its inputs moved, commits, pushes. Refuses to push
if the remote is public.

## To just look at the dashboard

Open `dashboard/dist/avocado-pipeline.html` in a browser. Nothing to install.

## To rebuild it

```bash
pip install lightgbm scikit-learn pandas numpy scipy
python data/real_data.py
python scripts/build_dashboard.py
```

## Keep it private

This directory holds named individuals with emails and direct phone numbers,
plus MNDA-covered material and briefings marked Confidential. The scripts
enforce a private remote. Read the Security section of `README.md` before
sharing any of it.

---
Full map: `CLAUDE.md` · Human overview: `README.md`
