"""
Generate SYNTHETIC hourly monitoring data for one Turkish EAF steel plant
(meltshop -> billet, rolling mill -> rebar), with labelled injected anomalies.

    python ai/simulate.py            -> ai/data/mill_hourly.csv

The labels (`injected_anomaly`) exist only so we can measure how well the integrity
layer catches manipulation. The detector never sees them.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import config as C

OUT = Path(__file__).parent / "data" / "mill_hourly.csv"
SEED = 2026
DAYS = 120
ANOMALY_RATE = 0.03


def simulate(days: int = DAYS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=days * 24, freq="h")
    n = len(idx)

    # --- production pattern: weekday/weekend + planned maintenance stops
    util = np.where(idx.dayofweek < 6, 0.88, 0.70) + rng.normal(0, 0.05, n)
    maint = np.zeros(n, dtype=bool)
    for start in rng.choice(np.arange(48, n - 12), size=days // 14, replace=False):
        maint[start:start + rng.integers(4, 10)] = True
    util = np.clip(util, 0, 1)
    util[maint] = 0.0

    billet = C.EAF_CAPACITY_T_PER_H * util
    scrap = billet / (C.METALLIC_YIELD * rng.normal(1.0, 0.01, n))
    produce = billet > 0

    def per_t(mean, sd):
        return mean * rng.normal(1.0, sd, n)

    eaf_mwh = np.where(produce, billet * per_t(C.EAF_KWH_PER_T, 0.05) / 1000, rng.uniform(0.3, 1.2, n))
    # legitimate operations noise: first hours after a stop need extra energy (cold furnace)
    restart = produce & ~np.roll(produce, 1)
    restart2 = np.roll(restart, 1) & produce
    eaf_mwh = eaf_mwh * np.where(restart, rng.uniform(1.15, 1.30, n), 1.0) * np.where(restart2, 1.08, 1.0)
    eaf_ng = np.where(produce, billet * per_t(C.EAF_NG_GJ_PER_T, 0.10), 0.0)
    electrode = np.where(produce, billet * per_t(C.ELECTRODE_KG_PER_T, 0.08), 0.0)
    charge_c = np.where(produce, billet * per_t(C.CHARGE_C_KG_PER_T, 0.08), 0.0)

    # rolling mill runs on a 2-hour lag of the meltshop
    rebar = np.roll(billet, 2) * C.RM_YIELD
    rm_ng = np.where(rebar > 0, rebar / C.RM_YIELD * per_t(C.RM_NG_GJ_PER_T, 0.06), rng.uniform(5, 15, n))
    rm_mwh = np.where(rebar > 0, rebar * per_t(C.RM_KWH_PER_T, 0.06) / 1000, rng.uniform(0.2, 0.6, n))

    df = pd.DataFrame({
        "timestamp": idx, "scrap_t": scrap, "billet_t": billet, "eaf_mwh": eaf_mwh,
        "eaf_ng_gj": eaf_ng, "electrode_kg": electrode, "charge_carbon_kg": charge_c,
        "rebar_t": rebar, "rm_ng_gj": rm_ng, "rm_mwh": rm_mwh,
    })
    df["injected_anomaly"] = "none"

    # --- inject manipulation / faults on producing hours
    candidates = np.flatnonzero(produce[24:-24]) + 24
    k = int(ANOMALY_RATE * n)
    picks = rng.choice(candidates, size=k, replace=False)
    kinds = rng.choice(
        ["electricity_underreport", "stuck_meter", "gas_zeroed", "output_inflated"],
        size=k, p=[0.35, 0.2, 0.2, 0.25],
    )
    for i, kind in zip(picks, kinds):
        if kind == "electricity_underreport":      # meter tampered to lower emissions
            df.loc[i, "eaf_mwh"] *= rng.uniform(0.70, 0.90)
        elif kind == "stuck_meter":                # frozen reading repeated for 6 h
            df.loc[i:i + 5, "eaf_mwh"] = df.loc[i, "eaf_mwh"]
            df.loc[i:i + 5, "injected_anomaly"] = kind
            continue
        elif kind == "gas_zeroed":                 # fuel consumption not reported
            df.loc[i, "eaf_ng_gj"] = 0.0
            df.loc[i, "rm_ng_gj"] *= rng.uniform(0.0, 0.2)
        elif kind == "output_inflated":            # production overstated -> lower intensity
            df.loc[i, "billet_t"] *= rng.uniform(1.06, 1.25)
        df.loc[i, "injected_anomaly"] = kind

    # stuck meter labels: only hours where the frozen value actually differs from truth matter;
    # keep the label for all 6 hours (they are all corrupted records)
    num = df.select_dtypes("number").columns
    df[num] = df[num].round(4)
    return df


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = simulate()
    data.to_csv(OUT, index=False)
    print(f"SYNTHETIC data written: {OUT}  ({len(data)} hourly rows)")
    print(data["injected_anomaly"].value_counts().to_string())
