# 04 — Outreach Pipeline: The Operating Playbook

*The core operational doc. Everything else is input to this.*

---

## 1. The question this system answers

> Identify the right opportunities → the right organizations → the right people → the efficient path to reach them.

The system must be **repeatable without Bhuvan**, and its output must be **legible to management** as a ranked list with reasons.

## 2. The founding insight: pursue the applicant, not the opportunity

Most B2G pipelines are built as: *find RFP → bid on RFP*. **That is the wrong model for Avocado, and the Hawaii win proves it.**

Avocado did not win the Hawaii DOH RFP. **Healthy Mothers Healthy Babies won it.** Avocado was the technology underneath, and — deliberately — let the partner take the credit. The customer got to look good; Avocado got a $1M/yr deployment and a state DOH reference.

This has four consequences that shape the entire pipeline:

1. **The unit of pursuit is an organization likely to win or administer funding — not the funding itself.** An RFP is a *signal that a cohort of organizations is about to have money*, not a thing to bid on.
2. **The pitch is not "buy our product." It is "we make your application stronger and your delivery cheaper."** The prospect's motivation is winning *their* funding.
3. **Timing runs earlier than the RFP.** By the time an RFP posts, the applicant has usually chosen partners. The window is 3–12 months *before* the solicitation.
4. **Every win compounds upstream.** A CBO deployment creates a state DOH reference, which makes the next CBO easier and eventually makes a direct GOV deal possible.

**Corollary — the highest-leverage target profile:**
> A mission-aligned CBO, perinatal network, First 5, or FQHC that (a) sits in a state with programmed RHTP or maternal/child dollars, (b) already employs CHWs / home visitors / doulas whose time Avocado saves, (c) has a grant or RFP cycle in the next 3–9 months, and (d) has no incumbent engagement platform.

That profile is the scoring model in §4.

## 3. Pipeline stages

```
S0 SOURCE  →  S1 SCORE  →  S2 MAP  →  S3 PATH  →  S4 ENGAGE  →  S5 QUALIFY  →  S6 COLLABORATE  →  S7 CLOSE
 signal      prioritize   find the    find the    podcast-      fit + funding   co-build the     Hans /
 capture     A/B/C        humans      warm route  first ask     + timing        proposal         leadership
```

### S0 — Source
Continuous capture of three signal types into one target table:

| Signal type | What it looks like | Where it comes from |
|---|---|---|
| **Money signals** | RHTP state allocations, posted/forthcoming RFPs, grant NOFOs, budget line items, council/board approvals | Civic Operator, RHTP Hub Portal, Grants.gov |
| **Organization signals** | Entities that won similar awards before, orgs with CHW/home-visiting/doula programs, First 5 county commissions, FQHC networks, perinatal collaboratives | Civic Operator award history, HRSA/state directories |
| **Person signals** | New MCH director hires, program-officer moves, conference speakers, podcast-suitable thought leaders | LinkedIn, conference agendas, podcast research |

**Rule:** never source a bare opportunity. Every opportunity row must resolve to at least one candidate *organization* before it enters scoring. An unresolved opportunity is not a lead.

### S1 — Score
Apply the model in §4. Assign A / B / C. Only A and B advance. C's are archived with the reason, so the archive itself becomes training data for the model.

### S2 — Map
For each A/B organization, identify **3 named humans**:
- **Economic buyer** — the title from `02` that controls the budget line
- **Champion** — the operational person whose time Avocado saves (CHW supervisor, home-visiting director, care-coordination lead). *This person is usually the actual entry point.*
- **Gatekeeper/blocker** — IT/compliance, procurement, or the incumbent-vendor owner

Capture: name, title, email, LinkedIn, tenure, and one specific, non-generic thing about their work.

### S3 — Path
Rank the route in strictly this order:
1. **Warm intro** — existing partner, advisor, investor (1752vc), foundation program officer, clinical team member's network, Hawaii/HMHB reference
2. **Podcast invitation** — the highest-converting cold-ish channel
3. **LinkedIn** — hit or miss, use when there's a specific hook
4. **Cold email** — lowest yield; use only with a hard, dated, specific trigger (e.g., "your state's RHT plan names maternal health and the subaward window closes in March")

Never skip to 4 because 1 is slow. A warm path is worth roughly ten cold attempts.

### S4 — Engage
**The ask is a podcast conversation, not a demo.** Hans's stated finding: getting people to book a meeting with the potential of coming on the podcast is the highest-converting, most effective path to a meeting.

