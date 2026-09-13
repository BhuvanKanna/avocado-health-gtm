# Avocado Health — GTM pipeline

Go-to-market and outbound pipeline for Avocado Health's Rural Health
Transformation Program work. Identifies which organizations will win RHTP and
adjacent maternal/child health money, which of those need a technology layer,
and how to reach the right person inside them.

**Confidential.** MNDA between Avocado Health and Bhuvan Kanna, 2026-08-09.
Contains named individuals with contact details. Keep the repository private —
see [Security](#security).

If you are Claude Code, read [`CLAUDE.md`](CLAUDE.md) first.

## Quick start

```bash
git clone <your-private-repo-url> && cd avocado-health-gtm
pip install lightgbm scikit-learn pandas numpy scipy

python data/real_data.py            # regenerate the payload
python scripts/build_dashboard.py   # → dashboard/dist/avocado-pipeline.html
open dashboard/dist/avocado-pipeline.html
```

No server, no API keys, no install for the dashboard itself. It runs from the
file system and stores editions in browser local storage.

## First-time GitHub setup

```bash
./scripts/setup_github.sh            # creates a PRIVATE repo and pushes
./scripts/install_hooks.sh           # optional: rebuild dist/ on commit
```

Then, **after every change**:

```bash
./scripts/commit.sh "data: add 2026-09-17 edition, 3 new VA contacts"
```

`commit.sh` rebuilds the dashboard if its inputs moved, refuses to push if the
remote is public, then commits and pushes.

## Layout

```
CLAUDE.md          Project map and working rules. Start here.
context/           The eight strategy docs. Source of truth.
data/              Real data: CMS awards, briefing editions, resolved contacts.
dashboard/         Template, build output. dist/ is what goes to Hans.
tools/             fetch_live.py, contact_resolve.py, demo_briefing.py
research/          ML harness + written spec. Simulated data; never shipped.
scripts/           Build, commit, GitHub setup, hooks.
notes/             Session notes and call summaries.
```

## What's in the dashboard

Six tabs: ranked targets, 50-state opportunity index, contact resolution,
briefing upload with edition diffing, the algorithm explained, and full data
provenance.

Current state as of 2026-09-13:

| | |
|---|---|
| States loaded | 50 (CMS FY26 awards, exact) |
| States covered by briefings | 10 |
| Observed first-tier subaward movement | $124.3M across 6 states |
| Scored organizations | 52 |
| Organizations already holding RHTP money | 7 |
| Editions stored / change events between them | 2 / 90 |
| Contacts / domain patterns learned | 70 / 21 |

## Adding a briefing

Drop the PDF on the dashboard's **Add briefing** tab. It parses in-browser,
stores a dated snapshot, and diffs against the previous edition. Nothing leaves
the machine.

For an edition you want as permanent repo data rather than browser storage,
transcribe it into `data/editions/` following `edition_0910.py`, then rebuild.
Hand transcription beats regex for these: the PDF text layer interleaves table
columns, and a parser that mis-associates a name with the wrong organization
produces confident wrong contacts.

## Pulling live award data

```bash
python tools/fetch_live.py --all
```

Pulls every recipient of assistance listings 93.224, 93.505, 93.926, 93.994 and
93.798 — health centers, MIECHV home-visiting grantees, Healthy Start sites,
Title V agencies and RHTP recipients. That is a 50-state candidate universe that
exists whether or not any briefing mentions it. Drop the JSON on the Add-briefing
tab.

Exits 2 if the API is unreachable rather than writing an empty file. "API down"
and "no state has moved money yet" must never look the same.

## Security

The repository contains:

- Named individuals at public agencies and private organizations, with email
  addresses and direct telephone numbers
- MNDA-covered material: ICP matrix economics, HMA report conclusions, Riverside
  brief structure, partner names
- Civic Operator briefings, marked Confidential on every page

**Keep the repo private.** `setup_github.sh` passes `--private`; `commit.sh`
refuses to push to a public remote. Do not fork, do not add outside
collaborators, and do not paste `data/` contents into anything outbound.

The only artifact meant to leave this repo is
`dashboard/dist/avocado-pipeline.html`, and that is for Hans — not for partners.

## Research harness

`research/avocado_pap/` holds the full ML system: a LambdaRank applicant ranker
with isotonic calibration and split conformal, an Elkan-Noto PU fit model,
forward-chaining temporal validation, ablation-driven feature selection, an
equity audit and a portfolio allocator. It runs end to end on simulated data.

```bash
cd research && python -m avocado_pap.pipeline.run
```

**Simulation figures never appear in the dashboard and must never be quoted to
a partner.** The written spec and backtest are in
`research/docs/prime-applicant-prediction.html`. The learned ranker drops into
the dashboard's interface once real label history exists — roughly two more
subaward cycles, or a backfill via `fetch_live.py --all`.
