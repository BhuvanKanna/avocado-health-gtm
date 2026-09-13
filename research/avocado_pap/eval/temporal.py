"""
Evaluation.

Forward-chaining only. Award data is backfilled by months, so any random or
stratified split leaks the future and produces a backtest that flatters the
model by 20-30 NDCG points. Each fold trains on solicitations closing on or
before T, calibrates on (T, T+delta], and tests on the next window.

Reported metrics
----------------
  NDCG@k          ranking quality where it is read (k = 10, 20)
  Recall@k        did the eventual awardee make the shortlist
  Hit@k           at least one true positive in the top k, per solicitation
  PR-AUC          class-imbalance-honest, unlike ROC-AUC at 1-3% positives
  ECE             expected calibration error; a p_win of 0.30 must mean 0.30
  Coverage        empirical conformal coverage vs. nominal 1 - alpha
  Set size        mean |prediction set|; the model's own admission of doubt
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score


def dcg(rel: np.ndarray, k: int) -> float:
    rel = rel[:k]
    return float(np.sum((2 ** rel - 1) / np.log2(np.arange(2, len(rel) + 2))))


def ndcg_at_k(y: np.ndarray, s: np.ndarray, k: int = 20) -> float:
    order = np.argsort(-s)
    ideal = np.sort(y)[::-1]
    d, i = dcg(y[order], k), dcg(ideal, k)
    return d / i if i > 0 else 0.0


def recall_at_k(y: np.ndarray, s: np.ndarray, k: int = 20) -> float:
    if (y > 0).sum() == 0:
        return np.nan
    top = np.argsort(-s)[:k]
    return float((y[top] > 0).sum() / (y > 0).sum())


def hit_at_k(y: np.ndarray, s: np.ndarray, k: int = 20) -> float:
    if (y > 0).sum() == 0:
        return np.nan
    return float((y[np.argsort(-s)[:k]] > 0).any())


def expected_calibration_error(y: np.ndarray, p: np.ndarray,
                               bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    ece, n = 0.0, len(p)
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        ece += m.sum() / n * abs(y[m].mean() - p[m].mean())
    return float(ece)


def group_metrics(df: pd.DataFrame, y: np.ndarray, p: np.ndarray,
                  ks=(10, 20)) -> dict:
    p = np.nan_to_num(np.asarray(p, dtype=float), nan=0.0,
                      posinf=0.0, neginf=0.0)
    out = {}
    per_group = {k: {"ndcg": [], "recall": [], "hit": []} for k in ks}
    for _, g in df.assign(_y=y, _p=p).groupby("opp_id", sort=False):
        yy, pp = g["_y"].to_numpy(), g["_p"].to_numpy()
        for k in ks:
            per_group[k]["ndcg"].append(ndcg_at_k(yy, pp, k))
            per_group[k]["recall"].append(recall_at_k(yy, pp, k))
            per_group[k]["hit"].append(hit_at_k(yy, pp, k))
    for k in ks:
        for m in ("ndcg", "recall", "hit"):
            out[f"{m}@{k}"] = float(np.nanmean(per_group[k][m]))
    binary = (y > 0).astype(int)
    out["pr_auc"] = float(average_precision_score(binary, p)) if binary.any() else np.nan
    out["ece"] = expected_calibration_error(binary.astype(float), p)
    out["base_rate"] = float(binary.mean())
    return out


def forward_chain_folds(sols: pd.DataFrame, n_folds: int = 4,
                        cal_days: int = 200, test_days: int = 200):
    """Yield (train_ids, cal_ids, test_ids) by close date."""
    s = sols.dropna(subset=["close_date"]).sort_values("close_date")
    dates = s["close_date"].to_numpy()
    lo, hi = dates.min(), dates.max()
    span = (hi - lo).days
    start = lo + timedelta(days=int(span * 0.32))
    step = max(1, int((span - (start - lo).days - test_days) / n_folds))
    for i in range(n_folds):
        t = start + timedelta(days=i * step)
        c_end = t + timedelta(days=cal_days)
        te_end = c_end + timedelta(days=test_days)
        tr = s[s["close_date"] <= t]["opp_id"].tolist()
        ca = s[(s["close_date"] > t) & (s["close_date"] <= c_end)]["opp_id"].tolist()
        te = s[(s["close_date"] > c_end) & (s["close_date"] <= te_end)]["opp_id"].tolist()
        if len(tr) >= 6 and len(ca) >= 2 and len(te) >= 2:
            yield {"fold": i, "cut": t, "train": tr, "cal": ca, "test": te}