Why this works structurally: it inverts the value exchange. A demo request asks the prospect for time; a podcast invitation offers them visibility and positions them as the expert. It also produces content, builds the foundation/thought-leader network, and gives a second, non-sales reason to follow up.

Sequence: invite → record → publish → promote them → *then* the partnership conversation happens as a peer, not a vendor.

Templates in `05`.

### S5 — Qualify
Four gates. All four must clear before Hans's time is spent:
- **Funding** — is there money, and from which line? (see `03 §4`)
- **Fit** — do they serve the population, and do they employ staff Avocado offloads?
- **Timing** — is there a decision or application window in the next 3–9 months?
- **Role** — can Avocado be the tech layer, or would we have to be the prime? (Prefer the former.)

### S6 — Collaborate
Co-build. Reusable assets: the Riverside brief structure (`01 §5`) is the template — anchor to the partner's *own* published research and stated priorities, propose a phased pilot in their most underserved districts, enroll through their existing touchpoints so it requires no new hires, and lead with safety rails.

### S7 — Close
Hand to Hans/leadership. Log the outcome and the reason, win or lose, back into S1 scoring.

## 4. The scoring model

Score each target organization 0–5 on seven dimensions. Multiply by weight. **Max 65.**

| # | Dimension | Weight | 0 | 5 |
|---|---|---|---|---|
| 1 | **Funding certainty** | ×3 | No identified money | Money appropriated/awarded and unspent, or a live posted solicitation |
| 2 | **Timing fit** | ×2 | No decision window in 18 mo | Decision or application window in 3–9 months |
| 3 | **ICP tier fit** | ×2 | Deprioritized segment (e.g., private pediatric clinic) | Tier-1 segment per `02` |
| 4 | **Role fit** | ×2 | Avocado would have to be prime contractor | Clean tech-layer/subcontractor slot under a willing prime |
| 5 | **Warm path strength** | ×2 | Fully cold, no shared network | Direct intro available from partner, advisor, or investor |
| 6 | **Deal size** | ×1 | <$15K ACV | >$250K ACV |
| 7 | **Competitive whitespace** | ×1 | Entrenched incumbent platform, recently renewed | No incumbent; manual/phone-based today |

**Tiers:** **A ≥ 45** (work now) · **B 32–44** (nurture, revisit on trigger) · **C < 32** (archive with reason)

**Design notes — why these weights:**
- *Funding certainty* is ×3 because the Hawaii pattern shows the constraint is never product fit, it's whether money exists. A perfect-fit org with no budget is a 12-month waste.
- *Warm path* is ×2 and not ×1 because cold email is explicitly the weakest channel in this market. Reachability is a real qualifier, not a convenience.
- *Role fit* is ×2 because Avocado bidding as prime is off-strategy — it changes the cost structure, the liability posture, and who gets the credit.
- *Deal size* is only ×1 deliberately. Weighting it higher pulls the pipeline toward MCOs (9–36 month cycles) and starves the 3–6 month segments that fund the company. Large deals should enter via warm intro in parallel (`02 §5`), not by outranking near-term revenue.

## 5. Tooling — Civic Operator as the intelligence layer

**Decision (Aug 2026): Civic Operator is the designated market-intelligence platform. MNDA signed. It supersedes overlapping tools.**

### What Civic Operator replaces

| Retired / not purchased | Prior role | Why retired |
|---|---|---|
| **GovWin (Deltek)** — ~$7K–$13K+/yr | State/local RFP database; award history; applicant + winner contacts | Cost, and function now covered. Was always aspirational rather than committed. |
| **Manual RHTP Hub scraping** | State-by-state RHTP opportunity tracking (~$20/mo) | Keep the subscription as a **cross-check and source of truth for RHTP specifics**, but stop treating it as the primary workflow |
| **Ad-hoc Grants.gov monitoring** | Federal non-dilutive funding discovery | Fold into one monitored feed rather than a separate manual habit |
| **GovSpend / other B2G point tools** | Historical spend benchmarking | Not needed at current stage |

### What Civic Operator must cover (confirm against actual capabilities) `[UNCONFIRMED]`

The pipeline design depends on the following jobs being done. Verify each with Hans / the Civic Operator team, and note which are gaps:

- [ ] Federal + **state and local** solicitation coverage (SLED, not federal-only)
- [ ] **Pre-RFP signals** — budget lines, board/council actions, plan documents, contract expirations
- [ ] **Award history** — who has won similar work before (this is how we find prime-applicant candidates)
- [ ] **Named contacts** attached to agencies and awardees
- [ ] Grants / NOFO coverage alongside contracts
- [ ] Saved searches + alerting, and export/API for the dashboard
- [ ] Fit-scoring or capability matching that can be reconciled with the model in §4

