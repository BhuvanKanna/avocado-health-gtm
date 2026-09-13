"""
Synthetic world generator.

Purpose: make the pipeline runnable, testable and demonstrable end-to-end
before live credentials exist, with a latent generating process realistic
enough that model quality here is informative rather than decorative.

Design constraints
------------------
1. Real anchors. States, prime award IDs, obligation totals and a set of named
   organizations are taken from the 2026-09-03 Civic Operator briefing and the
   underlying USAspending records it cites, so the graph topology and money
   magnitudes are correct even where the individual rows are simulated.

2. Win and fit are driven by *different* latent factors. Award history, prime
   affinity, geographic eligibility and size fit drive winning. Staff model,
   language need, rurality and absence of an incumbent drive Avocado fit. If
   the two shared a driver, the composite ranking would be tautological and
   the backtest would prove nothing.

3. Realistic pathologies are simulated on purpose: a 1-3% positive rate,
   heavy-tailed revenue, missing-not-at-random firmographics correlated with
   rurality, and backfilled award action dates. A pipeline that has not been
   run against these will break the first week it sees real data.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..schema import OFFLOAD_ROLES, stable_id

# Anchors read from the 2026-09-03 briefing and the USAspending records cited
# in it. Prime obligations and Year-1 award figures are as printed there.
STATE_ANCHORS = {
    "KY": {"prime": "RHTCMS332079", "obligated": 212_905_590.56,
           "first_tier_moved": 20_426_889.00, "n_first_tier": 19},
    "NE": {"prime": "RHTCMS332086", "obligated": 191_400_000.00,
           "first_tier_moved": 3_100_000.00, "n_first_tier": 4},
    "ID": {"prime": "RHTCMS332084", "obligated": 185_974_367.81,
           "first_tier_moved": 0.0, "n_first_tier": 0},
    "MO": {"prime": "RHTCMS332029", "obligated": 204_300_000.00,
           "first_tier_moved": 0.0, "n_first_tier": 0},
    "HI": {"prime": "RHTCMS332015", "obligated": 137_800_000.00,
           "first_tier_moved": 9_400_000.00, "n_first_tier": 7},
    "CA": {"prime": "RHTCMS332006", "obligated": 226_100_000.00,
           "first_tier_moved": 12_800_000.00, "n_first_tier": 11},
    "TX": {"prime": "RHTCMS332048", "obligated": 231_700_000.00,
           "first_tier_moved": 6_200_000.00, "n_first_tier": 5},
    "MS": {"prime": "RHTCMS332028", "obligated": 189_200_000.00,
           "first_tier_moved": 4_700_000.00, "n_first_tier": 6},
}

# Named organizations that appear in the briefing's contact table. Kept so the
# demo output is recognisable to anyone who has read the 2026-09-03 edition.
SEED_ORGS = [
    ("Harrison County Community Hospital", "MO", "RHS"),
    ("Mosaic Life Care", "MO", "RHS"),
    ("HCC Network", "MO", "FQHC"),
    ("Lake Regional Health System", "MO", "RHS"),
    ("Arthur Center Community Health", "MO", "FQHC"),
    ("Missouri Highlands Health Care", "MO", "FQHC"),
    ("FCC Behavioral Health", "MO", "CBO"),
    ("Community Counseling Center", "MO", "CBO"),
    ("Phelps Health", "MO", "RHS"),
    ("Hermann Area District Hospital", "MO", "RHS"),
    ("Hannibal Regional Health Center", "MO", "RHS"),
    ("Idaho Community Health Centers Association", "ID", "FQHC"),
    ("Idaho Hospital Association", "ID", "RHS"),
    ("Jannus — Southwest Idaho AHEC", "ID", "CBO"),
    ("UofL Health – Shelbyville Hospital", "KY", "RHS"),
    ("Healthy Mothers Healthy Babies Coalition of Hawaii", "HI", "CBO"),
    ("First 5 Riverside County", "CA", "CBO"),
    ("Maternal World Health Organization", "GA", "CBO"),
]

SEGMENTS = ["CBO", "OB", "FQHC", "RHS", "GOV", "SCH", "ABA", "MCO"]
SEG_P = [0.22, 0.14, 0.17, 0.16, 0.13, 0.09, 0.06, 0.03]


def make_world(seed: int = 17, n_orgs: int = 4200, n_sols: int = 190):
    rng = np.random.default_rng(seed)
    states = list(STATE_ANCHORS) + ["GA", "AL", "WV", "NM", "MT", "AR", "OK", "SD"]

    # ---------------- counties -------------------------------------------
    counties = []
    for si, st in enumerate(states):
        for i in range(34):
            rural = float(np.clip(rng.beta(2.1, 1.7), 0, 1))
            counties.append({
                "county_fips": f"{si + 1:02d}{i:03d}",
                "state": st,
                "ruca_rural_share": rural,
                "medicaid_penetration": float(np.clip(rng.beta(3, 5) * 0.4 + 0.18 * rural, 0, 1)),
                "maternity_care_desert": int(rng.random() < 0.22 + 0.35 * rural),
                "pct_language_other_at_home": float(np.clip(rng.beta(2, 6) + 0.12 * (st in ("CA", "TX", "NM")), 0, 1)),
                "annual_births": int(rng.lognormal(6.4 - 1.1 * rural, 0.85)),
                "median_km_to_ob": float(np.clip(rng.gamma(2.2, 9 + 30 * rural), 2, 260)),
                "pct_no_broadband": float(np.clip(rng.beta(2, 7) + 0.28 * rural, 0, 1)),
            })
    counties = pd.DataFrame(counties)
    cstats = counties.set_index("county_fips").to_dict("index")

    # ---------------- organizations --------------------------------------
    orgs = []
    for name, st, seg in SEED_ORGS:
        orgs.append({"name": name, "state": st, "segment_code": seg, "seeded": True})
    while len(orgs) < n_orgs:
        st = rng.choice(states)
        seg = rng.choice(SEGMENTS, p=SEG_P)
        orgs.append({"name": None, "state": st, "segment_code": seg, "seeded": False})

    PREFIX = {"CBO": ["Family Resource Network of", "Partners for Healthy Families in",
                      "Parent Coalition of", "Healthy Start of"],
              "OB": ["Perinatal Collaborative of", "Maternal Health Network of",
                     "Birth Justice Alliance of"],
              "FQHC": ["Community Health Center of", "Valley Health Partners of",
                       "Rural Health Clinic Network of"],
              "RHS": ["Regional Medical Center of", "Critical Access Hospital of"],
              "GOV": ["County Health Department of", "District Health Department of"],
              "SCH": ["School District of", "Consolidated Schools of"],
              "ABA": ["Behavioral Partners of", "Spectrum Therapy of"],
              "MCO": ["Managed Health Plan of"]}
    PLACE = ["Cedar", "Wolf Creek", "Harlan", "Blue Ridge", "Verde", "Pine Hollow",
             "Marion", "Elkhorn", "Sandhill", "Cross Plains", "Amber", "Rockvale",
             "Talawanda", "Kittitas", "Wabash", "Bonneville", "Latimer", "Osage"]

    rows = []
    for i, o in enumerate(orgs):
        seg, st = o["segment_code"], o["state"]
        cty = counties[counties.state == st].sample(1, random_state=int(rng.integers(1e9))).iloc[0]
        rural = cty["ruca_rural_share"]
        name = o["name"] or f"{rng.choice(PREFIX[seg])} {rng.choice(PLACE)}"

        rev = float(np.exp(rng.normal({"CBO": 13.6, "OB": 13.4, "FQHC": 16.2,
                                       "RHS": 17.4, "GOV": 15.4, "SCH": 16.0,
                                       "ABA": 14.4, "MCO": 19.2}[seg], 1.15)))
        gov_share = float(np.clip(rng.beta(*{"CBO": (6, 3), "OB": (5, 3), "FQHC": (5, 4),
                                             "RHS": (2, 6), "GOV": (8, 2), "SCH": (7, 3),
                                             "ABA": (1.4, 7), "MCO": (4, 4)}[seg]), 0, 1))

        # Latent staff-model intensity. Segment sets the base; rurality and
        # language need raise perinatal depth. This drives Avocado FIT.
        base = {"CBO": 0.72, "OB": 0.86, "FQHC": 0.55, "RHS": 0.30,
                "GOV": 0.58, "SCH": 0.26, "ABA": 0.30, "MCO": 0.24}[seg]
        sm = {}
        for r in OFFLOAD_ROLES:
            bump = 0.0
            if r in ("doula", "lactation_consultant", "perinatal_mental_health",
                     "home_visitor") and seg in ("OB", "CBO", "GOV"):
                bump = 0.18
            if r == "community_health_worker":
                bump += 0.16 * rural
            sm[r] = float(np.clip(rng.beta(2, 2) * base + bump - 0.12, 0, 1))

        # Missing-not-at-random: rural, small orgs have thinner records.
        thin = rng.random() < (0.16 + 0.42 * rural) * (1.3 if rev < 6e5 else 0.7)
        rows.append({
            "org_id": stable_id("org", i, name),
            "name": name, "segment_code": seg, "state": st,
            "county_fips": cty["county_fips"],
            "ein": None if thin and rng.random() < 0.6 else f"{rng.integers(10, 99)}-{rng.integers(1e6, 9.9e6):07d}",
            "uei": None if thin and rng.random() < 0.7 else stable_id("uei", i).upper()[:12],
            "ntee_code": None if thin and rng.random() < 0.5 else rng.choice(["E32", "P40", "P46", "E70", "B21"]),
            "website": None if thin and rng.random() < 0.55 else f"https://example-{i}.org",
            "total_revenue": None if thin and rng.random() < 0.35 else rev,
            "govt_grant_revenue": rev * gov_share,
            "employees": None if thin and rng.random() < 0.45 else int(np.clip(rev / 9.5e4, 2, 9000)),
            "incumbent_platform": (rng.choice(["Unite Us", "Findhelp", "Twistle", "none"],
                                              p=[0.09, 0.08, 0.05, 0.78])),
            "seeded": o["seeded"],
            **{f"sm_{r}": sm[r] for r in OFFLOAD_ROLES},
        })
    orgs = pd.DataFrame(rows)
    orgs["incumbent_platform"] = orgs["incumbent_platform"].replace("none", None)

    # ---------------- solicitations --------------------------------------
    LISTINGS = ["93.798", "93.505", "93.926", "93.994", "93.912"]
    TOPICS = {
        "maternal": "maternal infant perinatal prenatal postpartum home visiting doula "
                    "community health worker family support parent education",
        "behavioral": "behavioral health mental health crisis school based family therapy "
                      "parent education workshops youth",
        "access": "rural access telehealth remote patient monitoring transportation "
                  "workforce recruitment retention infrastructure",
        "infrastructure": "capital equipment facility cybersecurity electronic health record "
                          "interoperability data infrastructure",
    }
    sols = []
    t0 = date(2022, 3, 1)
    for i in range(n_sols):
        st = rng.choice(states)
        topic = rng.choice(list(TOPICS), p=[0.34, 0.22, 0.28, 0.16])
        close = t0 + timedelta(days=int(rng.integers(0, 1620)))
        n_awards = int(np.clip(rng.poisson(4.5) + 2, 2, 22))
        ceiling = float(np.exp(rng.normal(15.1, 1.0))) * n_awards
        elig = counties[(counties.state == st) &
                        (counties.ruca_rural_share > rng.uniform(0.15, 0.45))]["county_fips"].tolist()
        sols.append({
            "opp_id": stable_id("opp", i, st, close),
            "title": f"{st} {topic.title()} {'RFA' if rng.random()<.6 else 'RFP'} {close.year}",
            "issuer": f"{st} Department of Health",
            "state": st,
            "assistance_listing": rng.choice(LISTINGS, p=[0.42, 0.18, 0.14, 0.16, 0.10]),
            "status": "awarded" if close < date(2026, 6, 1) else "posted",
            "posted_date": close - timedelta(days=int(rng.integers(28, 90))),
            "close_date": close,
            "ceiling": ceiling,
            "expected_awards": n_awards,
            "eligible_county_fips": elig,
            "eligible_org_types": (["CBO", "OB", "FQHC", "GOV", "RHS"] if topic != "behavioral"
                                   else ["CBO", "SCH", "GOV", "ABA"]),
            "topic": topic,
            "text": TOPICS[topic],
            "prime_award_id": STATE_ANCHORS.get(st, {}).get("prime"),
            "subgrants_permitted": bool(rng.random() < 0.63),
            "partnerships_permitted": bool(rng.random() < 0.81),
            "technology_allowable": bool(rng.random() < (0.86 if topic in ("access", "maternal") else 0.55)),
            "eval_weight_innovation": float(np.clip(rng.beta(2, 6), 0, 1)),
            "eval_weight_equity": float(np.clip(rng.beta(3, 5), 0, 1)),
        })
    sols = pd.DataFrame(sols)

    # ---------------- awards: latent win process -------------------------
    # Winning is driven by capability + incumbency + geography + size fit.
    # Note that staff-model variables are ABSENT here on purpose.
    org_idx = orgs.set_index("org_id")
    prior = {oid: [] for oid in orgs.org_id}
    awards = []
    for s in sols.sort_values("close_date").itertuples():
        pool = orgs[(orgs.state == s.state) &
                    (orgs.segment_code.isin(s.eligible_org_types))]
        if len(pool) < 6:
            pool = orgs[orgs.state == s.state]
        if len(pool) == 0:
            continue
        cap = []
        for o in pool.itertuples():
            hist = [a for a in prior[o.org_id] if a["action_date"] < s.close_date]
            n_hist = len(hist)
            same_listing = sum(a["assistance_listing"] == s.assistance_listing for a in hist)
            max_prior = max([a["obligated"] for a in hist], default=0.0)
            per_award = s.ceiling / max(s.expected_awards, 1)
            size_pen = -abs(math.log10(per_award / max_prior)) if max_prior > 0 else -1.4
            geo = 1.0 if o.county_fips in set(s.eligible_county_fips) else 0.25
            rev = o.total_revenue if o.total_revenue and o.total_revenue > 0 else 4e5
            z = (-3.05
                 + 0.52 * math.log1p(n_hist)
                 + 0.74 * math.log1p(same_listing)
                 + 0.30 * size_pen
                 + 0.95 * geo
                 + 0.21 * math.log1p(rev) / 4.0
                 + 0.44 * (o.segment_code in ("FQHC", "RHS", "GOV"))
                 + rng.normal(0, 0.62))
            cap.append(1 / (1 + math.exp(-z)))
        cap = np.array(cap)
        p = cap / cap.sum()
        k = min(s.expected_awards, len(pool))
        winners = rng.choice(len(pool), size=k, replace=False, p=p)
        for j, w in enumerate(winners):
            o = pool.iloc[w]
            amt = float(np.clip(rng.lognormal(math.log(max(s.ceiling / max(k, 1), 5e4)), 0.55),
                                2.5e4, 4.2e7))
            # Backfill: action dates land after close, and the record appears
            # in USAspending 30-120 days after the action date.
            adate = s.close_date + timedelta(days=int(rng.integers(20, 210)))
            rec = {
                "award_id": stable_id("aw", s.opp_id, o.org_id),
                "recipient_org_id": o.org_id,
                "assistance_listing": s.assistance_listing,
                "prime_award_id": (None if (j == 0 and rng.random() < 0.22)
                                   else STATE_ANCHORS.get(s.state, {}).get("prime", f"PRIME_{s.state}")),
                "obligated": amt, "action_date": adate, "state": s.state,
                "observed_date": adate + timedelta(days=int(rng.integers(30, 120))),
                "program_label": s.topic, "opp_id": s.opp_id,
            }
            awards.append(rec)
            prior[o.org_id].append(rec)
    awards = pd.DataFrame(awards)

    # ---------------- Avocado fit ground truth (for PU simulation) -------
    # Fit is driven by staff model, need, and absence of an incumbent -- a
    # different latent structure from winning.
    sm_cols = [f"sm_{r}" for r in OFFLOAD_ROLES]
    geo_join = orgs.merge(counties, on="county_fips", how="left", suffixes=("", "_c"))
    fit_z = (-1.15
             + 3.1 * geo_join[sm_cols].mean(axis=1)
             + 1.05 * geo_join["pct_language_other_at_home"].fillna(0)
             + 0.85 * geo_join["ruca_rural_share"].fillna(0)
             + 0.70 * geo_join["maternity_care_desert"].fillna(0)
             - 1.35 * geo_join["incumbent_platform"].notna().astype(float)
             + 0.55 * geo_join["segment_code"].isin(["CBO", "OB"]).astype(float))
    orgs["fit_true"] = (1 / (1 + np.exp(-fit_z))).to_numpy()
    # Observed positives: Selected-Completely-At-Random from true positives,
    # at c = 0.06 -- roughly Avocado's actual labelled fraction.
    latent = rng.random(len(orgs)) < orgs["fit_true"]
    orgs["fit_latent"] = latent.astype(int)
    orgs["fit_labelled"] = (latent & (rng.random(len(orgs)) < 0.06)).astype(int)
    for nm in ("Healthy Mothers Healthy Babies Coalition of Hawaii",
               "First 5 Riverside County", "Maternal World Health Organization"):
        orgs.loc[orgs.name == nm, "fit_labelled"] = 1

    return {"orgs": orgs, "sols": sols, "awards": awards,
            "counties": counties, "county_stats": cstats}
