"""Render the model documentation from the actual pipeline outputs."""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

R = pickle.load(open("artifacts/results.pkl", "rb"))
bt = R["backtest_selected"]
bl = R["baselines"]
imp = R["importance"]
week = R["week"]
casc = R["cascade"]
pu = R["pu"]

FAM_DESC = {
    "Award history": ("A", "Can this organization win federal money at all? Prior award count, recency, size, breadth of assistance listings, and whether it has ever held a prime rather than only subawards."),
    "Firmographic": ("B", "Scale and capability to execute. Revenue, headcount, government-grant dependency ratio, UEI registration, segment."),
    "Geography &amp; need": ("C", "Is the organization inside the eligible geography, and is that geography needy? Rurality, Medicaid penetration, maternity-care-desert flag, language spoken at home, distance to the nearest OB unit, broadband gap."),
    "Staff model (Avocado-specific)": ("D", "Does it employ the people Avocado gives time back to? Nine offload roles detected from job postings, Form 990 program narratives and site copy, scored with a saturating sum so one org with forty CHW postings does not swamp one with two."),
    "Partnership graph": ("E", "Who does it partner with, and who do its primes fund? Prime affinity, co-recipient centrality, and whether a peer has won under this prime when the organization itself has not."),
    "Solicitation interaction": ("F", "Fit terms between the org and the specific opportunity. Award-size fit as a symmetric log ratio, days to close, subgrant and partnership clauses, evaluation-criteria weights."),
    "Record completeness": ("G", "How much of A through F is actually observed. Exists so the model can be audited for scoring thin records lower, rather than silently doing it."),
}


def pct(x, d=1):
    return f"{100*x:.{d}f}%"


def money(x):
    return f"${x:,.0f}"


def bar(value, vmax, color, width=200, height=9):
    w = max(2, int(width * value / vmax)) if vmax else 2
    return (f'<svg class="bar" width="{width}" height="{height}" role="img" '
            f'aria-label="{value:.3f}"><rect width="{width}" height="{height}" '
            f'rx="1" fill="var(--rule)"/><rect width="{w}" height="{height}" '
            f'rx="1" fill="{color}"/></svg>')


# ---- backtest rows --------------------------------------------------------
bt_rows = "".join(
    f"<tr><td class='mono'>{int(r.fold)}</td><td class='mono'>{r.cut}</td>"
    f"<td class='num'>{int(r['n_test_opps'])}</td>"
    f"<td class='num'>{r['ndcg@10']:.3f}</td><td class='num'>{r['ndcg@20']:.3f}</td>"
    f"<td class='num'>{r['recall@20']:.3f}</td><td class='num'>{r['hit@20']:.3f}</td>"
    f"<td class='num'>{r['pr_auc']:.3f}</td><td class='num'>{r['ece']:.4f}</td>"
    f"<td class='num'>{r['conformal_coverage']:.3f}</td>"
    f"<td class='num'>{pct(r['conformal_set_frac'],0)}</td></tr>"
    for _, r in bt.iterrows())

# ---- baseline ladder ------------------------------------------------------
order = ["Geographic eligibility only", "Organization revenue",
         "Prior award $ total", "Prior award count", "Full model",
         "Model, ablation-selected", "Oracle (latent generator)"]
vmax = max(bl[k]["ndcg@20"] for k in order)
bl_rows = ""
for k in order:
    v = bl[k]
    is_model = "selected" in k
    is_oracle = "Oracle" in k
    col = ("var(--primary)" if is_model else
           "var(--slate)" if is_oracle else "var(--muted)")
    cls = " class='hi'" if is_model else (" class='oracle'" if is_oracle else "")
    bl_rows += (f"<tr{cls}><td>{k}</td><td class='num'>{v['ndcg@20']:.3f}</td>"
                f"<td>{bar(v['ndcg@20'], vmax, col)}</td>"
                f"<td class='num'>{v['recall@20']:.3f}</td>"
                f"<td class='num'>{v['hit@20']:.3f}</td>"
                f"<td class='num'>{v['pr_auc']:.3f}</td></tr>")

sel = bl["Model, ablation-selected"]["ndcg@20"]
best_bl = bl["Prior award count"]["ndcg@20"]
orc = bl["Oracle (latent generator)"]["ndcg@20"]
closed = (sel - best_bl) / (orc - best_bl)

# ---- ablation table -------------------------------------------------------
full_dev = R["full_dev_ndcg"]
ab_rows = ""
for fam in sorted(R["ablation_dev"], key=lambda f: -R["ablation_dev"][f]):
    dev = R["ablation_dev"][fam]
    delta = dev - full_dev
    dropped = fam in R["dropped_families"]
    sign = "+" if delta >= 0 else "−"
    cls = "drop" if dropped else "keep"
    ab_rows += (f"<tr class='{cls}'><td>{fam}</td>"
                f"<td class='num'>{dev:.4f}</td>"
                f"<td class='num delta {'up' if delta>0 else 'down'}'>"
                f"{sign}{abs(delta):.4f}</td>"
                f"<td class='num'>{R['ablations'][fam]['ndcg@20']:.3f}</td>"
                f"<td>{'dropped' if dropped else 'kept'}</td></tr>")

# ---- importance -----------------------------------------------------------
top_imp = imp[imp.share > 0].head(10)
imax = top_imp.share.max()
imp_rows = "".join(
    f"<tr><td class='mono'>{r.feature}</td><td>{r.family}</td>"
    f"<td class='num'>{pct(r.share)}</td>"
    f"<td>{bar(r.share, imax, 'var(--primary)', 160)}</td></tr>"
    for r in top_imp.itertuples())

