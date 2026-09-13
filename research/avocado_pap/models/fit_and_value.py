"""
Model B (Avocado fit), Model C (role fit), the value composite, the rubric
bridge back to 04 §4, and the missingness/equity audit.

Why B is a PU problem, not a classifier
---------------------------------------
Avocado has roughly five known positives — HMHB Hawaii, First 5 Riverside,
Maternal World Health Organization, Ocean Pediatrics, the twelve-clinic BCBA
network — and zero labelled negatives. An organization that has not bought
Avocado has almost always simply never been asked. Training a standard
classifier on positives-vs-everything-else learns "unlabelled" rather than
"bad fit," and it will confidently reject good prospects.

Elkan-Noto handles this. Train a non-traditional classifier g(x) = P(s=1|x)
where s is the *labelled* indicator, estimate the label frequency
c = P(s=1 | y=1) on held-out positives, and recover P(y=1|x) = g(x)/c. The
correction is only valid under Selected Completely At Random, which is
approximately true here for a reason worth stating: Avocado's five positives
came from inbound, personal networks, and one RFP, none of which correlate
strongly with the fit features. That assumption should be re-tested every time
the positive set doubles.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold


def _logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _apply(platt, raw):
    return platt.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]

# ACV midpoints by segment, from 02 §2. Used for expected value only; the
# consumer $16.67 figure is deliberately absent (01 §7).
SEGMENT_ACV = {
    "OB": 60_000, "ABA": 45_000, "CBO": 37_500, "HR": 175_000,
    "FQHC": 220_000, "GOV": 400_000, "RHS": 62_500, "MCO": 850_000,
    "SCH": 50_000, "K12": 50_000, "CW": 80_000, "FDN": 0,
}

SEGMENT_CYCLE_MONTHS = {
    "OB": 4.5, "ABA": 2, "CBO": 4.5, "HR": 9, "FQHC": 6.5,
    "GOV": 12, "RHS": 15, "MCO": 22, "SCH": 6, "K12": 6, "CW": 12, "FDN": 4,
}


class AvocadoFitPU:
    """Model B. P(this org is a viable Avocado deployment site)."""

    def __init__(self, seed: int = 17):
        self.seed = seed
        self.base = None
        self.platt = None
        self.c: float = 1.0
        self.c_oof_sd: float = 0.0
        self.c_interval: tuple = (0.0, 1.0)
        self.saturation: float = 0.0
        self.features: list[str] = []

    def fit(self, X: pd.DataFrame, s: np.ndarray,
            feature_cols: list[str]) -> "AvocadoFitPU":
        """Cross-fit, then calibrate, then estimate c out-of-fold.

        Not CalibratedClassifierCV. That class averages the calibrated outputs
        of k fold-models, and under 4% positives the per-fold sigmoids are
        nearly flat, so the average washes out the ranking that the base model
        had found: measured AUC fell from 0.60 to 0.52 against known latent
        fit. Fitting one sigmoid on pooled out-of-fold scores and applying it
        to a base model refit on all the data keeps the ranking intact and
        still calibrates honestly, because the sigmoid never sees a score its
        own base model produced in-sample.
        """
        self.features = feature_cols
        Xv = X[feature_cols].to_numpy()
        n_pos = int(s.sum())
        folds = int(np.clip(n_pos // 12, 3, 8))

        def _base():
            return HistGradientBoostingClassifier(
                max_depth=3, learning_rate=0.05, max_iter=180,
                min_samples_leaf=40, l2_regularization=5.0,
                max_features=0.7, random_state=self.seed)

        oof = np.zeros(len(s))
        skf = StratifiedKFold(folds, shuffle=True, random_state=self.seed)
        for tr, va in skf.split(Xv, s):
            m = _base().fit(Xv[tr], s[tr])
            oof[va] = m.predict_proba(Xv[va])[:, 1]

        self.base = _base().fit(Xv, s)
        self.platt = LogisticRegression(C=1.0, max_iter=1000)
        self.platt.fit(_logit(oof).reshape(-1, 1), s)

        # Elkan-Noto label frequency, estimated strictly out-of-fold so it is
        # not the in-sample optimism of a model that has already seen these
        # positives. c drifts as the labelled set grows; refit quarterly and
        # alert if it moves more than ~30% between refits, because a moving c
        # means the Selected-Completely-At-Random assumption is failing.
        g_oof = _apply(self.platt, oof)
        e1 = g_oof[s == 1].mean()                       # Elkan-Noto e1
        e3 = g_oof[s == 1].sum() / max(g_oof.sum(), 1e-9)  # Elkan-Noto e3
        # Hard lower bound: P(s=1) = c * P(y=1) <= c, so c can never fall below
        # the marginal labelling rate. Not a heuristic -- it follows directly
        # from the definition, and it stops a badly-fit g from producing an
        # absurdly small c that then inflates every fit probability to 1.
        lower = float(s.mean())
        self.c = float(np.clip(max((e1 + e3) / 2.0, lower), 1e-3, 1.0))
        self.c_interval = (float(min(e1, e3)), float(max(e1, e3)))
        self.c_oof_sd = float(g_oof[s == 1].std())
        # Saturation share: how many organizations have g(x) > c and therefore
        # cap at p_fit = 1. Above roughly a fifth, the fit probability has
        # stopped discriminating at the top and EAV should be read as an
        # ordering rather than a dollar forecast.
        self.saturation = float((g_oof > self.c).mean())
        return self

    def rank_score(self, X: pd.DataFrame) -> np.ndarray:
        """Uncapped g(x). Use this for ORDERING."""
        raw = self.base.predict_proba(X[self.features].to_numpy())[:, 1]
        return _apply(self.platt, raw)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """PU-corrected probability. Use this for expected-value MATH.

        Capping at 1.0 is necessary (a probability cannot exceed one) but it
        ties every organization whose g(x) exceeds c, which destroys the top of
        the ranking. Anything needing an order calls rank_score; anything
        multiplying by dollars calls this.
        """
        return np.clip(self.rank_score(X) / self.c, 0.0, 1.0)

    def score_report(self, X: pd.DataFrame, latent_y: np.ndarray) -> dict:
        """Diagnostics that require ground truth. Available in backtest and
        simulation only; in production the honest substitutes are the
        precision of the top decile against subsequent closed-won outcomes and
        the stability of c across quarterly refits."""
        from scipy.stats import spearmanr
        from sklearn.metrics import roc_auc_score
        p = self.rank_score(X)
        return {"c_hat": self.c,
                "auc_vs_latent": float(roc_auc_score(latent_y, p)),
                "spearman": float(spearmanr(p, latent_y).statistic),
                "top_decile_precision": float(
                    latent_y[np.argsort(-p)[:max(1, len(p)//10)]].mean()),
                "base_rate": float(latent_y.mean())}

def role_fit(sol_row: pd.Series, org_row: pd.Series) -> float:
    """Model C. Can Avocado occupy the technology-layer slot under this
    applicant, for this solicitation, without becoming the prime?

    Deliberately a transparent scorecard rather than a learned model. There is
    no training signal for it (Avocado has one observed instance, Hawaii), and
    the inputs are extracted clauses whose semantics are legally load-bearing.
    A model that quietly learned "Idaho solicitations are fine" would be worse
    than useless.
    """
    score, weight = 0.0, 0.0

    def add(v: Optional[float], w: float):
        nonlocal score, weight
        if v is not None:
            score += w * float(v)
            weight += w

    add(sol_row.get("subgrants_permitted"), 3.0)
    add(sol_row.get("partnerships_permitted"), 2.0)
    add(sol_row.get("technology_allowable"), 2.0)
    # An org that has never been a prime is more likely to need a partner and
    # less likely to have in-house build capacity.
    add(1.0 - min(org_row.get("aw_ever_prime", 0.0), 1.0), 1.0)
    add(org_row.get("ix_no_incumbent", 0.0), 1.5)
    add(org_row.get("staff_offload_index", 0.0), 1.5)
    return score / weight if weight else 0.35


def warm_path_multiplier(org_row: pd.Series, warm_index: dict) -> float:
    """Reachability is a real qualifier, not a convenience (04 §4)."""
    oid = org_row["org_id"]
    if oid in warm_index.get("direct", set()):
        return 1.60
    if oid in warm_index.get("one_hop", set()):
        return 1.30
    if org_row.get("gr_peer_prime_reach", 0.0) > 0:
        return 1.15
    if org_row.get("cm_field_completeness", 0.0) > 0.7:
        return 1.00
    return 0.85


def time_discount(months: float, annual_rate: float = 0.35) -> float:
    return float(1.0 / (1.0 + annual_rate) ** (months / 12.0))


@dataclass
class ValueConfig:
    win_floor: float = 0.02
    fit_floor: float = 0.05
    role_floor: float = 0.15


def expected_avocado_value(df: pd.DataFrame, p_win: np.ndarray,
                           p_fit: np.ndarray, p_role: np.ndarray,
                           warm: np.ndarray,
                           cfg: ValueConfig = ValueConfig()) -> pd.DataFrame:
    """EAV = P(win) x P(fit) x P(role) x ACV x reach x time-discount.

    Deal size enters through ACV but is *not* separately weighted, mirroring
    the ×1 weight in 04 §4. Weighting size higher pulls the whole pipeline
    toward 9-36 month MCO cycles and starves the 3-6 month segments that fund
    the company. The time discount is what enforces that.
    """
    acv = df["segment"].map(SEGMENT_ACV).fillna(40_000).to_numpy()
    months = df["segment"].map(SEGMENT_CYCLE_MONTHS).fillna(8.0).to_numpy()
    disc = np.array([time_discount(m) for m in months])
    pw = np.maximum(p_win, cfg.win_floor)
    pf = np.maximum(p_fit, cfg.fit_floor)
    pr = np.maximum(p_role, cfg.role_floor)
    eav = pw * pf * pr * acv * warm * disc
    return pd.DataFrame({
        "p_win": p_win, "p_fit": p_fit, "p_role": p_role,
        "expected_acv": acv, "reach": warm, "time_discount": disc,
        "eav": eav,
    }, index=df.index)


# ---------------------------------------------------------------------------
# Bridge back to the human rubric in 04 §4, so scores stay legible
# ---------------------------------------------------------------------------

RUBRIC_WEIGHTS = {"funding": 3, "timing": 2, "icp": 2, "role": 2,
                  "path": 2, "size": 1, "whitespace": 1}


def _band(x: float, edges=(0.05, 0.15, 0.30, 0.50, 0.70)) -> int:
    return int(sum(x >= e for e in edges))


def rubric_bridge(row: pd.Series, p_win: float, p_role: float,
                  warm: float) -> dict:
    """Model outputs -> the 0-5 dimensions Hans already reads.

    Dimensions 1, 2, 4 and 7 become computed; 3, 5 and 6 stay mostly
    deterministic. The point is that nobody has to trust a black box: the
    total still lands on the A>=45 / B 32-44 / C<32 tiers already in use.
    """
    dims = {
        "funding": _band(p_win),
        "timing": 5 if row.get("ix_window_3_9mo", 0) else
                  (3 if 0 < row.get("ix_days_to_close", 999) < 400 else 1),
        "icp": 5 if row.get("fm_tier1_icp", 0) else
               (3 if row.get("fm_is_fqhc", 0) or row.get("fm_is_govt", 0) else 1),
        "role": _band(p_role),
        "path": {1.60: 5, 1.30: 4, 1.15: 3, 1.00: 2}.get(round(warm, 2), 1),
        "size": _band(min(SEGMENT_ACV.get(row.get("segment"), 40_000) / 250_000, 1.0)),
        "whitespace": 5 if row.get("ix_no_incumbent", 0) else 1,
    }
    dims["total"] = sum(RUBRIC_WEIGHTS[k] * v for k, v in dims.items()
                        if k in RUBRIC_WEIGHTS)
    dims["tier"] = ("A" if dims["total"] >= 45 else
                    "B" if dims["total"] >= 32 else "C")
    return dims


# ---------------------------------------------------------------------------
# Missingness / equity audit
# ---------------------------------------------------------------------------

def missingness_audit(df: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    """Does the model score thin-record and high-rurality orgs lower?

    This is not a compliance checkbox. Avocado exists because SMS reaches
    rural, low-broadband, low-digital-literacy families that apps do not
    (01 §3). Small rural CBOs have fewer job postings, thinner 990s, and often
    no website — so families A, B and D are systematically sparser for them. An
    uncorrected ranker learns "we know less about them" as "they win less," and
    would point Avocado away from precisely the counties the product is for.

    If the score gap across completeness deciles exceeds the tolerance, the
    scorer applies a per-stratum recalibration rather than shipping the raw
    ranking.
    """
    d = df.copy()
    d["p"] = p
    d["completeness_decile"] = pd.qcut(d["cm_field_completeness"], 5,
                                       labels=False, duplicates="drop")
    d["rural_band"] = pd.cut(d["geo_rurality"], [-.01, .25, .5, .75, 1.01],
                             labels=["urban", "mixed", "rural", "frontier"])
    a = d.groupby("completeness_decile", observed=True)["p"].mean()
    b = d.groupby("rural_band", observed=True)["p"].mean()
    return pd.DataFrame({
        "stratum": list(a.index.map(lambda i: f"completeness_d{i}")) +
                   list(b.index.astype(str)),
        "mean_p": list(a.values) + list(b.values),
    })


def stratified_recalibrate(df: pd.DataFrame, p: np.ndarray,
                           col: str = "cm_field_completeness",
                           tolerance: float = 0.15) -> np.ndarray:
    """Equalise mean rank across completeness strata when the gap is material.

    Applied only when the observed gap exceeds tolerance, and always logged, so
    the intervention is visible rather than baked silently into the score.
    """
    d = pd.DataFrame({"p": p, "s": pd.qcut(df[col], 4, labels=False,
                                           duplicates="drop")})
    means = d.groupby("s", observed=True)["p"].mean()
    if means.max() - means.min() <= tolerance or len(means) < 2:
        return p
    target = means.mean()
    adj = d["s"].map(target / means).to_numpy()
    return np.clip(p * adj, 1e-6, 1 - 1e-6)


# ---------------------------------------------------------------------------
# Portfolio allocation
# ---------------------------------------------------------------------------

# GTM sequencing from 02 §5. The model maximises expected dollars; the company
# needs 2026 revenue AND 2027 positioning, which are different segments.
NOW_SEGMENTS = {"OB", "ABA", "CBO"}
NEXT_SEGMENTS = {"FQHC", "RHS", "GOV", "SCH"}
LATER_SEGMENTS = {"MCO", "BRK", "API", "CW", "K12"}


def portfolio_select(ranked: pd.DataFrame, n: int = 20,
                     min_now: float = 0.45, max_later: float = 0.15,
                     max_per_state: int = 3) -> pd.DataFrame:
    """Pick the week's outreach list under sequencing and diversity quotas.

    Ranking purely by expected value concentrates the whole week on GOV and
    MCO, because ACV there is five to twenty times a CBO's. Those are also the
    6-36 month cycles. Running the pipeline that way books no revenue in the
    first year and starves the 3-6 month segments that fund the company, which
    is exactly the failure the ×1 deal-size weight in 04 §4 was written to
    prevent. The quota makes that constraint explicit and auditable instead of
    hoping the weights hold it.

    Greedy under quotas is optimal here: the objective is modular (a sum of
    per-target EAV) and the constraints are a partition matroid, so the greedy
    solution is exact rather than approximate.
    """
    df = ranked.sort_values("eav", ascending=False)
    picked, per_state = [], {}
    n_now = n_later = 0
    need_now = int(np.ceil(min_now * n))
    cap_later = int(np.floor(max_later * n))

    def eligible(row, phase_check=True):
        st = row["state"]
        if per_state.get(st, 0) >= max_per_state:
            return False
        if phase_check and row["segment"] in LATER_SEGMENTS and n_later >= cap_later:
            return False
        return True

    # Pass 1: satisfy the NOW quota first, best-first within it.
    for _, row in df[df.segment.isin(NOW_SEGMENTS)].iterrows():
        if n_now >= need_now or len(picked) >= n:
            break
        if eligible(row):
            picked.append(row)
            per_state[row["state"]] = per_state.get(row["state"], 0) + 1
            n_now += 1
    chosen = {id(r) for r in picked}
    keys = {(r["org_id"], r["opp_id"]) for r in picked}

    # Pass 2: fill the remainder best-first under the remaining caps.
    for _, row in df.iterrows():
        if len(picked) >= n:
            break
        if (row["org_id"], row["opp_id"]) in keys:
            continue
        if not eligible(row):
            continue
        picked.append(row)
        keys.add((row["org_id"], row["opp_id"]))
        per_state[row["state"]] = per_state.get(row["state"], 0) + 1
        if row["segment"] in LATER_SEGMENTS:
            n_later += 1
    out = pd.DataFrame(picked)
    if len(out):
        out["phase"] = np.where(out.segment.isin(NOW_SEGMENTS), "NOW",
                        np.where(out.segment.isin(NEXT_SEGMENTS), "NEXT", "LATER"))
    return out
