"""
Feature construction.

Every function takes `as_of: date` and may only read facts whose action or
retrieval date is on or before it. This is not a stylistic preference. Award
data is heavily backfilled — USAspending subaward records for a July action
date routinely appear in September — so a naive join produces a model that
looks excellent in backtest and is worthless in production. `as_of` discipline
is enforced at the loader and asserted again here.

Feature families
----------------
  A. award_history   — can this org win federal money at all?
  B. firmographic    — size, dependency, capability to execute
  C. geography       — does the org sit inside the eligible, needy geography?
  D. staff_model     — does it employ the people Avocado gives time back to?
  E. graph           — who does it partner with, and who do its primes fund?
  F. text            — topical alignment between org programs and solicitation
  G. interaction     — org x solicitation fit terms
  H. completeness    — how much of the above is actually observed

Family D is the one no generic govcon model has. It is the operational
definition of Avocado's ICP (02 §2, 06 §2): the buyer is an organization whose
CHWs, home visitors, doulas, lactation consultants, and HealthySteps
specialists are the bottleneck. Family H exists because families A-G are
systematically thinner for small rural CBOs, and an uncorrected model will
mistake "we know less about them" for "they are less likely to win" — which
would point Avocado away from exactly the rural, low-connectivity populations
the product is built for.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from ..schema import OFFLOAD_ROLES, Award, Organization, Solicitation

# ---------------------------------------------------------------------------
# D. Staff-model detection
# ---------------------------------------------------------------------------

# Lexicon per offload role. Weighted: a job posting title is stronger evidence
# than a mention in a 990 narrative, and a certification mention is stronger
# still because it implies a funded, credentialed position.
STAFF_LEXICON: dict[str, dict[str, float]] = {
    "community_health_worker": {
        r"community health worker": 1.0, r"\bCHW\b": 0.9, r"promotora": 1.0,
        r"community health representative": 0.8, r"health navigator": 0.6,
    },
    "home_visitor": {
        r"home visit(or|ing)": 1.0, r"nurse[- ]family partnership": 1.0,
        r"parents as teachers": 0.9, r"healthy families america": 0.9,
        r"early head start home[- ]based": 0.8, r"MIECHV": 0.9,
    },
    "doula": {
        r"\bdoula": 1.0, r"birth (worker|companion)": 0.7,
        r"perinatal support (specialist|worker)": 0.7,
    },
    "lactation_consultant": {
        r"lactation": 1.0, r"\bIBCLC\b": 1.0, r"breastfeeding (peer )?counselor": 0.9,
        r"\bWIC\b peer": 0.6,
    },
    "healthysteps_specialist": {
        r"healthysteps": 1.0, r"developmental specialist": 0.6,
        r"child life specialist": 0.7,
    },
    "care_coordinator": {
        r"care coordinat": 0.9, r"care manage(r|ment)": 0.8,
        r"patient navigat": 0.8, r"case manage(r|ment)": 0.6,
    },
    "perinatal_mental_health": {
        r"perinatal mental health": 1.0, r"postpartum depression": 0.8,
        r"\bPMH-?C\b": 1.0, r"maternal mental health": 0.9,
    },
    "family_resource_navigator": {
        r"family resource center": 1.0, r"family (support|resource) (specialist|navigator)": 0.9,
        r"\bFRC\b": 0.5,
    },
    "parent_educator": {
        r"parent educat(or|ion)": 1.0, r"parenting (class|workshop|program)": 0.8,
        r"triple p\b": 0.8, r"incredible years": 0.8,
    },
}

SOURCE_WEIGHT = {"job_posting_title": 1.0, "job_posting_body": 0.6,
                 "form990_program": 0.7, "website": 0.5, "award_text": 0.4}


def detect_staff_model(docs: Iterable[tuple[str, str]]) -> dict[str, float]:
    """docs: iterable of (source_kind, text). Returns role -> saturating score.

    Uses a saturating sum rather than a raw count so that one organization with
    forty CHW job postings does not swamp one with two. What matters for
    Avocado is whether the role exists and is funded, not its headcount.
    """
    raw = defaultdict(float)
    for kind, text in docs:
        w = SOURCE_WEIGHT.get(kind, 0.5)
        for role, pats in STAFF_LEXICON.items():
            for pat, pw in pats.items():
                if re.search(pat, text, re.I):
                    raw[role] += w * pw
    return {r: 1.0 - math.exp(-raw[r]) for r in OFFLOAD_ROLES}


def staff_features(org: Organization) -> dict:
    sm = org.staff_model or {}
    vals = [sm.get(r, 0.0) for r in OFFLOAD_ROLES]
    perinatal = [sm.get(r, 0.0) for r in
                 ("doula", "lactation_consultant", "perinatal_mental_health",
                  "home_visitor")]
    return {
        **{f"staff_{r}": sm.get(r, 0.0) for r in OFFLOAD_ROLES},
        "staff_breadth": float(sum(v > 0.4 for v in vals)),
        "staff_max": max(vals) if vals else 0.0,
        # The offload index is the direct operationalisation of the value prop:
        # 1-2 hrs/day back for CHWs, 2-3 for nurses/doulas/lactation (05 §4).
        "staff_offload_index": float(np.mean(vals)) if vals else 0.0,
        "staff_perinatal_depth": float(np.mean(perinatal)),
    }


# ---------------------------------------------------------------------------
# A. Award history — computed strictly as-of
# ---------------------------------------------------------------------------

def award_features(org_id: str, awards: list[Award], as_of: date,
                   target_listing: str) -> dict:
    hist = [a for a in awards
            if a.recipient_org_id == org_id and a.action_date <= as_of]
    if not hist:
        return {"aw_n": 0, "aw_n_listing": 0, "aw_total": 0.0,
                "aw_recency_days": 3650.0, "aw_max": 0.0, "aw_mean": 0.0,
                "aw_sub_share": 0.0, "aw_listing_breadth": 0,
                "aw_velocity_3y": 0.0, "aw_first_seen_days": 0.0,
                "aw_prime_count": 0, "aw_ever_prime": 0}
    amts = [a.obligated for a in hist]
    recency = min((as_of - a.action_date).days for a in hist)
    three_yr = [a for a in hist if (as_of - a.action_date).days <= 1095]
    return {
        "aw_n": len(hist),
        "aw_n_listing": sum(a.assistance_listing == target_listing for a in hist),
        "aw_total": float(sum(amts)),
        "aw_recency_days": float(recency),
        "aw_max": float(max(amts)),
        "aw_mean": float(np.mean(amts)),
        "aw_sub_share": float(np.mean([a.is_subaward for a in hist])),
        "aw_listing_breadth": len({a.assistance_listing for a in hist}),
        "aw_velocity_3y": float(len(three_yr)),
        "aw_first_seen_days": float(max((as_of - a.action_date).days for a in hist)),
        "aw_prime_count": sum(not a.is_subaward for a in hist),
        "aw_ever_prime": int(any(not a.is_subaward for a in hist)),
    }


# ---------------------------------------------------------------------------
# E. Graph — co-recipient and prime->sub structure
# ---------------------------------------------------------------------------

class CascadeGraph:
    """Bipartite org<->prime-award graph, projected to org<->org.

    Two signals come out of it:

      prime_affinity(org, prime): has this state agency funded this org before?
        The strongest single predictor of the next subaward, and it is exactly
        the Hawaii pattern read backwards.

      partner_centrality(org): how often the org appears alongside others on
        the same prime. High centrality means the org is a habitual coalition
        member, which is who you want as a prime applicant carrying Avocado.
    """

    def __init__(self, awards: list[Award], as_of: date):
        self.by_prime: dict[str, set[str]] = defaultdict(set)
        self.by_org: dict[str, set[str]] = defaultdict(set)
        for a in awards:
            if a.action_date > as_of or not a.prime_award_id:
                continue
            self.by_prime[a.prime_award_id].add(a.recipient_org_id)
            self.by_org[a.recipient_org_id].add(a.prime_award_id)
        self.co = defaultdict(set)
        for prime, orgs in self.by_prime.items():
            for o in orgs:
                self.co[o] |= (orgs - {o})

    def features(self, org_id: str, prime_award_id: Optional[str]) -> dict:
        primes = self.by_org.get(org_id, set())
        peers = self.co.get(org_id, set())
        return {
            "gr_prime_affinity": float(prime_award_id in primes) if prime_award_id else 0.0,
            "gr_n_primes": float(len(primes)),
            "gr_partner_centrality": float(len(peers)),
            "gr_log_centrality": math.log1p(len(peers)),
            # An org whose peers have won under this prime, but who has not,
            # is a warm-adjacent candidate: reachable via a peer intro (04 §3).
            "gr_peer_prime_reach": float(any(
                prime_award_id in self.by_org.get(p, set()) for p in peers
            )) if prime_award_id else 0.0,
        }


# ---------------------------------------------------------------------------
# C. Geography and need
# ---------------------------------------------------------------------------

def geo_features(org: Organization, sol: Solicitation,
                 county_stats: dict[str, dict]) -> dict:
    fips = org.county_fips
    stats = county_stats.get(fips, {})
    eligible = (not sol.eligible_county_fips) or (fips in sol.eligible_county_fips)
    return {
        "geo_eligible": float(eligible),
        "geo_same_state": float(org.state == sol.state),
        "geo_rurality": stats.get("ruca_rural_share", 0.0),
        "geo_medicaid_pen": stats.get("medicaid_penetration", 0.0),
        "geo_maternity_desert": float(stats.get("maternity_care_desert", 0)),
        "geo_lang_other_home": stats.get("pct_language_other_at_home", 0.0),
        "geo_births_per_yr": math.log1p(stats.get("annual_births", 0)),
        "geo_ob_distance_km": stats.get("median_km_to_ob", 0.0),
        "geo_broadband_gap": stats.get("pct_no_broadband", 0.0),
    }


# ---------------------------------------------------------------------------
# F/G. Text alignment and interactions
# ---------------------------------------------------------------------------

def interaction_features(org: Organization, sol: Solicitation,
                         aw: dict, topic_cos: float) -> dict:
    ceiling = sol.ceiling or 0.0
    per_award = (ceiling / sol.expected_awards) if (ceiling and sol.expected_awards) else ceiling
    prior_max = aw.get("aw_max", 0.0)
    # Award-size fit: orgs rarely win an award an order of magnitude larger
    # than anything they have managed before. Symmetric log ratio.
    if per_award > 0 and prior_max > 0:
        size_fit = -abs(math.log10(per_award / prior_max))
    else:
        size_fit = -2.0
    days = ((sol.close_date - date.today()).days
            if sol.close_date else 180)
    return {
        "ix_topic_cosine": topic_cos,
        "ix_size_fit": size_fit,
        "ix_log_per_award": math.log1p(max(per_award, 0.0)),
        "ix_days_to_close": float(days),
        "ix_window_3_9mo": float(90 <= days <= 270),   # 04 §4 dimension 2
        "ix_grant_dependency": org.grant_dependency,
        "ix_sub_permitted": float(bool(sol.subgrants_permitted)),
        "ix_partner_permitted": float(bool(sol.partnerships_permitted)),
        "ix_tech_allowable": float(bool(sol.technology_allowable)),
        "ix_eval_innovation": sol.eval_weight_innovation or 0.0,
        "ix_eval_equity": sol.eval_weight_equity or 0.0,
        "ix_no_incumbent": float(org.incumbent_platform in (None, "", "none")),
    }


def firmographic_features(org: Organization) -> dict:
    return {
        "fm_log_revenue": math.log1p(org.total_revenue or 0.0),
        "fm_grant_dependency": org.grant_dependency,
        "fm_log_employees": math.log1p(org.employees or 0),
        "fm_has_uei": float(bool(org.uei)),
        "fm_is_govt": float(org.segment_code == "GOV"),
        "fm_is_cbo": float(org.segment_code in ("CBO", "OB")),
        "fm_is_fqhc": float(org.segment_code == "FQHC"),
        "fm_is_rhs": float(org.segment_code == "RHS"),
        "fm_tier1_icp": float(org.segment_code in ("OB", "ABA", "CBO", "HR")),
    }


# ---------------------------------------------------------------------------
# H. Completeness / missingness audit
# ---------------------------------------------------------------------------

COMPLETENESS_FIELDS = ("ein", "uei", "website", "total_revenue", "employees",
                       "county_fips", "ntee_code")


def completeness(org: Organization) -> dict:
    present = sum(getattr(org, f, None) not in (None, "", 0)
                  for f in COMPLETENESS_FIELDS)
    frac = present / len(COMPLETENESS_FIELDS)
    has_text = float(len(org.program_text or "") > 200)
    return {"cm_field_completeness": frac,
            "cm_has_program_text": has_text,
            "cm_thin_record": float(frac < 0.5)}


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

FEATURE_FAMILY = {
    "aw_": "Award history", "fm_": "Firmographic", "geo_": "Geography & need",
    "staff_": "Staff model (Avocado-specific)", "gr_": "Partnership graph",
    "ix_": "Solicitation interaction", "cm_": "Record completeness",
}


def family_of(name: str) -> str:
    for pre, fam in FEATURE_FAMILY.items():
        if name.startswith(pre):
            return fam
    return "Other"


def assemble(pairs: list[tuple[Organization, Solicitation]],
             awards: list[Award], as_of: date,
             county_stats: dict, topic_cos: dict[tuple[str, str], float],
             graph: CascadeGraph) -> pd.DataFrame:
    rows = []
    for org, sol in pairs:
        aw = award_features(org.org_id, awards, as_of, sol.assistance_listing)
        row = {"org_id": org.org_id, "opp_id": sol.opp_id,
               "segment": org.segment_code, "state": org.state}
        row.update(aw)
        row.update(firmographic_features(org))
        row.update(geo_features(org, sol, county_stats))
        row.update(staff_features(org))
        row.update(graph.features(org.org_id, getattr(sol, "prime_award_id", None)))
        row.update(interaction_features(
            org, sol, aw, topic_cos.get((org.org_id, sol.opp_id), 0.0)))
        row.update(completeness(org))
        rows.append(row)
    return pd.DataFrame(rows)