### Known coverage gap — the healthcare-organization side

Civic Operator addresses the **government/opportunity** half of the ICP set (GOV, RHTP, grants). It likely does **not** cover firmographics and contacts for **FQHCs, MCOs, rural hospitals, and perinatal networks** as *organizations* — which is exactly why Hans raised **Definitive Healthcare** on Aug 21.

Options, cheapest first:
1. **UT Austin library / McCombs database access** — this was Hans's actual question. Check UT Libraries for Definitive Healthcare, IBISWorld, Mergent, or similar. Student access, if available, is free and is the highest-value single action Bhuvan can take this week.
2. **Free public directories** — HRSA FQHC/health-center data, CMS provider files, state DOH directories, First 5 county commission listings, MIECHV grantee lists. Covers organization discovery well; weak on named contacts.
3. **LinkedIn Sales Navigator** — strong on named contacts and title filtering; weak on firmographics and funding.
4. **Definitive Healthcare** — only if 1–3 leave a real gap.

### Tools still in the stack
- **HubSpot** — CRM, sequences, meeting links. System of record.
- **RHTP Hub Portal** — RHTP-specific verification.
- **Clay** — enrichment/orchestration. Access **unconfirmed** (`07`, O-2). Only worth it once there's list volume to enrich; not a day-one need.
- **LinkedIn** — person mapping and channel 3.
- **tl;dv** — call capture.

## 6. Targets and funnel math

**North-star target (set by Hans): 150 highly engaged calls per year** with decision-makers such as state DOH directors, child & family services executives, and foundation program officers. That is ~**3 per week**.

Working backwards with conservative assumptions `[to be replaced with real conversion data after 90 days]`:

| Stage | Conversion | Volume needed |
|---|---|---|
| Engaged calls / yr | — | **150** |
| Contacts engaged → call | ~15% (podcast-first) | ~1,000 contacts/yr ≈ **85/mo** |
| Named contacts per org | 3 | ~330 orgs/yr ≈ **28 orgs/mo** |
| A/B pass rate at scoring | ~40% | ~**70 orgs sourced/mo** |

**Weekly operating cadence**
- ~15–20 new organizations sourced and scored
- ~20 named contacts mapped
- ~20 first-touch outreaches (warm-path first)
- 3 engaged conversations held
- 1 pipeline review with Hans

**Leading indicators to watch** (these predict the lagging number): warm-intro rate, podcast acceptance rate, reply rate by segment, and time-from-source-to-first-touch.

## 7. Data schema (dashboard-ready)

Build the target table with these fields from day one so the live dashboard is a rendering job, not a rebuild.

**Organization**
`org_id · name · segment_code (OB/ABA/CBO/HR/FQHC/GOV/RHS/MCO/BRK/API/CW/K12) · state · county · type · population_served · staff_model (CHW/home-visiting/doula/none) · incumbent_platform · website`

**Opportunity**
`opp_id · org_id · source (civic_operator/rhtp_hub/grants_gov/inbound/referral) · funding_source · amount · status (signal/forthcoming/posted/awarded) · key_dates (post/close/award/budget) · avocado_role (prime/sub/unclear)`

**Scoring**
`s1_funding · s2_timing · s3_icp · s4_role · s5_path · s6_size · s7_whitespace · total_score · tier (A/B/C) · scored_date · rationale`

**Contact**
`contact_id · org_id · name · title · role (economic_buyer/champion/gatekeeper) · email · linkedin · warm_path_via · personalization_hook`

**Activity**
`stage (S0–S7) · owner · last_touch_date · channel · next_action · next_action_date · outcome · loss_reason`

## 8. First 30 days

**Week 1**
- Confirm Civic Operator capabilities against the §5 checklist; document gaps
- Check UT Austin library database access (Definitive Healthcare et al.)
- Resolve open questions O-1 through O-7 in `07` with Hans
- Stand up the target table per §7

**Week 2**
- Select 2–3 pilot states using the criteria in `03 §1`
- Source and score the first 50 organizations, weighted to CBO + OB (the combined workstream per `02 §6`)
- Draft the segment message set (`05`) and get Hans's sign-off

**Week 3**
- Map named contacts for the top 20 A/B orgs
- Audit warm paths: 1752vc network, advisors, HMHB/Hawaii references, clinical team networks, foundation contacts
- Begin podcast-first outreach to the top 10

**Week 4**
- First conversations held
- Review scoring model against real outcomes; recalibrate weights
- Ship v1 of the ranked target list to leadership and agree the dashboard spec
