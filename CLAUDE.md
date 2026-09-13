# CLAUDE.md

Read this first, every session.

## What this is

The go-to-market and outbound pipeline for **Avocado Health**, a text-based
parent decision-support platform sold as white-labeled infrastructure to public
health agencies, health plans, FQHCs and community organizations.

Owner: Bhuvan Kanna, BD/GTM intern. Reports to Hans Kullberg, CEO.
Started July 28, 2026. MNDA executed August 9, 2026.

The question the whole repo exists to answer, in Hans's words:

> "How do we identify the right opportunities — and more importantly, the right
> people and contacts as target partners/collaborators to win them? Once
> established, how do we efficiently connect to them?"

## Before you write any code, read these

| Path | What it holds | When it matters |
|---|---|---|
| `context/00-project-brief.md` | Charter, scope, glossary, working rules | always |
| `context/01-company-profile.md` | Product, evidence base, proof points, **liability boundaries** | any product claim |
| `context/02-icp-and-targets.md` | 8 core ICP segments, economics, tiering, GTM sequencing | deciding *who* |
| `context/03-funding-landscape.md` | RHTP, HR1, grants, reimbursement, procurement | deciding *when* |
| `context/04-outreach-pipeline.md` | Stages, scoring model, tooling, cadence, metrics | **the core doc** |
| `context/05-messaging-playbook.md` | Per-segment value props, objections, templates | anything outbound |
| `context/06-white-label-positioning.md` | Brand-visibility strategy, deployment tiers | positioning |
| `context/07-engagement-log.md` | Timeline, decisions, open questions, action items | status, follow-ups |

**Non-redundancy rule:** each fact lives in exactly one doc. Others
cross-reference by number. Update the source doc only.

## Repository map

```
context/          The eight project docs. Source of truth for strategy.
                  Treat as read-mostly; update 07 after every Hans exchange.

data/
  real_data.py            Builds the dashboard payload. Run to regenerate.
  real_data.json          Generated. CMS 50-state awards + parsed editions.
  editions/               One module per transcribed briefing edition.
  briefings/              Raw Civic Operator source documents, by date.
  contacts-resolved.csv   Output of tools/contact_resolve.py.

dashboard/
  dashboard_template.html Source. Contains __DATA__ placeholder.
  dist/                   Built artifact. This is what gets sent to Hans.

tools/
  fetch_live.py           USAspending puller. --all is the important mode.
  contact_resolve.py      Email pattern learning + role classification.
  demo_briefing.py        Edition snapshot + diff, no ML.

research/
  avocado_pap/            The ML harness: LambdaRank ranker, PU fit model,
                          temporal backtest, ablation selection, allocator.
                          Runs on simulated data. NOT shipped to partners.
  docs/                   The written spec and backtest.

scripts/                  Repo automation. See "Git discipline" below.
notes/                    Session notes, scratch, meeting summaries.
```

## Build and run

```bash
pip install lightgbm scikit-learn pandas numpy scipy

# regenerate the dashboard after any data change
cd data && python real_data.py && cd ..
python scripts/build_dashboard.py          # writes dashboard/dist/

# pull real award data (needs network; exits 2 if unreachable)
python tools/fetch_live.py --all

# resolve contacts from a briefing
python tools/contact_resolve.py data/real_data.json --csv data/contacts-resolved.csv

# the research harness (simulated; ~4 min)
cd research && python -m avocado_pap.pipeline.run
```

## Git discipline — commit after every change

**This repo is committed and pushed after every change you make.** Not at the
end of a session, not when something feels finished. Every change.

The reason is specific to this project: the dashboard's value is that it
accumulates. Editions, contact resolutions, score-weight tunings and corrections
compound over months, and an uncommitted local change is a change that silently
didn't happen. The same logic that makes the diff engine worth building makes
the commit history worth keeping.

After any edit:

```bash
./scripts/commit.sh "what changed and why"
```

That script stages, commits and pushes. If you have made a change and not run
it, the change is not done.

Commit message format — imperative, one line, name the file area:

```
data: add 2026-09-17 edition, 3 new VA contacts
dashboard: fix opportunity key matching across editions
context: update 07 engagement log after Hans call
research: drop staff-model family from Model A per ablation
```

