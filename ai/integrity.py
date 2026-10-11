"""
VeriKarbon integrity layer: decides which monitoring records are trustworthy enough to
anchor on-chain, and how much the plant's reported emissions could be understated.

Two complementary detectors:
  1. Physics rules   - hard limits from EAF process physics (energy per tonne, metallic
                       yield, electrode and fuel intensity, frozen meters).
  2. Isolation Forest - unsupervised ML on intensity ratios; catches subtler combinations
                       that individually stay inside the rule limits.

A record is FLAGGED if either detector fires. The verifier then reviews only flagged hours
(the "where to sample" list) instead of the whole year.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

import config as C

FEATURES = ["eaf_kwh_per_t", "yield", "electrode_kg_per_t", "eaf_ng_gj_per_t", "rm_ng_gj_per_t", "eaf_mwh_per_scrap_t"]


# --------------------------------------------------------------------------- features
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    prod = d["billet_t"] > 0
    safe = d["billet_t"].where(prod)
    d["producing"] = prod
    d["eaf_kwh_per_t"] = d["eaf_mwh"] * 1000 / safe
    d["yield"] = d["billet_t"] / d["scrap_t"].where(d["scrap_t"] > 0)
    d["electrode_kg_per_t"] = d["electrode_kg"] / safe
    d["eaf_ng_gj_per_t"] = d["eaf_ng_gj"] / safe
    billet_charged = (d["rebar_t"] / C.RM_YIELD).where(d["rebar_t"] > 0)
    d["rm_ng_gj_per_t"] = d["rm_ng_gj"] / billet_charged
    # scrap is weighed independently of billet output: a second, cross-checking denominator
    d["eaf_mwh_per_scrap_t"] = d["eaf_mwh"] * 1000 / d["scrap_t"].where(d["scrap_t"] > 0)
    # frozen meter: same electricity value repeated while production changes
    same = d["eaf_mwh"].diff().abs().lt(1e-9)
    d["frozen_meter"] = same | same.shift(-1, fill_value=False)
    return d


# --------------------------------------------------------------------------- detectors
def rule_flags(d: pd.DataFrame) -> pd.DataFrame:
    reasons = pd.Series([[] for _ in range(len(d))], index=d.index)
    for col, (lo, hi) in C.BOUNDS.items():
        bad = d["producing"] & d[col].notna() & ~d[col].between(lo, hi)
        for i in d.index[bad]:
            reasons[i] = reasons[i] + [f"{col}={d.at[i, col]:.2f} outside [{lo}, {hi}]"]
    for i in d.index[d["frozen_meter"] & d["producing"]]:
        reasons[i] = reasons[i] + ["electricity meter value frozen"]
    idle_energy = ~d["producing"] & (d["eaf_mwh"] > 3)
    for i in d.index[idle_energy]:
        reasons[i] = reasons[i] + ["high electricity while not producing"]
    d = d.copy()
    d["rule_reasons"] = reasons
    d["rule_flag"] = reasons.str.len() > 0
    return d


def ml_flags(d: pd.DataFrame, contamination: float = 0.035, seed: int = 0) -> pd.DataFrame:
    d = d.copy()
    d["ml_score"] = 0.0
    d["ml_flag"] = False
    m = d["producing"] & d[FEATURES].notna().all(axis=1)
    X = RobustScaler().fit_transform(d.loc[m, FEATURES])
    iso = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed).fit(X)
    d.loc[m, "ml_score"] = -iso.score_samples(X)          # higher = more anomalous
    d.loc[m, "ml_flag"] = iso.predict(X) == -1
    return d


# --------------------------------------------------------------------------- emissions
def emissions(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["eaf_direct_t"] = (d["eaf_ng_gj"] * C.NG_EF_KG_PER_GJ
                         + (d["electrode_kg"] + d["charge_carbon_kg"]) * C.C_EF_KG_PER_KG) / 1000
    d["eaf_indirect_t"] = d["eaf_mwh"] * C.GRID_EF_T_PER_MWH
    d["rm_direct_t"] = d["rm_ng_gj"] * C.NG_EF_KG_PER_GJ / 1000
    d["rm_indirect_t"] = d["rm_mwh"] * C.GRID_EF_T_PER_MWH
    return d


def expected_emissions(d: pd.DataFrame) -> pd.Series:
    """Emissions each flagged hour *should* have had, using clean-hour median intensities
    and the independently weighed scrap input as the production basis."""
    clean = d[d["producing"] & ~d["flag"]]
    k_eaf = (clean["eaf_direct_t"] + clean["eaf_indirect_t"]).sum() / clean["scrap_t"].sum()
    k_rm = (clean["rm_direct_t"] + clean["rm_indirect_t"]).sum() / clean["rebar_t"].sum()
    return d["scrap_t"] * k_eaf + d["rebar_t"] * k_rm


def analyse(df: pd.DataFrame) -> pd.DataFrame:
    d = emissions(ml_flags(rule_flags(add_features(df))))
    d["flag"] = d["rule_flag"] | d["ml_flag"]
    d["detected_by"] = np.select(
        [d["rule_flag"] & d["ml_flag"], d["rule_flag"], d["ml_flag"]],
        ["rules + ML", "rules", "ML"], default="")
    reported = d[["eaf_direct_t", "eaf_indirect_t", "rm_direct_t", "rm_indirect_t"]].sum(axis=1)
    d["understatement_t"] = np.where(d["flag"], np.clip(expected_emissions(d) - reported, 0, None), 0.0)
    return d


# --------------------------------------------------------------------------- evaluation & summary
def evaluate(d: pd.DataFrame) -> dict:
    """Detection quality against the synthetic ground-truth labels (never used for fitting)."""
    truth = d["injected_anomaly"] != "none"
    tp = int((d["flag"] & truth).sum())
    fp = int((d["flag"] & ~truth).sum())
    fn = int((~d["flag"] & truth).sum())
    out = {"precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1)}
    out["f1"] = 2 * out["precision"] * out["recall"] / max(out["precision"] + out["recall"], 1e-9)
    out["recall_by_type"] = {
        k: float(d.loc[d["injected_anomaly"] == k, "flag"].mean())
        for k in sorted(d["injected_anomaly"].unique()) if k != "none"
    }
    return out


def summarise(d: pd.DataFrame) -> dict:
    clean = d[~d["flag"]]
    rebar_t = d["rebar_t"].sum()
    billet_t = d["billet_t"].sum()
    # specific embedded emissions of rebar, from clean data only (t CO2e per t rebar)
    eaf_dir_i = clean["eaf_direct_t"].sum() / clean["billet_t"].sum()
    eaf_ind_i = clean["eaf_indirect_t"].sum() / clean["billet_t"].sum()
    billet_per_rebar = 1 / C.RM_YIELD
    rm_dir_i = clean["rm_direct_t"].sum() / clean["rebar_t"].sum()
    rm_ind_i = clean["rm_indirect_t"].sum() / clean["rebar_t"].sum()
    return {
        "period": f"{d['timestamp'].min():%Y-%m-%d} to {d['timestamp'].max():%Y-%m-%d}",
        "hours": int(len(d)),
        "flagged_hours": int(d["flag"].sum()),
        "readiness_pct": round(100 * (1 - d["flag"].mean()), 1),
        "billet_t": round(float(billet_t), 1),
        "rebar_t": round(float(rebar_t), 1),
        "rebar_direct_t_per_t": round(eaf_dir_i * billet_per_rebar + rm_dir_i, 4),
        "rebar_indirect_t_per_t": round(eaf_ind_i * billet_per_rebar + rm_ind_i, 4),
        "understatement_tco2": round(float(d["understatement_t"].sum()), 1),
    }


# --------------------------------------------------------------------------- evidence (Merkle root)
def _keccak(b: bytes) -> bytes:
    from eth_hash.auto import keccak  # ships with web3
    return keccak(b)


def merkle_root(df: pd.DataFrame) -> str:
    """Keccak-256 Merkle root over canonical JSON of each hourly record (sorted-pair tree,
    same convention as OpenZeppelin MerkleProof). Any edited record changes the root."""
    cols = ["timestamp", "scrap_t", "billet_t", "eaf_mwh", "eaf_ng_gj", "electrode_kg",
            "charge_carbon_kg", "rebar_t", "rm_ng_gj", "rm_mwh"]
    rows = df[cols].assign(timestamp=df["timestamp"].astype(str)).to_dict("records")
    layer = [_keccak(json.dumps(r, sort_keys=True, separators=(",", ":")).encode()) for r in rows]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [_keccak(min(a, b) + max(a, b)) for a, b in zip(layer[::2], layer[1::2])]
    return "0x" + layer[0].hex()