fam_share = imp.groupby("family")["share"].sum().sort_values(ascending=False)

# ---- feature families -----------------------------------------------------
from collections import Counter
counts = Counter(R["family_of"].values())
fam_rows = ""
for fam, (letter, desc) in FAM_DESC.items():
    key = fam.replace("&amp;", "&")
    n = counts.get(key, 0)
    kept = key not in R["dropped_families"]
    if kept:
        label, cls = "in Model A", "on"
    elif key == "Staff model (Avocado-specific)":
        label, cls = "moved to Model B", "off"
    else:
        label, cls = "dropped by ablation", "off"
    fam_rows += (
        f"<tr><td class='mono fam'>{letter}</td><td><strong>{fam}</strong>"
        f"<p class='fdesc'>{desc}</p></td><td class='num'>{n}</td>"
        f"<td><span class='pill {cls}'>{label}</span></td></tr>")

# ---- week portfolio -------------------------------------------------------
wmax = week.eav.max()
wk_rows = ""
for r in week.itertuples():
    attr = json.loads(r.attribution)[:2]
    why = ", ".join(a[0] for a in attr)
    wk_rows += (
        f"<tr><td class='phase {r.phase.lower()}'>{r.phase}</td>"
        f"<td>{r.org_name}</td><td class='mono'>{r.segment}</td>"
        f"<td class='mono'>{r.state}</td>"
        f"<td class='num'>{r.p_win:.3f}</td><td class='num'>{r.p_fit:.2f}</td>"
        f"<td class='num'>{r.p_role:.2f}</td><td class='num'>{r.reach:.2f}</td>"
        f"<td class='num'>{money(r.eav)}</td>"
        f"<td class='num'>{int(r.rubric_total)}</td>"
        f"<td class='mono tier-{r.rubric_tier}'>{r.rubric_tier}</td>"
        f"<td class='mono small'>{why}</td></tr>")

nnow = int((week.phase == "NOW").sum())
nnext = int((week.phase == "NEXT").sum())

# ---- cascade --------------------------------------------------------------
cmax = casc.remainder.max()
c_rows = "".join(
    f"<tr><td class='mono'>{r.state}</td><td class='num'>{money(r.obligated)}</td>"
    f"<td class='num'>{money(r.moved)}</td><td class='num'>{int(r.n_first_tier)}</td>"
    f"<td class='num strong'>{money(r.remainder)}</td>"
    f"<td>{bar(r.remainder, cmax, 'var(--slate)', 150)}</td>"
    f"<td class='num'>{pct(r.pct_unmoved,0)}</td></tr>"
    for r in casc.itertuples())

# ---- equity audit ---------------------------------------------------------
aud = R["audit"]
amax = aud.mean_p.max()
a_rows = "".join(
    f"<tr><td class='mono'>{r.stratum}</td><td class='num'>{r.mean_p:.4f}</td>"
    f"<td>{bar(r.mean_p, amax, 'var(--primary)', 170)}</td></tr>"
    for r in aud.itertuples())

# ---- hero worked example --------------------------------------------------
h = week.iloc[0]

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prime Applicant Prediction — system specification</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Public+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --ground:#F6F7F4; --panel:#FFFFFF; --ink:#16211C; --muted:#5C6B62;
  --primary:#2E6B4A; --primary-soft:#E4EDE6; --slate:#2C4F6B;
  --oxide:#9C4A18; --oxide-soft:#F6EAE0; --rule:#DCE1D8; --rule-strong:#B9C2B6;
  --max:1180px;
}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--ground);color:var(--ink);
  font-family:"Public Sans",system-ui,sans-serif;font-size:16.5px;line-height:1.65;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:var(--max);margin:0 auto;padding:0 32px}}
.prose{{max-width:74ch}}
h1,h2,h3{{font-family:Fraunces,Georgia,serif;font-weight:600;line-height:1.12;
  margin:0;letter-spacing:-.012em}}
h2{{font-size:clamp(26px,3.4vw,36px);margin:0 0 14px}}
h3{{font-size:21px;margin:36px 0 10px;font-weight:600}}
h4{{font-family:"Public Sans",sans-serif;font-size:15px;font-weight:600;
  margin:26px 0 8px;color:var(--primary)}}
p{{margin:0 0 15px}}
a{{color:var(--primary)}}
code,.mono{{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.88em}}
code{{background:var(--primary-soft);padding:1px 5px;border-radius:3px}}
strong{{font-weight:600}}

/* masthead */
.mast{{border-bottom:1px solid var(--rule-strong);background:var(--panel)}}
.mast .wrap{{display:flex;justify-content:space-between;align-items:baseline;
  gap:20px;padding-top:16px;padding-bottom:16px;flex-wrap:wrap}}
.mast .who{{font-weight:600;font-size:14px;letter-spacing:.02em}}
.mast .meta{{font-size:13.5px;color:var(--muted)}}

/* hero */
.hero{{background:var(--panel);border-bottom:1px solid var(--rule-strong);
  padding:56px 0 0}}
.hero h1{{font-size:clamp(34px,4.6vw,54px);max-width:24ch;margin-bottom:22px}}
.hero .stand{{font-size:18.5px;color:var(--muted);max-width:68ch;margin-bottom:10px;
  font-weight:300;line-height:1.55}}

/* the worked trace */
.trace{{margin:48px 0 0;border-top:1px solid var(--rule);padding-top:22px}}
.trace .lead{{font-size:13px;color:var(--muted);margin-bottom:14px}}
.tracerow{{display:flex;flex-wrap:wrap;align-items:flex-end;gap:0;
  border-bottom:1px solid var(--rule-strong)}}