**Never commit:** anything under `outputs/`, `.env`, API keys, or a file with
a credential in it. `.gitignore` covers the known cases; check before adding a
new file type.

## Confidentiality — read this before pushing anywhere

This repository contains:

- Named individuals at public agencies and private organizations, with **email
  addresses and direct telephone numbers** (`data/contacts-resolved.csv`,
  `data/editions/`, `data/briefings/`)
- MNDA-covered material: the ICP matrix economics, the HMA white-labeling
  report's conclusions, Riverside brief structure, partner names
- Civic Operator briefings, marked Confidential on every page

**The GitHub repository must be private.** The setup commands in
`scripts/setup_github.sh` pass `--private` and will refuse to run otherwise.
Do not make it public, do not add collaborators outside Avocado, and do not
push to a fork.

Nothing in `context/`, `data/` or `research/` goes into an outbound email, a
proposal, or a partner conversation. The only artifact intended to leave the
repo is `dashboard/dist/avocado-pipeline.html`, and that is for Hans, not for
partners.

## Hard rules that govern the work

These come from `context/00` §4 and `context/01` §6. They are liability lines,
not style preferences.

1. **Avocado is usually the subcontractor, not the prime.** Hawaii was won *by*
   Healthy Mothers Healthy Babies; Avocado was the platform underneath and let
   the partner take the credit. Every ranking, score and message assumes this.
2. **The unit of pursuit is the organization likely to win the money**, not the
   solicitation. An RFP is a signal that a cohort is about to have money.
3. **The offer is the podcast, not the demo.** Cold email is the weakest
   channel. Don't lead with a sales ask.
4. **Never make medical claims.** Evidence-based information, not diagnosis.
   No decision-tree symptom checkers.
5. **Flag assumptions.** Mark unverified things `[UNCONFIRMED]` rather than
   filling the gap.
6. **Cite the source doc** when producing analysis, so a claim can be checked.

## How the scoring works, in one paragraph

Two scores. The **state opportunity index** combines unmoved money
(`FY26 award − observed subawards`), CMS's own discretionary allocation
(`award − $100,000,000`, which is CMS's dollar-denominated rural-need scoring
under PL 119-21), observed signal activity and contact reachability. The
**target score** combines ICP fit, state opportunity, reach, urgency,
subgrant/role fit and prior award history, then multiplies by a play factor that
discounts issuing agencies relative to applicants. Expected value multiplies by
segment ACV and discounts by cycle length. Full derivation is in the dashboard's
Algorithm tab and in `research/docs/prime-applicant-prediction.html`.

**There is no trained model in the shipped dashboard, deliberately.** RHTP has
produced one round of first-tier awards. Training on that would be fitting
noise and calling it intelligence. The learned ranker exists in `research/` and
drops in when the label history does.

## Current state, as of 2026-09-13

- 50 states loaded (CMS FY26 awards, exact, primary source)
- 10 states covered by briefings; 6 with observed subaward movement, $124.3M
- 52 scored organizations, 7 of which already hold RHTP money
- 2 editions stored; 90 change events between them
- 70 contacts, 21 email-domain patterns learned, 36 corroborated, 1 flagged

## Open items — check `context/07` for the live list

The highest-priority ones are not code:

- **A-6** reply to Hans's Aug 21 check-in — overdue
- **A-4** infrastructure GTM study (Stripe/Shopify/Twilio) — explicitly
  requested Aug 14, still open
- **B-5** fill the ICP matrix name column — flagged as the clearest handoff
- **O-4** ask for inbound RHT form leads before building more outbound

If you are about to build something new, check whether one of these would be
worth more first. Usually it is.

## Working style

- Say what you actually did, including what broke. Two bugs in this codebase
  were found by smoke tests, not by reasoning: duplicate contact names
  collapsing in the diff index, and opportunity titles not matching across
  editions. Both silently swallowed the highest-priority signal. Assume there
  are more wherever two documents name the same thing differently.
- Prefer deterministic and checkable over clever. A pattern-matching email
  resolver whose output a human can verify beats a model whose output they
  cannot.
- Never merge an inferred value into a verified column. Separate fields,
  always.
- When a network call fails, fail loudly. `fetch_live.py` exits 2 rather than
  writing an empty file, because "API unreachable" and "no state has moved
  money yet" must never look identical.
