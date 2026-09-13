# 03 — Funding & Buying Landscape

*Why now, where the money is, and how it actually moves. This is the doc that determines timing.*

---

## 1. Rural Health Transformation Program (RHTP) — the primary tailwind

**Scale:** A federal rural-health initiative distributing large multi-year allocations to states. Figures as briefed internally: on the order of **$1B**, with roughly **$200M per year per state over 5 years** for rural health advancement. `[Verify exact allocation mechanics and per-state amounts against the RHTP Hub Portal and CMS source before using any number externally.]`

**Why it matters to Avocado:** Almost entirely untapped by the company to date. The stated blockers were not fit — they were **bandwidth, lack of systematic prospect identification, and a missing contact database.** That is precisely the gap this project closes.

**How the money actually moves — the critical structural point:**

```
CMS / federal appropriation
        ↓
STATE receives allocation, writes a state RHT plan
        ↓
State DOH / designated agency administers subawards + RFPs
        ↓
LOCAL entities apply and win  ← ★ these are Avocado's customers
   (CBOs, FQHCs, county First 5s, rural hospitals,
    perinatal networks, health departments)
        ↓
Winning entity deploys a technology layer  ← ★ Avocado's slot
```

**Two distinct plays, run in parallel:**

| Play | Target | Objective | Horizon |
|---|---|---|---|
| **Upstream (state)** | State MCH Director, DOH Director, state RHT plan owners | Influence what the state plan funds; get known before RFPs are written | 12–24 mo, low hit rate, very high value |
| **Downstream (applicant)** | Likely prime applicants — CBOs, First 5s, FQHCs, perinatal networks | Be the technology partner inside their application | 3–9 mo, higher hit rate, this is where Hawaii came from |

**Prioritize downstream.** It converts faster, it matches the proven Hawaii pattern, and each win becomes upstream credibility.

**State selection criteria** (for choosing pilot states — open question O-7 in `07`):
1. Approved state RHT plan contains an explicit **maternal/child health** or **workforce** component
2. Existing warm relationship or advisor connection
3. Rural population share and Medicaid penetration
4. Timing — plan finalized but subaward RFPs not yet closed
5. Multilingual/equity need (strengthens the Avocado-specific argument)

**Portal:** RHTP Hub Portal (`rhtphub.com`) — company account exists; credentials held by Hans and on file with Bhuvan. ~$20/mo. Lists funded opportunities by state.

## 2. HR1 / Medicaid redetermination — the hard deadline

**Effective January 2027.** This is the single sharpest forcing function in the entire landscape because it has a date attached.

- Estimated **20–25% of the covered population is at risk of losing coverage** under redetermination requirements.
- FQHCs face a direct **revenue** threat: disenrolled patients are uncompensated patients.
- Avocado guides families through eligibility and redetermination **by text in ~10–15 minutes** (with Liife), versus a ~180-day process.

**Why this is the best cold-open in the deck:** it converts Avocado from a "nice-to-have engagement tool" into a **revenue-protection product** with a countdown. A CFO who ignores a parenting platform will not ignore Medicaid revenue leakage in Q1 2027.

**Sales implication:** every FQHC, MCO, and community health center conversation between now and Q4 2026 should lead with redetermination, not with parenting. Parenting is the second sentence.

## 3. Other funding channels

**Grants.gov** — Avocado has completed federal and statewide contractor/vendor registration (USFCR Verified Vendor, SAM). This unlocks **non-dilutive funding** and is an underused channel. Relevant program families: MIECHV, Healthy Start, HRSA maternal/child health, CMS SDOH and health-equity initiatives, state early-childhood dollars (Head Start / Early Head Start).

**NIH grant proposal** — in development as of July 2026; more detailed and nuanced than the public white paper. `[Status unknown — check with Hans.]`

**Foundation / philanthropic** — foundations are not buyers but are the pressure source. Program officers are asking grantees how they're using AI to scale impact. Avocado is a ready-made answer to that question, which is why the CBO segment closes on grant cycles.

## 4. Reimbursement pathways (the sustainability argument)

These matter because they change the buyer's math from "cost" to "revenue-neutral or better."

| Pathway | Mechanic | Relevant segments |
|---|---|---|
| **Care coordination CPT codes** | Care-coordination interactions become reimbursable — benchmark cited: ~**$45 per 15-minute** session (Blue Cross Blue Shield example) | CBO, OB, FQHC |
| **Remote Therapeutic Monitoring (RTM)** | Structured PGHD from text interactions supports billable RTM codes | FQHC, RHS, pediatric |
| **HCPCS pathway** | Potential reimbursement route flagged for FQHCs | FQHC |
| **HEDIS quality measures** | Drives revenue-relevant scores — well-child visits (WCV), vaccinations | FQHC, MCO |
| **MLR optimization** | Reduced avoidable utilization improves the payer's medical loss ratio | MCO |
| **Community benefit** | Nonprofit hospitals can fund from community-benefit obligation rather than operating budget | RHS |

**Use:** when a prospect says "we have no budget line for this," the answer is usually that there is an existing line it fits into — grant pass-through, community benefit, or a reimbursable service. Learn which line applies to which segment before the call.

## 5. Procurement realities (set expectations accordingly)

- **The Hawaii cycle was 12 months** first-contact-to-award. That is normal, not slow, for health/government contracts.
- Government cycles are **RFP-driven and budget-cycle dependent**. Missing a budget cycle costs a year.
- MCOs require **actuarial-grade ROI proof** before full-book rollout; expect security review then pilot-to-scale.
- FQHCs require EHR-integration and compliance review.
- Rural hospitals have **limited IT/security bandwidth** — a low-integration, SMS-only footprint is a genuine advantage here and should be stated explicitly.
- Avocado's **USFCR/SAM registration is a real qualifier** — many small vendors are disqualified on this alone. Mention it.

## 6. Competitive/market context

Avocado's chosen frame is the **infrastructure layer**, and the analogue set to study and emulate is:
- **Healthcare:** Unite Us, Findhelp (formerly Aunt Bertha), Innovaccer, Xealth
- **Non-healthcare:** Stripe, Shopify, Twilio

Detailed lessons in `06`. The relevant point here: infrastructure companies win procurement by being **recognized by decision-makers** even when invisible to end users. Every deployment must contribute to one common evidence base rather than fragmenting into unconnected local brands.

**Direct competitive substitutes parents currently use:** Google, Instagram/social, general-purpose chatbots (ChatGPT), and nothing. The site maintains explicit comparison pages against ChatGPT and traditional parent coaching.

**Adjacent startup activity:** Hans noted several startups working on patient onboarding and symptom collection. Avocado deliberately sits in an **adjacent layer** — around-the-clock parent support and parent-confidence measurement — rather than competing in intake/triage. Keep this distinction crisp; it is also the liability boundary (`01 §6`).