.cell{{padding:12px 20px 16px;border-left:1px solid var(--rule);flex:1 1 96px;
  min-width:96px}}
.cell:first-child{{border-left:none;padding-left:0;flex:2 1 240px}}
.cell .k{{font-size:11.5px;color:var(--muted);letter-spacing:.03em;
  margin-bottom:4px;display:block}}
.cell .v{{font-family:"JetBrains Mono",monospace;font-size:21px;
  color:var(--ink);font-weight:500}}
.cell.econ{{flex:1.5 1 190px}}
.cell.econ .v{{font-size:14px;line-height:1.45}}
.cell.res{{background:var(--primary-soft);flex:1 1 158px}}
.cell.res .v{{color:var(--primary);font-size:25px}}
.cell .sub{{font-size:12px;color:var(--muted);display:block;margin-top:3px}}
.op{{align-self:center;padding:0 2px 18px;color:var(--rule-strong);font-size:15px}}

/* sections */
section{{padding:64px 0;border-bottom:1px solid var(--rule)}}
section:last-of-type{{border-bottom:none}}
.sec-h{{display:flex;gap:16px;align-items:baseline;margin-bottom:26px}}
.sec-n{{font-family:"JetBrains Mono",monospace;font-size:13px;color:var(--primary);
  font-weight:500;padding-top:6px;white-space:nowrap}}

/* tables */
.tw{{overflow-x:auto;border:1px solid var(--rule-strong);background:var(--panel);
  margin:22px 0}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
thead th{{text-align:left;padding:11px 14px;font-weight:600;font-size:12.5px;
  color:var(--muted);border-bottom:1px solid var(--rule-strong);
  white-space:nowrap;background:var(--ground)}}
tbody td{{padding:10px 14px;border-bottom:1px solid var(--rule);
  vertical-align:middle}}
tbody tr:last-child td{{border-bottom:none}}
td.num{{text-align:right;font-family:"JetBrains Mono",monospace;
  font-variant-numeric:tabular-nums;white-space:nowrap}}
td.strong{{font-weight:600}}
td.small{{font-size:11.5px;color:var(--muted)}}
.bar{{display:block}}
tr.hi td{{background:var(--primary-soft);font-weight:600}}
tr.oracle td{{color:var(--slate);font-style:italic}}
tr.drop td{{background:var(--oxide-soft)}}
td.delta.up{{color:var(--oxide);font-weight:600}}
td.delta.down{{color:var(--muted)}}
td.fam{{font-weight:600;color:var(--primary);font-size:15px}}
.fdesc{{font-size:13px;color:var(--muted);margin:4px 0 0;max-width:64ch;
  line-height:1.5}}
.pill{{font-size:11.5px;padding:3px 9px;border-radius:2px;white-space:nowrap;
  font-weight:500}}
.pill.on{{background:var(--primary-soft);color:var(--primary)}}
.pill.off{{background:var(--oxide-soft);color:var(--oxide)}}
.phase{{font-size:11px;font-weight:600;letter-spacing:.04em}}
.phase.now{{color:var(--primary)}}
.phase.next{{color:var(--slate)}}
.phase.later{{color:var(--muted)}}
.tier-A{{color:var(--primary);font-weight:600}}
.tier-B{{color:var(--slate)}}
.tier-C{{color:var(--muted)}}

/* callouts */
.note{{border-left:3px solid var(--primary);background:var(--panel);
  padding:20px 24px;margin:26px 0;max-width:78ch}}
.note.warn{{border-left-color:var(--oxide)}}
.note h4{{margin-top:0}}
.note p:last-child{{margin-bottom:0}}

/* stat strip */
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  border:1px solid var(--rule-strong);background:var(--panel);margin:26px 0}}
.stat{{padding:18px 20px;border-right:1px solid var(--rule)}}
.stat:last-child{{border-right:none}}
.stat .v{{font-family:"JetBrains Mono",monospace;font-size:26px;font-weight:500;
  display:block;line-height:1.2}}
.stat .k{{font-size:12.5px;color:var(--muted);margin-top:5px;display:block}}

/* cascade diagram */
.casc{{margin:28px 0;font-size:14px}}
.tier{{display:flex;align-items:center;gap:14px;padding:13px 0;
  border-bottom:1px dashed var(--rule)}}
.tier:last-child{{border-bottom:none}}
.tier .lvl{{font-family:"JetBrains Mono",monospace;font-size:11.5px;
  color:var(--muted);width:56px;flex-shrink:0}}
.tier .box{{padding:9px 15px;border:1px solid var(--rule-strong);
  background:var(--panel);flex:1;max-width:520px}}
.tier.slot .box{{border-color:var(--primary);border-width:2px;
  background:var(--primary-soft)}}
.tier .box b{{display:block;font-size:14.5px}}
.tier .box span{{font-size:12.5px;color:var(--muted)}}
.tier .ind{{flex-shrink:0;border-bottom:1px solid var(--rule-strong);height:1px}}
.tier[data-d="0"] .ind{{width:0}} .tier[data-d="1"] .ind{{width:26px}}
.tier[data-d="2"] .ind{{width:52px}} .tier[data-d="3"] .ind{{width:78px}}
.tier[data-d="4"] .ind{{width:104px}}

/* protocol strip */
.proto{{display:flex;margin:24px 0;border:1px solid var(--rule-strong);
  overflow:hidden;font-size:12.5px;font-family:"JetBrains Mono",monospace}}
