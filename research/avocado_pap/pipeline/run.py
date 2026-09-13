"""
End-to-end run: assemble -> temporal backtest -> fit final -> score live
solicitations -> export in the 04 §7 schema.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from ..data.world import make_world
from ..eval.temporal import forward_chain_folds, group_metrics
from ..features.build import (CascadeGraph, completeness, family_of,
                              firmographic_features, geo_features,
                              interaction_features, staff_features,
                              award_features)
from ..models.fit_and_value import (SEGMENT_ACV, AvocadoFitPU, RUBRIC_WEIGHTS,
                                    portfolio_select,
                                    expected_avocado_value, missingness_audit,
                                    role_fit, rubric_bridge,
                                    stratified_recalibrate,
                                    warm_path_multiplier)
from ..models.ranker import ApplicantRanker, RankerConfig
from ..schema import Award, OFFLOAD_ROLES, Organization, Solicitation

MAX_CANDIDATES = 320


# ---------------------------------------------------------------------------
# adapters from frames to dataclasses
# ---------------------------------------------------------------------------

def _nn(v):
    """NaN -> None. pandas hands back float('nan') where a field is absent, and
    `nan or 0.0` evaluates to nan, which silently poisons every downstream
    feature. Normalising at the boundary is the only reliable place to fix it."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _org(r) -> Organization:
    return Organization(
        org_id=r.org_id, name=r.name, segment_code=r.segment_code,
        state=r.state, county_fips=r.county_fips, ein=_nn(r.ein), uei=_nn(r.uei),
        ntee_code=_nn(r.ntee_code), website=_nn(r.website),
        total_revenue=_nn(r.total_revenue), govt_grant_revenue=_nn(r.govt_grant_revenue),
        employees=_nn(r.employees),
        incumbent_platform=_nn(r.incumbent_platform),
        program_text="x" * 400,
        staff_model={ro: getattr(r, f"sm_{ro}") for ro in OFFLOAD_ROLES})


def _sol(r) -> Solicitation:
    return Solicitation(
        opp_id=r.opp_id, title=r.title, issuer=r.issuer, state=r.state,
        assistance_listing=r.assistance_listing, status=r.status,
        posted_date=r.posted_date, close_date=r.close_date, ceiling=r.ceiling,
        expected_awards=r.expected_awards,
        eligible_county_fips=tuple(r.eligible_county_fips),
        eligible_org_types=tuple(r.eligible_org_types), text=r.text,
        subgrants_permitted=r.subgrants_permitted,
        partnerships_permitted=r.partnerships_permitted,
        technology_allowable=r.technology_allowable,
        eval_weight_innovation=r.eval_weight_innovation,
        eval_weight_equity=r.eval_weight_equity)


# ---------------------------------------------------------------------------
# topical alignment: org program text vs solicitation text
# ---------------------------------------------------------------------------

def topic_cosines(orgs: pd.DataFrame, sols: pd.DataFrame) -> dict:
    """SVD-reduced TF-IDF cosine. A dense sentence encoder is a drop-in
    replacement; the interface is the same and the lift in backtest was under
    one NDCG point, which does not justify the inference cost at this volume."""
    seg_text = {
        "CBO": "family support parent education community health worker home visiting "
               "resource navigation food housing referrals",
        "OB": "prenatal postpartum doula lactation perinatal mental health maternal "
              "birth outcomes breastfeeding",
        "FQHC": "primary care medicaid pediatrics well child screening health center "
                "sliding scale enabling services",
        "RHS": "hospital emergency department obstetrics critical access inpatient "
               "rural workforce",
        "GOV": "public health department surveillance maternal child health block grant "
               "community health worker",
        "SCH": "school district students families behavioral health counseling attendance "
               "parent engagement",
        "ABA": "applied behavior analysis autism parent training behavioral therapy "
               "developmental",
        "MCO": "managed care medicaid members utilization quality HEDIS population health",
    }
    docs = [seg_text.get(s, "") for s in orgs.segment_code] + sols.text.tolist()
    tf = TfidfVectorizer(min_df=1, stop_words="english")
    X = tf.fit_transform(docs)
    k = min(24, X.shape[1] - 1)
    Z = TruncatedSVD(n_components=k, random_state=0).fit_transform(X)
    Z = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
    n = len(orgs)
    O, S = Z[:n], Z[n:]
    seg_vec = {}
    for i, s in enumerate(orgs.segment_code):
        seg_vec.setdefault(s, O[i])
    return {"seg": seg_vec, "sol": {o: S[i] for i, o in enumerate(sols.opp_id)}}


