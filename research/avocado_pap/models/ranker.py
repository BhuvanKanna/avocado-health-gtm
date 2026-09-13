"""
Model A — applicant/win propensity.

Formulation
-----------
Learning-to-rank, not binary classification. The operational question is never
"will this org win money" in the abstract; it is "for THIS solicitation, which
twenty organizations should Bhuvan map contacts for this week." That is a
ranking problem with query groups = solicitations, and the loss should optimise
the top of each list. LightGBM's LambdaRank with NDCG@20 truncation does that
directly.

Label
-----
y = 1 if the org appears as prime awardee or first-tier subrecipient on an
award under the same assistance listing and state, action-dated within 18
months after the solicitation close date. Graded relevance:

    2  prime awardee
    1  first-tier subrecipient
    0  eligible, not selected

Grading matters because a first-tier subrecipient is often a *better* Avocado
prospect than the prime: it has money, it has delivery obligations, and it is
small enough to need a technology partner (04 §2).

Candidate universe
------------------
Negatives are not sampled at random. They are the eligible universe: orgs whose
county is in the solicitation's eligible geography and whose type matches the
eligibility clause. Random negatives make the model learn "is this org even in
the right state," which is trivially true at scan time and destroys the
ranking signal where it matters.

Calibration and uncertainty
---------------------------
Ranker margins are not probabilities. Isotonic regression on a held-out
temporal fold maps margin -> P(win), and split conformal produces a prediction
set with a coverage guarantee: "the true awardee is in this set of k orgs with
probability >= 1 - alpha." That set size is the honest expression of how much
the model actually knows about a given solicitation, and it is what stops the
briefing from printing a confident ranking over a solicitation the model has
no comparable history for.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression


@dataclass
class RankerConfig:
    objective: str = "lambdarank"
    metric: str = "ndcg"
    ndcg_eval_at: tuple = (5, 10, 20)
    lambdarank_truncation_level: int = 30
    learning_rate: float = 0.04
    num_leaves: int = 15
    min_data_in_leaf: int = 60
    feature_fraction: float = 0.55
    bagging_fraction: float = 0.80
    bagging_freq: int = 1
    lambda_l2: float = 10.0
    min_gain_to_split: float = 0.02
    num_boost_round: int = 700
    early_stopping_rounds: int = 60
    label_gain: tuple = (0, 1, 3)      # 0 / sub / prime
    seed: int = 17


def build_labels(pairs: pd.DataFrame, awards: pd.DataFrame,
                 sols: pd.DataFrame, horizon_months: int = 18) -> pd.Series:
    """Graded relevance with a strict forward window."""
    close = sols.set_index("opp_id")["close_date"].to_dict()
    listing = sols.set_index("opp_id")["assistance_listing"].to_dict()
    st = sols.set_index("opp_id")["state"].to_dict()
    idx = {}
    for r in awards.itertuples():
        idx.setdefault((r.recipient_org_id, r.assistance_listing, r.state),
                       []).append((r.action_date, r.prime_award_id))

    out = []
    for r in pairs.itertuples():
        c = close.get(r.opp_id)
        hits = idx.get((r.org_id, listing.get(r.opp_id), st.get(r.opp_id)), [])
        grade = 0
        if c is not None:
            hi = c + timedelta(days=int(30.44 * horizon_months))
            for adate, prime in hits:
                if c <= adate <= hi:
                    grade = max(grade, 2 if prime in (None, "", float("nan")) else 1)
        out.append(grade)
    return pd.Series(out, index=pairs.index, name="y")


def build_candidate_universe(orgs: pd.DataFrame, sol: pd.Series,
                             max_candidates: int = 400) -> pd.DataFrame:
    """Eligible-universe negatives, not random negatives."""
    df = orgs
    if sol.get("eligible_county_fips"):
        elig = set(sol["eligible_county_fips"])
        in_geo = df["county_fips"].isin(elig)
        # keep same-state orgs even outside the named counties: statewide
        # applicants routinely serve counties they are not headquartered in
        df = df[in_geo | (df["state"] == sol["state"])]
    else:
        df = df[df["state"] == sol["state"]]
    if sol.get("eligible_org_types"):
        types = set(sol["eligible_org_types"])
        keep = df["segment_code"].isin(types)
        if keep.sum() >= 10:
            df = df[keep]
    return df.head(max_candidates)


class ApplicantRanker:
    def __init__(self, cfg: RankerConfig = RankerConfig()):
        self.cfg = cfg
        self.model: Optional[lgb.Booster] = None
        self.calibrator: Optional[IsotonicRegression] = None
        self.q_hat: Optional[float] = None
        self.features: list[str] = []

    # -- training -----------------------------------------------------------
    @staticmethod
    def _groups(df: pd.DataFrame) -> np.ndarray:
        return df.groupby("opp_id", sort=False).size().to_numpy()

    def fit(self, train: pd.DataFrame, y_train: pd.Series,
            valid: pd.DataFrame, y_valid: pd.Series,
            feature_cols: list[str]) -> "ApplicantRanker":
        self.features = feature_cols
        train = train.sort_values("opp_id")
        valid = valid.sort_values("opp_id")
        y_train = y_train.loc[train.index]
        y_valid = y_valid.loc[valid.index]

        dtr = lgb.Dataset(train[feature_cols], label=y_train,
                          group=self._groups(train), free_raw_data=False)
        dva = lgb.Dataset(valid[feature_cols], label=y_valid,
                          group=self._groups(valid), reference=dtr,
                          free_raw_data=False)
        params = {
            "objective": self.cfg.objective, "metric": self.cfg.metric,
            "ndcg_eval_at": list(self.cfg.ndcg_eval_at),
            "lambdarank_truncation_level": self.cfg.lambdarank_truncation_level,
            "learning_rate": self.cfg.learning_rate,
            "num_leaves": self.cfg.num_leaves,
            "min_data_in_leaf": self.cfg.min_data_in_leaf,
            "feature_fraction": self.cfg.feature_fraction,
            "bagging_fraction": self.cfg.bagging_fraction,
            "bagging_freq": self.cfg.bagging_freq,
            "lambda_l2": self.cfg.lambda_l2,
            "min_gain_to_split": self.cfg.min_gain_to_split,
            "label_gain": list(self.cfg.label_gain),
            "seed": self.cfg.seed, "verbosity": -1,
            "deterministic": True, "force_row_wise": True,
        }
        self.model = lgb.train(
            params, dtr, num_boost_round=self.cfg.num_boost_round,
            valid_sets=[dva], valid_names=["valid"],
            callbacks=[lgb.early_stopping(self.cfg.early_stopping_rounds,
                                          verbose=False)])
        self._calibrate(valid, y_valid)
        return self

    def _calibrate(self, valid: pd.DataFrame, y_valid: pd.Series):
        margins = self.margin(valid)
        binary = (y_valid.to_numpy() > 0).astype(float)
        self.calibrator = IsotonicRegression(out_of_bounds="clip",
                                             y_min=0.0, y_max=1.0)
        self.calibrator.fit(margins, binary)

    def conformalize(self, cal: pd.DataFrame, y_cal: pd.Series,
                     alpha: float = 0.10):
        """Split conformal on 1 - p. q_hat is the score threshold such that
        the prediction set covers a true positive with prob >= 1 - alpha."""
        p = self.predict_proba(cal)
        pos = p[y_cal.to_numpy() > 0]
        if len(pos) == 0:
            self.q_hat = 0.0
            return self
        scores = 1.0 - pos                       # nonconformity
        n = len(scores)
        k = min(n - 1, int(np.ceil((n + 1) * (1 - alpha))) - 1)
        self.q_hat = float(np.sort(scores)[max(k, 0)])
        return self

    # -- inference ----------------------------------------------------------
    def margin(self, df: pd.DataFrame) -> np.ndarray:
        return self.model.predict(df[self.features],
                                  num_iteration=self.model.best_iteration)

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        m = self.margin(df)
        if self.calibrator is None:
            return 1.0 / (1.0 + np.exp(-m))
        return np.clip(self.calibrator.predict(m), 1e-6, 1 - 1e-6)

    def in_conformal_set(self, p: np.ndarray) -> np.ndarray:
        if self.q_hat is None:
            return np.ones_like(p, dtype=bool)
        return (1.0 - p) <= self.q_hat

    def attributions(self, df: pd.DataFrame, top: int = 6):
        """Exact TreeSHAP contributions from LightGBM (pred_contrib)."""
        contrib = self.model.predict(df[self.features], pred_contrib=True,
                                     num_iteration=self.model.best_iteration)
        out = []
        for row in contrib:
            vals = row[:-1]
            order = np.argsort(-np.abs(vals))[:top]
            out.append([(self.features[i], float(vals[i])) for i in order])
        return out