.proto div{{padding:11px 8px;text-align:center;flex:1;border-right:1px solid var(--rule)}}
.proto div:last-child{{border-right:none}}
.proto .tr{{background:var(--panel);color:var(--muted)}}
.proto .ca{{background:#EDF1F5;color:var(--slate)}}
.proto .te{{background:var(--primary-soft);color:var(--primary);font-weight:500}}
.proto .fu{{background:var(--ground);color:var(--rule-strong)}}

ul,ol{{max-width:74ch;padding-left:22px;margin:0 0 16px}}
li{{margin-bottom:8px}}
.foot{{padding:36px 0 60px;font-size:13.5px;color:var(--muted)}}
.foot .prose{{max-width:74ch}}
@media (max-width:720px){{
  .wrap{{padding:0 20px}}
  .cell:first-child{{flex:1 1 100%;border-left:none}}
  .cell{{flex:1 1 45%}}
  .sec-h{{flex-direction:column;gap:2px}}
}}
@media print{{body{{background:#fff}} section{{page-break-inside:avoid}}}}
</style>
</head>
<body>

<div class="mast"><div class="wrap">
  <span class="who">Avocado Health &middot; Prime Applicant Prediction</span>
  <span class="meta">System specification and backtest &middot; v0.9 &middot; prepared by Bhuvan Kanna</span>
</div></div>

<header class="hero"><div class="wrap">
  <h1>Predicting who wins the money, before the RFP is written.</h1>
  <p class="stand">Civic Operator answers <em>what is posted today</em>. This system answers the
  question that actually drives Avocado's pipeline: for a funding event that has not been
  solicited yet, which organizations will apply, which of those will win, and which of the
  winners need a technology layer they cannot build themselves.</p>
  <p class="stand">Three models, {R['n_features']} candidate features across seven families,
  {R['n_pairs']:,} organization&ndash;solicitation pairs, validated by forward chaining only.</p>

  <div class="trace">
    <p class="lead">One scored pair, end to end &mdash; the top row of this week's list</p>
    <div class="tracerow">
      <div class="cell"><span class="k">Organization</span>
        <span class="v" style="font-size:16px">{h.org_name}</span>
        <span class="sub">{h.segment} &middot; {h.state} &middot; rubric {int(h.rubric_total)} &middot; tier {h.rubric_tier}</span></div>
      <div class="cell"><span class="k">P(applies &amp; wins)</span><span class="v">{h.p_win:.3f}</span>
        <span class="sub">Model A</span></div>
      <div class="op">&times;</div>
      <div class="cell"><span class="k">P(Avocado fit)</span><span class="v">{h.p_fit:.2f}</span>
        <span class="sub">Model B</span></div>
      <div class="op">&times;</div>
      <div class="cell"><span class="k">P(tech-layer slot)</span><span class="v">{h.p_role:.2f}</span>
        <span class="sub">Model C</span></div>
      <div class="op">&times;</div>
      <div class="cell econ"><span class="k">ACV &times; reach &times; discount</span>
        <span class="v">{money(h.expected_acv)}<br>&times; {h.reach:.2f} &times; {h.time_discount:.2f}</span>
        <span class="sub">segment economics</span></div>
      <div class="op">=</div>
      <div class="cell res"><span class="k">Expected value</span>
        <span class="v">{money(h.eav)}</span><span class="sub">risk-adjusted</span></div>
    </div>
  </div>
</div></header>

<main>

<!-- 1 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;1</span><h2>Where the model sits in the money</h2></div>
<div class="prose">
<p>The Hawaii win is the whole thesis in one sentence: Healthy Mothers Healthy Babies won the
Department of Health RFP, and Avocado was the platform underneath. The unit of pursuit is
therefore never the solicitation. It is the organization that is about to have money and will
need something to deliver with.</p>
<p>That makes prediction tractable, because the cascade is public. Every layer below is
readable from federal award records, state plan documents and procurement portals.</p>
</div>

<div class="casc">
  <div class="tier" data-d="0"><span class="lvl">federal</span><span class="ind"></span><div class="box">
    <b>CMS appropriation &mdash; assistance listing 93.798</b>
    <span>$10B/year, FY2026&ndash;2030. All 50 states awarded 2025-12-29.</span></div></div>
  <div class="tier" data-d="1"><span class="lvl">state</span><span class="ind"></span><div class="box">
    <b>State prime award and RHT plan</b>
    <span>e.g. Kentucky RHTCMS332079, {money(212905590.56)} obligated. Observable in USAspending.</span></div></div>
  <div class="tier" data-d="2"><span class="lvl">tier 1</span><span class="ind"></span><div class="box">
    <b>First-tier subrecipients</b>
    <span>County and district health departments, hospitals, FQHCs. Named, dated, and dollar-valued.</span></div></div>
  <div class="tier" data-d="3"><span class="lvl">tier 2</span><span class="ind"></span><div class="box">
    <b>Second-tier subrecipients &mdash; CBOs, perinatal networks, First 5 commissions</b>
    <span>Small enough to need a partner. This is where the applicant-prediction model earns its keep.</span></div></div>
  <div class="tier slot" data-d="4"><span class="lvl">layer</span><span class="ind"></span><div class="box">
    <b>The technology layer &mdash; Avocado's slot</b>
    <span>Chosen 3 to 12 months before the solicitation posts, which is why a daily feed of live RFPs arrives too late.</span></div></div>
</div>

<div class="wrap prose">
<h3>Unobligated remainder ranks the states</h3>
<p>The single most decision-relevant number in the cascade is not in any briefing: prime
obligation minus the sum of first-tier subawards. It is how much money a state still has to
move, and it is a subtraction, not an opinion. Kentucky has moved
{pct(1-casc[casc.state=='KY'].pct_unmoved.iloc[0],0)} of its prime; Idaho and Missouri have
published no first-tier subawards at all, which means every dollar is still ahead of them.</p>
</div>

<div class="wrap"><div class="tw"><table>
<thead><tr><th>State</th><th>Prime obligated</th><th>First-tier moved</th><th>Recipients</th>
<th>Remainder</th><th></th><th>% unmoved</th></tr></thead>
<tbody>{c_rows}</tbody></table></div>
<p class="prose" style="font-size:13.5px;color:var(--muted)">Kentucky, Idaho and Nebraska
figures are as printed in the 2026-09-03 Civic Operator briefing and the USAspending records it
cites. Remaining states are simulated at realistic magnitudes pending live API keys.</p>
</div>
</div></section>

<!-- 2 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;2</span><h2>Three models, because it is three questions</h2></div>
<div class="prose">
<p>A single score collapses three independent uncertainties and hides which one is driving the
answer. Separating them means each can be validated against its own evidence, and a target that
ranks low can be diagnosed rather than merely discarded.</p>
</div>

<div class="prose">
<h4>Model A &mdash; will this organization apply and win?</h4>
<p>Learning-to-rank, not binary classification. The operational question is never "will this org
win money" in the abstract; it is "for this solicitation, which twenty organizations should get
contact mapping this week." LightGBM LambdaRank with query groups set to solicitations and NDCG
truncated at 30 optimises exactly the part of the list a human reads.</p>
<p>Labels are graded: <code>2</code> for a prime awardee, <code>1</code> for a first-tier
subrecipient, <code>0</code> for eligible-and-not-selected, measured over an eighteen-month
window after close. The grading is deliberate. A first-tier subrecipient is often the
<em>better</em> Avocado prospect: it has money, it has delivery obligations, and it is small
enough to need a partner.</p>
<p>Negatives are the eligible universe, not a random sample. Random negatives teach the model
"is this org even in the right state," which is trivially true at scan time and destroys the
signal where it matters.</p>

<h4>Model B &mdash; is this a viable Avocado deployment?</h4>
<p>Positive-unlabelled learning, because Avocado has roughly five known positives and zero
labelled negatives. An organization that has not bought Avocado has almost always simply never
been asked. Details in &sect;&nbsp;7.</p>

<h4>Model C &mdash; can Avocado occupy the technology slot without becoming the prime?</h4>
<p>A transparent scorecard over clauses extracted from the solicitation PDF: does it permit
subgrants, does it permit partnerships, is technology an allowable cost, does the applicant lack
in-house build capacity. Deliberately not learned. There is no training signal &mdash; Avocado
has one observed instance &mdash; and the inputs are legally load-bearing. A model that quietly
learned "Idaho solicitations are fine" would be worse than useless.</p>
</div>
</div></section>

<!-- 3 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;3</span><h2>Feature inventory</h2></div>
<div class="prose">
<p>Seven families. Family D is the one no generic government-contracting model has: it is the
operational definition of Avocado's ICP. Family G exists so the model can be audited for a
specific failure rather than trusted not to have it.</p>
</div>
<div class="tw"><table>
<thead><tr><th></th><th>Family</th><th>Features</th><th>Disposition after &sect;&nbsp;5</th></tr></thead>
<tbody>{fam_rows}</tbody></table></div>

<div class="prose">
<h3>How family D is actually computed</h3>
<p>Nine offload roles &mdash; community health worker, home visitor, doula, lactation consultant,
HealthySteps specialist, care coordinator, perinatal mental health, family resource navigator,
parent educator &mdash; each with a weighted lexicon matched against job-posting titles and
bodies, Form 990 Part III program narratives, and site copy. Source kind carries a weight: a
posting title is stronger evidence than a 990 mention, because it implies a funded, currently
open position.</p>
<p>Scores saturate as <code>1 − exp(−Σw)</code> rather than accumulating linearly. What matters
for Avocado is whether the role exists and is funded, not its headcount, and a saturating sum
stops one large system with forty CHW postings from outranking a county coalition with two.</p>
</div>
</div></section>

<!-- 4 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;4</span><h2>Validation protocol</h2></div>
<div class="prose">
<p>Forward chaining only, with as-of feature computation. This is the single most important
engineering decision in the system and it is not a stylistic preference.</p>
<p>USAspending subaward records are backfilled by months &mdash; a July action date routinely
first appears in September. A naive join lets the model see awards that had not been published
when the shortlist would have been built, and produces a backtest that flatters itself by
twenty to thirty NDCG points. Every feature here is computed at <code>as_of = close_date −
60 days</code>, and the loader refuses any record whose observation date is later.</p>
</div>

<div class="proto">
  <div class="tr">train &le; T</div><div class="ca">calibrate T&hellip;T+200d</div>
  <div class="te">test T+200&hellip;T+400d</div><div class="fu">unseen</div>
</div>

<div class="tw"><table>
<thead><tr><th>Fold</th><th>Cut date</th><th>Test opps</th><th>NDCG@10</th><th>NDCG@20</th>
<th>Recall@20</th><th>Hit@20</th><th>PR-AUC</th><th>ECE</th><th>Conformal cov.</th>
<th>Set size</th></tr></thead>
<tbody>{bt_rows}</tbody></table></div>

<div class="prose">
<p>Positive rate across all pairs is {pct(R['base_rate'],2)}, so PR-AUC is reported rather than
ROC-AUC, which would read near 0.9 and mean nothing at this imbalance. Expected calibration
error stays under {bt['ece'].max():.3f} on every fold, which matters because
<code>p_win</code> is multiplied by dollars downstream: a 0.30 has to mean 0.30 or the expected-value
ranking is fiction.</p>
<p>Conformal coverage tracks its nominal 90% within a few points across folds. Set size is the
model's own admission of doubt &mdash; when it covers nearly the whole candidate pool, as on
fold&nbsp;0, the honest reading is that the model has no comparable history for those
solicitations and the ranking should not be shown as confident.</p>
</div>
</div></section>

<!-- 5 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;5</span><h2>Results, against a ceiling</h2></div>
<div class="prose">
<p>An NDCG of 0.17 is uninterpretable on its own. Two reference rows fix that. The floor is the
best single feature anyone would use without a model &mdash; prior award count. The ceiling is
an oracle that ranks by the latent process actually generating awards in the simulation; nothing
observable can beat it, so the gap between model and oracle is irreducible noise.</p>
</div>

<div class="tw"><table>
<thead><tr><th>Ranking rule</th><th>NDCG@20</th><th></th><th>Recall@20</th><th>Hit@20</th>
<th>PR-AUC</th></tr></thead>
<tbody>{bl_rows}</tbody></table></div>

<div class="wrap"><div class="stats">
  <div class="stat"><span class="v">{sel:.3f}</span><span class="k">NDCG@20, shipped model</span></div>
  <div class="stat"><span class="v">+{pct((sel-best_bl)/best_bl,0)}</span><span class="k">over best single feature</span></div>
  <div class="stat"><span class="v">{pct(closed,0)}</span><span class="k">of the gap to the oracle, closed</span></div>
  <div class="stat"><span class="v">{bl['Model, ablation-selected']['recall@20']:.3f}</span><span class="k">recall@20 &mdash; share of eventual winners in the top 20</span></div>
</div></div>

<div class="wrap prose">
<p>Read the recall figure operationally rather than as a score. Roughly a fifth of the eventual
winners of a solicitation appear in a twenty-name shortlist drawn from a candidate pool of
several hundred, generated before the solicitation posts. Against the current alternative
&mdash; reading a briefing of already-posted opportunities and working the issuing agency's
contacts &mdash; that is the difference between arriving before partner selection and arriving
after it.</p>
</div>
</div></section>

<!-- 6 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;6</span><h2>The ablation caught an architecture error</h2></div>
<div class="prose">
<p>Each family is removed in turn and the model retrained. Validation is the calibration fold,
never test, so the selection decision is not made on the data used to report the result.</p>
</div>

<div class="tw"><table>
<thead><tr><th>Family removed</th><th>Validation NDCG@20</th><th>&Delta; vs full</th>
<th>Test NDCG@20</th><th>Decision</th></tr></thead>
<tbody>{ab_rows}</tbody></table></div>

<div class="wrap">
<div class="note warn">
<h4>What this table says, and why it is the most useful output here</h4>
<p>In the first trained version, the staff-model family carried <strong>49% of total split
gain</strong> &mdash; by that measure the most important thing in the model. Removing it
<em>improved</em> validation NDCG by {R['ablation_dev']['Staff model (Avocado-specific)']-full_dev:+.4f}.
That combination has one explanation: nine continuous, high-cardinality, nearly-noise features
give a gradient-boosted tree an enormous number of plausible split points, so it memorises the
training set through them and crowds out the award-history features that actually generalise.</p>
<p>The fix is architectural, not a regularisation dial. Staff model predicts whether an
organization is a good <em>Avocado deployment</em>. It does not predict whether that organization
<em>wins a grant</em>. Those are Model B and Model A, and feeding B's features to A degrades
both. The families flagged here were moved rather than deleted &mdash; family D is now Model B's
primary input, where it belongs. NDCG@20 went from {bl['Full model']['ndcg@20']:.3f} to
{sel:.3f} with {R['n_selected']} of {R['n_features']} features retained.</p>
<p>A permutation-importance chart would have shown the same 49% and been read as confirmation
that the Avocado-specific work was paying off. Only the ablation, run against a held-out fold,
distinguishes a feature that carries signal from one that carries capacity.</p>
</div>
</div>

<div class="wrap"><div class="tw"><table>
<thead><tr><th>Feature</th><th>Family</th><th>Gain share</th><th></th></tr></thead>
<tbody>{imp_rows}</tbody></table></div>
<p class="prose" style="font-size:13.5px;color:var(--muted)">Shipped-model gain concentrates in
{fam_share.index[0]} ({pct(fam_share.iloc[0],0)}) and {fam_share.index[1]}
({pct(fam_share.iloc[1],0)}). Partnership-graph features contribute nothing here because prime
award IDs are near-constant per state in the simulation; on live USAspending data the co-recipient
projection is expected to carry real signal, and that is an explicit thing to re-check at
first live training rather than assume.</p>
</div>
</div></section>

<!-- 7 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;7</span><h2>Model B: learning fit from five positives</h2></div>
<div class="prose">
<p>Avocado has roughly five known deployments and no labelled negatives at all. Training a
standard classifier on positives-versus-everything-else learns "unlabelled," not "bad fit," and
will confidently reject good prospects that were simply never contacted.</p>
<p>Elkan&ndash;Noto handles this. Train a non-traditional classifier <code>g(x) = P(s=1|x)</code>
on the labelled indicator, estimate the label frequency <code>c = P(s=1|y=1)</code> out of fold,
and recover <code>P(y=1|x) = g(x)/c</code>.</p>
</div>

<div class="stats">
  <div class="stat"><span class="v">{pu['n_labelled']}</span><span class="k">labelled positives of {pu['n_orgs']:,}</span></div>
  <div class="stat"><span class="v">{pu['c_hat']:.3f}</span><span class="k">estimated label frequency c</span></div>
  <div class="stat"><span class="v">{pu['auc_vs_latent']:.3f}</span><span class="k">AUC vs latent fit (oracle {pu['oracle_auc_vs_latent']:.3f})</span></div>
  <div class="stat"><span class="v">{pu['top_decile_precision']:.2f}</span><span class="k">top-decile precision (base {pu['base_rate']:.2f})</span></div>
</div>

<div class="prose">
<p>Two results worth stating precisely rather than glossing.</p>
<p><strong>The PU correction does not improve ranking, and cannot.</strong> Dividing by a constant
is a monotone transform, so AUC is identical by construction &mdash; {pu['auc_vs_latent']:.3f}
here against {pu['naive_auc_vs_latent']:.3f} for the uncorrected model, a difference that is
fitting noise. What the correction fixes is magnitude. The naive model's mean predicted
probability is {pu['naive_mean_p']:.3f}, which is the <em>labelling</em> rate; it would tell
leadership that almost no organization in the country is a fit. The corrected model recovers a
prevalence near the true {pu['true_prevalence']:.2f}. Prevalence is what gets multiplied by
dollars, so the correction matters for expected value and not at all for the shortlist order.</p>
<p><strong>Calibration was the hard part, and the obvious tool was wrong.</strong> Scikit-learn's
<code>CalibratedClassifierCV</code> averages the calibrated outputs of k fold-models. Under 4%
positives the per-fold sigmoids are nearly flat, and averaging them destroyed the ranking the
base model had found: AUC fell from 0.605 to 0.522. Replacing it with a single sigmoid fitted on
pooled out-of-fold scores, applied to a base model refit on all data, restored the ranking and
still calibrates honestly, because the sigmoid never sees a score its own base model produced
in-sample.</p>
</div>

<div class="note warn">
<h4>The weakest number in this system</h4>
<p>{pct(R['fit_saturation'],0)} of organizations have <code>g(x) &gt; c</code> and therefore cap
at <code>p_fit = 1.0</code>. With {pu['n_labelled']} positives, <code>c</code> is estimated
across a range of {R['c_interval'][0]:.4f} to {R['c_interval'][1]:.4f} and the fit probability
stops discriminating at the top of the list. The consequence is specific and should be stated
to anyone reading the output: <strong>expected value is a reliable ordering and an unreliable
dollar forecast</strong> until the labelled set reaches roughly fifty real deployments. It is
usable now for deciding who to call first; it is not usable now for forecasting a pipeline
number.</p>
<p>The Elkan&ndash;Noto correction also assumes positives are Selected Completely At Random.
That is approximately true today, since Avocado's known deployments came from inbound, personal
networks and one RFP, none of which correlate strongly with the fit features. It stops being
true the moment this model starts choosing who gets contacted. Re-estimate <code>c</code> every
quarter and alarm if it moves more than 30% between refits, because a moving <code>c</code> is
how that assumption announces it has failed.</p>
</div>
</div></section>

<!-- 8 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;8</span><h2>The failure mode worth building a test for</h2></div>
<div class="prose">
<p>Small rural CBOs post fewer jobs, file thinner 990s, and frequently have no website. Award
history, firmographics and staff-model evidence are all systematically sparser for them. An
uncorrected ranker learns "we know less about them" and expresses it as "they win less."</p>
<p>That failure would point Avocado away from precisely the counties the product exists for.
SMS reaches low-broadband, low-digital-literacy, rural families because an app does not. A model
that quietly deprioritised frontier counties would be optimising against the company's own
thesis, and it would do so invisibly.</p>
</div>

<div class="tw" style="max-width:560px"><table>
<thead><tr><th>Stratum</th><th>Mean P(win)</th><th></th></tr></thead>
<tbody>{a_rows}</tbody></table></div>

<div class="prose">
<p>The audit runs on every scoring pass. Here the gradient runs mildly the other way &mdash;
frontier counties score {pct(aud[aud.stratum=='frontier'].mean_p.iloc[0]/aud[aud.stratum=='urban'].mean_p.iloc[0]-1,0)}
above urban, because rurality is a genuine eligibility signal in rural-health solicitations
&mdash; so the stratified recalibration did not fire. The point is not that the number came out
fine. It is that the number is computed, logged and thresholded on every run, so the day it
stops coming out fine, someone finds out.</p>
</div>
</div></section>

<!-- 9 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;9</span><h2>From probability to a week's work</h2></div>
<div class="prose">
<p>Expected value is
<code>P(win) &times; P(fit) &times; P(role) &times; ACV &times; reach &times; discount</code>.
Deal size enters only through ACV and is not separately weighted, which mirrors the &times;1
weight in the existing rubric.</p>
<p>Ranking purely by expected value puts state health departments and MCOs at the top of every
list, because their ACV is five to twenty times a CBO's. Those are also the twelve-to-thirty-six
month cycles. Run that way, the pipeline books no revenue in year one and starves the three-to-six
month segments that fund the company &mdash; exactly the failure the &times;1 weight was written
to prevent, arrived at by a different route.</p>
<p>So the allocator carries the sequencing as an explicit constraint rather than hoping the
weights hold it: at least 45% of the week from the NOW segments, at most 15% from LATER, no more
than three targets per state. The objective is a sum of per-target values and the constraints
form a partition matroid, so greedy selection is exact rather than approximate. This week's list
comes out {nnow} NOW and {nnext} NEXT.</p>
</div>

<div class="tw"><table>
<thead><tr><th>Phase</th><th>Organization</th><th>Seg</th><th>St</th><th>P(win)</th>
<th>P(fit)</th><th>P(role)</th><th>Reach</th><th>Exp. value</th><th>Rubric</th><th>Tier</th>
<th>Top attributions</th></tr></thead>
<tbody>{wk_rows}</tbody></table></div>

<div class="prose">
<p>Every row carries exact TreeSHAP contributions from LightGBM's <code>pred_contrib</code>, so
the briefing can print the reason next to the name. It also carries a rubric total on the
existing 0&ndash;65 scale with its A/B/C tier, because a score nobody can check is a score nobody
will act on. Dimensions 1, 2, 4 and 7 become computed; 3, 5 and 6 stay deterministic. The output
is legible to someone who has never opened the model.</p>
</div>
</div></section>

<!-- 10 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;10</span><h2>What this does not do</h2></div>
<div class="prose">
<ol>
<li><strong>The numbers above are from simulation.</strong> State anchors, prime award IDs and
obligation totals are real, taken from the 2026-09-03 briefing and the USAspending records it
cites. The organization population and award outcomes are generated. Model quality here is
evidence that the harness is sound and the metrics are honestly computed &mdash; it is not
evidence of live accuracy, and no figure on this page should be repeated to a partner.</li>
<li><strong>Expected value is an ordering, not a forecast</strong>, until Model B has roughly
fifty labelled deployments. See &sect;&nbsp;7.</li>
<li><strong>Partnership-graph features are unproven.</strong> They contribute zero gain in
simulation for a structural reason that will not hold on live data. Re-check at first live
training.</li>
<li><strong>Contact-level resolution is out of scope here.</strong> This ranks organizations.
Turning an organization into three named humans with verified emails and a role classification
is a separate pipeline, and it is the one that determines whether any of this converts.</li>
<li><strong>It will degrade the moment it succeeds.</strong> Once the model chooses who gets
contacted, the SCAR assumption behind Model B breaks and the award labels start reflecting
Avocado's own presence. Log every scored list with its timestamp so a future refit can condition
on what was recommended, not only on what happened.</li>
</ol>
</div>
</div></section>

<!-- 11 -->
<section><div class="wrap">
<div class="sec-h"><span class="sec-n">&sect;&nbsp;11</span><h2>Build order</h2></div>
<div class="prose">
<p>Nothing here requires the whole system to exist before any of it is useful.</p>
<ol>
<li><strong>Briefing parser and diff engine, one week &mdash; already written.</strong> Every
Civic Operator edition becomes an immutable snapshot; deltas become triggers. A contact flipping
from "Not published" to source-verified, a due date moving, a subaward cohort growing from 19 to
24 &mdash; each is an outreach event that is invisible if you only ever read today's edition.
Zero machine learning, and it pays for itself the first time a deadline moves.</li>
<li><strong>Cascade graph and unobligated remainder, one week.</strong> USAspending subaward
endpoints, the subtraction in &sect;&nbsp;1, one table. Answers the open question of which states
to pilot in with a computed number.</li>
<li><strong>Model A on real award history, three to four weeks.</strong> Assistance listings
93.798, 93.505, 93.926, 93.994 and 93.224 give several thousand real labelled events. The
protocol in &sect;&nbsp;4 runs unchanged.</li>
<li><strong>Solicitation document intelligence, two weeks.</strong> Clause extraction feeding
Model C. Idaho's Laserfiche WebLink is scriptable; most state portals are.</li>
<li><strong>Model B, ongoing.</strong> Blocked on labels, not on code. Every closed-won and
closed-lost outcome logged from today forward is a training example, which is a reason to
instrument the CRM now rather than later.</li>
</ol>
<h3>What the parser found in the 2026-09-03 edition</h3>
<p>Run against the real briefing, the parser reads 45 contact rows and 4 opportunities. Of those
45 rows, <strong>6 carry a public source and 39 do not</strong>. Civic Operator is scrupulous
about the distinction and marks every unsourced row, which is the discipline that makes the feed
worth paying for &mdash; but it means roughly six in seven contacts in a given edition are
candidates for a resolution pipeline rather than addresses to mail. Government email patterns are
inferable and verifiable (<code>firstname.lastname@ky.gov</code> is unmistakable from the
Kentucky block alone), so this is a solvable gap and a large one.</p>
<p>Writing that parser also surfaced a bug worth repeating because it is the kind that fails
silently. The first version keyed rows on contact name. The 2026-09-03 edition contains the
literal string "No named individual published" five times across five different agencies, so
name-keyed rows collapse and every subsequent change to four of them becomes undetectable. The
shipped version keys on (opportunity, name, organization) and raises a
<code>duplicate_key</code> event rather than letting one row quietly win. Across this edition
that recovers 3 rows that would otherwise have disappeared. A diff engine that misses changes is
worse than no diff engine, because it is trusted.</p>

<p>Steps one and two are the ones to do first regardless of whether the models ever get built.
They convert a subscription that prints a document into an asset that accumulates.</p>
</div>
</div></section>

</main>

<footer class="foot"><div class="wrap prose">
<p>Prime Applicant Prediction v0.9 &middot; {R['n_pairs']:,} pairs &middot; {R['n_features']}
candidate features, {R['n_selected']} shipped &middot; four forward-chained folds &middot;
LightGBM LambdaRank, Elkan&ndash;Noto PU, isotonic calibration, split conformal at
&alpha;&nbsp;=&nbsp;0.10.</p>
<p>Confidential &mdash; MNDA between Avocado Health and Bhuvan Kanna, executed 2026-08-09.
Contains no Avocado partner terms, deal economics, or material from the ICP matrix, HMA report
or Riverside brief.</p>
</div></footer>

</body>
</html>
"""

Path("/mnt/user-data/outputs").mkdir(parents=True, exist_ok=True)
out = Path("/mnt/user-data/outputs/prime-applicant-prediction.html")
out.write_text(HTML)
print(f"wrote {out}  {len(HTML):,} bytes")