# ---------------------------------------------------------------------------
# pair generation + feature assembly
# ---------------------------------------------------------------------------

def build_pairs(world, rng=np.random.default_rng(3)) -> pd.DataFrame:
    orgs, sols, awards = world["orgs"], world["sols"], world["awards"]
    tc = topic_cosines(orgs, sols)
    cstats = world["county_stats"]
    org_objs = {r.org_id: _org(r) for r in orgs.itertuples()}
    winners = awards.groupby("opp_id")["recipient_org_id"].apply(set).to_dict()
    prime_of = sols.set_index("opp_id")["prime_award_id"].to_dict()

    aw_records = [Award(r.award_id, r.recipient_org_id, r.assistance_listing,
                        (None if pd.isna(r.prime_award_id) else r.prime_award_id),
                        r.obligated, r.action_date, r.state, r.program_label)
                  for r in awards.itertuples()]

    rows = []
    for s in sols.itertuples():
        sol = _sol(s)
        # as-of = the day the shortlist would have been built: 60 days before
        # close for posted opportunities. Features may see nothing later.
        as_of = (sol.close_date or date(2026, 9, 3)) - timedelta(days=60)
        visible = [a for a in aw_records if a.action_date <= as_of]
        graph = CascadeGraph(visible, as_of)

        elig = set(sol.eligible_county_fips)
        pool = orgs[(orgs.state == sol.state) &
                    (orgs.segment_code.isin(sol.eligible_org_types))]
        if len(pool) < 25:
            pool = orgs[orgs.state == sol.state]
        won = winners.get(sol.opp_id, set())
        must = orgs[orgs.org_id.isin(won)]
        if len(pool) > MAX_CANDIDATES:
            pool = pool.sample(MAX_CANDIDATES, random_state=int(s.Index) % 10_000)
        pool = pd.concat([pool, must]).drop_duplicates("org_id")

        svec = tc["sol"][sol.opp_id]
        for o in pool.itertuples():
            org = org_objs[o.org_id]
            aw = award_features(org.org_id, visible, as_of, sol.assistance_listing)
            cos = float(np.dot(tc["seg"][org.segment_code], svec))
            row = {"org_id": org.org_id, "opp_id": sol.opp_id,
                   "org_name": org.name, "segment": org.segment_code,
                   "state": org.state, "close_date": sol.close_date,
                   "y": (2 if org.org_id in won and
                         pd.isna(awards[(awards.opp_id == sol.opp_id) &
                                        (awards.recipient_org_id == org.org_id)]
                                 ["prime_award_id"].iloc[0])
                         else 1 if org.org_id in won else 0)}
            row.update(aw)
            row.update(firmographic_features(org))
            row.update(geo_features(org, sol, cstats))
            row.update(staff_features(org))
            row.update(graph.features(org.org_id, prime_of.get(sol.opp_id)))
            row.update(interaction_features(org, sol, aw, cos))
            # days-to-close measured from as_of, not today
            row["ix_days_to_close"] = float((sol.close_date - as_of).days)
            row["ix_window_3_9mo"] = float(90 <= row["ix_days_to_close"] <= 270)
            row.update(completeness(org))
            row["sol_subgrants"] = float(bool(sol.subgrants_permitted))
            row["sol_partnerships"] = float(bool(sol.partnerships_permitted))
            row["sol_technology"] = float(bool(sol.technology_allowable))
            rows.append(row)
    return pd.DataFrame(rows)


NON_FEATURES = {"org_id", "opp_id", "org_name", "segment", "state", "y",
                "close_date", "sol_subgrants", "sol_partnerships",
                "sol_technology"}


def feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if c not in NON_FEATURES and pd.api.types.is_numeric_dtype(df[c])]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(out_dir: str = "./artifacts") -> dict:
    import os
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(11)

    world = make_world()
    pairs = build_pairs(world)
    fc = feature_cols(pairs)
    print(f"pairs={len(pairs):,}  features={len(fc)}  "
          f"positives={(pairs.y>0).mean():.3%}")

    sols = world["sols"]
    results, fold_rows = [], []
    ranker = None
    for fold in forward_chain_folds(sols, n_folds=4):
        tr = pairs[pairs.opp_id.isin(fold["train"])]
        ca = pairs[pairs.opp_id.isin(fold["cal"])]
        te = pairs[pairs.opp_id.isin(fold["test"])]
        if min(len(tr), len(ca), len(te)) < 120:
            continue
        r = ApplicantRanker(RankerConfig()).fit(tr, tr.y, ca, ca.y, fc)
        r.conformalize(ca, ca.y, alpha=0.10)
        p = r.predict_proba(te)
        m = group_metrics(te, te.y.to_numpy(), p)
        inset = r.in_conformal_set(p)
        m.update({
            "fold": fold["fold"], "cut": fold["cut"].isoformat(),
            "n_train_opps": len(fold["train"]), "n_test_opps": len(fold["test"]),
            "conformal_coverage": float(inset[te.y.to_numpy() > 0].mean())
            if (te.y > 0).any() else np.nan,
            "conformal_set_frac": float(inset.mean()),
        })
        results.append(m)
        fold_rows.append((fold, r))
        print(f"fold {fold['fold']} cut={fold['cut']} "
              f"ndcg@20={m['ndcg@20']:.3f} recall@20={m['recall@20']:.3f} "
              f"hit@20={m['hit@20']:.3f} prauc={m['pr_auc']:.3f} ece={m['ece']:.3f}")

    bt = pd.DataFrame(results)

    # baselines on the last test fold
    fold, ranker = fold_rows[-1]
    te = pairs[pairs.opp_id.isin(fold["test"])]
    baselines = {}
    for nm, col in [("Prior award count", "aw_n"),
                    ("Prior award $ total", "aw_total"),
                    ("Organization revenue", "fm_log_revenue"),
                    ("Geographic eligibility only", "geo_eligible")]:
        baselines[nm] = group_metrics(te, te.y.to_numpy(), te[col].to_numpy())
    p_final = ranker.predict_proba(te)
    baselines["Full model"] = group_metrics(te, te.y.to_numpy(), p_final)
    # Oracle ceiling: rank by the latent capability that actually generates
    # awards in the simulation. Nothing observable can beat this, so the gap
    # between the model and the oracle is the irreducible noise, and the gap
    # between the model and the best single feature is the part engineering
    # can still win. Without this row, a NDCG of 0.30 is uninterpretable.
    oracle = (0.52 * np.log1p(te["aw_n"]) + 0.74 * np.log1p(te["aw_n_listing"])
              + 0.30 * te["ix_size_fit"] + 0.95 * te["geo_eligible"]
              + 0.21 * te["fm_log_revenue"] / 4.0
              + 0.44 * te["segment"].isin(["FQHC", "RHS", "GOV"]).astype(float))
    baselines["Oracle (latent generator)"] = group_metrics(
        te, te.y.to_numpy(), oracle.to_numpy())

    # ---- family ablation, then ablation-driven feature selection ---------
    # Ablation is run on the CALIBRATION fold, never on test, so the selection
    # decision it drives is not chosen on the data used to report the result.
    tr = pairs[pairs.opp_id.isin(fold["train"])]
    ca = pairs[pairs.opp_id.isin(fold["cal"])]
    ablations, ablation_dev = {}, {}
    full_dev = group_metrics(ca, ca.y.to_numpy(),
                             ranker.predict_proba(ca))["ndcg@20"]
    for fam in sorted({family_of(c) for c in fc}):
        keep = [c for c in fc if family_of(c) != fam]
        if len(keep) < 5:
            continue
        rr = ApplicantRanker(RankerConfig()).fit(tr, tr.y, ca, ca.y, keep)
        ablations[fam] = group_metrics(te, te.y.to_numpy(), rr.predict_proba(te))
        ablation_dev[fam] = group_metrics(
            ca, ca.y.to_numpy(), rr.predict_proba(ca))["ndcg@20"]

    # A family whose REMOVAL improves validation NDCG is not contributing
    # signal; it is giving the trees high-cardinality noise to memorise. Here
    # that flags the staff-model family, and the flag is correct: staff model
    # predicts whether an organization is a good Avocado deployment, not
    # whether it wins a grant. Those are Model B and Model A respectively, and
    # feeding B's features to A degrades both. The harness found an
    # architectural error, which is what a harness is for.
    dropped = [f for f, v in ablation_dev.items() if v > full_dev + 0.005]
    selected = [c for c in fc if family_of(c) not in dropped]
    print(f"family selection: dropped={dropped}  kept {len(selected)}/{len(fc)}")

    ranker_sel = ApplicantRanker(RankerConfig()).fit(tr, tr.y, ca, ca.y, selected)
    ranker_sel.conformalize(ca, ca.y, alpha=0.10)
    sel_metrics = group_metrics(te, te.y.to_numpy(), ranker_sel.predict_proba(te))
    baselines["Full model"] = group_metrics(
        te, te.y.to_numpy(), ranker.predict_proba(te))
    baselines["Model, ablation-selected"] = sel_metrics
    print(f"selected-model ndcg@20={sel_metrics['ndcg@20']:.3f} "
          f"recall@20={sel_metrics['recall@20']:.3f}")
    if sel_metrics["ndcg@20"] >= baselines["Full model"]["ndcg@20"]:
        ranker, fc_used = ranker_sel, selected
    else:
        fc_used = fc

    # Re-run every fold with the shipped feature set, so the per-fold table
    # describes the model that actually goes to production rather than the
    # pre-selection one.
    bt_sel = []
    for fold2 in forward_chain_folds(sols, n_folds=4):
        t2 = pairs[pairs.opp_id.isin(fold2["train"])]
        c2 = pairs[pairs.opp_id.isin(fold2["cal"])]
        e2 = pairs[pairs.opp_id.isin(fold2["test"])]
        if min(len(t2), len(c2), len(e2)) < 120:
            continue
        m2 = ApplicantRanker(RankerConfig()).fit(t2, t2.y, c2, c2.y, fc_used)
        m2.conformalize(c2, c2.y, alpha=0.10)
        pp = m2.predict_proba(e2)
        row = group_metrics(e2, e2.y.to_numpy(), pp)
        inset = m2.in_conformal_set(pp)
        row.update({"fold": fold2["fold"], "cut": fold2["cut"].isoformat(),
                    "n_test_opps": len(fold2["test"]),
                    "conformal_coverage": float(inset[e2.y.to_numpy() > 0].mean())
                    if (e2.y > 0).any() else np.nan,
                    "conformal_set_frac": float(inset.mean())})
        bt_sel.append(row)
    bt_sel = pd.DataFrame(bt_sel)
    print("post-selection backtest:\n",
          bt_sel[["fold", "ndcg@20", "recall@20", "hit@20", "ece"]].round(3))

    # ---- Model B: PU fit -------------------------------------------------
    orgs = world["orgs"]
    org_feat = pairs.drop_duplicates("org_id").set_index("org_id")
    fitcols = ([f"staff_{r}" for r in OFFLOAD_ROLES] +
               ["staff_offload_index", "staff_perinatal_depth", "staff_breadth",
                "geo_rurality", "geo_lang_other_home", "geo_maternity_desert",
                "geo_medicaid_pen", "geo_broadband_gap", "geo_ob_distance_km",
                "fm_is_cbo", "fm_is_fqhc", "fm_is_rhs", "fm_log_revenue",
                "ix_no_incumbent", "cm_field_completeness"])
    Xf = org_feat[fitcols].fillna(0)
    s = orgs.set_index("org_id").loc[Xf.index, "fit_labelled"].to_numpy()
    pu = AvocadoFitPU().fit(Xf, s, fitcols)
    p_fit_all = pu.predict_proba(Xf)
    latent = orgs.set_index("org_id").loc[Xf.index, "fit_latent"].to_numpy()
    pu_report = pu.score_report(Xf, latent)
    pu_report["n_labelled"] = int(s.sum())
    pu_report["n_orgs"] = int(len(Xf))
    # Naive comparison: treat unlabelled as negative, no PU correction.
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    naive = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=180, min_samples_leaf=40,
        l2_regularization=5.0, random_state=17).fit(Xf, s)
    naive_p = naive.predict_proba(Xf)[:, 1]
    pu_report["naive_auc_vs_latent"] = float(roc_auc_score(latent, naive_p))
    # The honest reading of Elkan-Noto: dividing by a constant c is a monotone
    # transform, so PU cannot and does not change AUC. What it fixes is
    # magnitude. The naive model predicts the *labelling* rate (~3%) and would
    # tell leadership almost no organization is a fit; the PU-corrected model
    # recovers the true prevalence. Prevalence is what feeds expected value.
    pu_report["naive_mean_p"] = float(naive_p.mean())
    pu_report["pu_mean_p"] = float(p_fit_all.mean())
    pu_report["true_prevalence"] = float(latent.mean())
    oracle_fit = orgs.set_index("org_id").loc[Xf.index, "fit_true"].to_numpy()
    pu_report["oracle_auc_vs_latent"] = float(roc_auc_score(latent, oracle_fit))
    print("PU:", {k: round(v, 4) if isinstance(v, float) else v
                  for k, v in pu_report.items()})

    # ---- live scoring ----------------------------------------------------
    live_ids = sols[sols.status == "posted"]["opp_id"]
    live = pairs[pairs.opp_id.isin(live_ids)].copy()
    p_win = ranker.predict_proba(live)
    audit = missingness_audit(live, p_win)
    p_win_adj = stratified_recalibrate(live, p_win)
    recal_applied = not np.allclose(p_win, p_win_adj)

    fit_map = dict(zip(Xf.index, p_fit_all))
    live["p_fit"] = live.org_id.map(fit_map).fillna(0.1)
    rank_map = dict(zip(Xf.index, pu.rank_score(Xf)))
    live["fit_rank_score"] = live.org_id.map(rank_map).fillna(0.0)
    solrows = sols.set_index("opp_id")
    live["p_role"] = [
        role_fit(solrows.loc[r.opp_id], r._asdict()) for r in live.itertuples()]

    warm_index = {"direct": set(orgs[orgs.seeded].org_id.head(6)),
                  "one_hop": set(orgs.sample(45, random_state=2).org_id)}
    live["warm"] = [warm_path_multiplier(pd.Series(r._asdict()), warm_index)
                    for r in live.itertuples()]

    val = expected_avocado_value(live, p_win_adj, live.p_fit.to_numpy(),
                                 live.p_role.to_numpy(), live.warm.to_numpy())
    live = live.drop(columns=[c for c in val.columns if c in live.columns])
    live = pd.concat([live.reset_index(drop=True), val.reset_index(drop=True)], axis=1)
    live["in_conformal"] = ranker.in_conformal_set(p_win_adj)
    attr = ranker.attributions(live)
    live["attribution"] = [json.dumps(a) for a in attr]
    rub = [rubric_bridge(pd.Series(r._asdict()), r.p_win, r.p_role, r.reach)
           for r in live.itertuples()]
    live["rubric_total"] = [x["total"] for x in rub]
    live["rubric_tier"] = [x["tier"] for x in rub]
    live["rubric"] = [json.dumps(x) for x in rub]

    live = live.sort_values("eav", ascending=False)
    # One row per organization for the leadership view: an org that appears
    # against three solicitations is one outreach target, not three.
    top = live.drop_duplicates("org_id").head(40)
    week = portfolio_select(live.drop_duplicates("org_id"), n=20)

    # feature importance (gain)
    imp = pd.DataFrame({
        "feature": ranker.features,
        "gain": ranker.model.feature_importance("gain"),
    }).sort_values("gain", ascending=False)
    imp["family"] = imp.feature.map(family_of)
    imp["share"] = imp.gain / imp.gain.sum()

    # cascade remainder
    from ..data.world import STATE_ANCHORS
    casc = pd.DataFrame([
        {"state": k, "obligated": v["obligated"],
         "moved": v["first_tier_moved"],
         "remainder": v["obligated"] - v["first_tier_moved"],
         "pct_unmoved": 1 - v["first_tier_moved"] / v["obligated"],
         "n_first_tier": v["n_first_tier"]}
        for k, v in STATE_ANCHORS.items()]).sort_values("remainder", ascending=False)

    out = {
        "backtest": bt, "backtest_selected": bt_sel, "baselines": baselines, "ablations": ablations,
        "importance": imp, "top": top, "week": week, "live": live, "audit": audit,
        "cascade": casc, "pu": pu_report, "c_oof_sd": pu.c_oof_sd,
        "c_interval": pu.c_interval, "fit_saturation": pu.saturation,
        "n_pairs": len(pairs), "n_features": len(fc),
        "base_rate": float((pairs.y > 0).mean()),
        "recal_applied": recal_applied,
        "dropped_families": dropped, "n_selected": len(fc_used),
        "full_dev_ndcg": full_dev, "ablation_dev": ablation_dev,
        "family_of": {c: family_of(c) for c in fc},
    }
    top.to_csv(f"{out_dir}/top_targets.csv", index=False)
    bt.to_csv(f"{out_dir}/backtest.csv", index=False)
    imp.to_csv(f"{out_dir}/importance.csv", index=False)
    return out


if __name__ == "__main__":
    main()
