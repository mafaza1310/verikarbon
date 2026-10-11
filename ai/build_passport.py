"""
Run the integrity layer on the plant's monitoring data and build the on-chain passport payload.

    python ai/build_passport.py

Outputs (ai/out/):
  integrity_report.json  - detection quality, readiness, emissions intensity, understatement
  flagged_hours.csv      - the verifier's sampling list (only these hours need a manual check)
  passport_payload.json  - exact arguments for CarbonPassport.createPassport + attestation hash
"""
import json
from pathlib import Path

import pandas as pd

import integrity as I
from integrity import _keccak

HERE = Path(__file__).parent
DATA = HERE / "data" / "mill_hourly.csv"
OUT = HERE / "out"


def main() -> None:
    if not DATA.exists():
        raise SystemExit("No data yet. Run:  python ai/simulate.py")
    OUT.mkdir(exist_ok=True)
    df = pd.read_csv(DATA, parse_dates=["timestamp"])
    d = I.analyse(df)
    summary = I.summarise(d)
    quality = I.evaluate(d)

    report = {
        "plant": "Synthetic EAF steel plant, Türkiye (SYNTHETIC DATA)",
        "product": "Concrete reinforcing bar (rebar), CN 7214",
        **summary,
        "detection_quality_vs_synthetic_labels": quality,
        "evidence_merkle_root": I.merkle_root(df),
    }
    report_bytes = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False).encode()
    (OUT / "integrity_report.json").write_bytes(report_bytes)

    cols = ["timestamp", "detected_by", "rule_reasons", "ml_score", "billet_t", "eaf_mwh",
            "eaf_kwh_per_t", "yield", "understatement_t"]
    d.loc[d["flag"], cols].to_csv(OUT / "flagged_hours.csv", index=False)

    q_kg = int(round(summary["rebar_t"] * 1000))
    payload = {
        "cnCode": "7214",
        "period": 2026,
        "quantityKg": q_kg,
        "directKg": int(round(summary["rebar_t"] * summary["rebar_direct_t_per_t"] * 1000)),
        "indirectKg": int(round(summary["rebar_t"] * summary["rebar_indirect_t_per_t"] * 1000)),
        "evidenceRoot": report["evidence_merkle_root"],
        # the verifier's attestation commits to the exact integrity report it reviewed
        "attestationHash": "0x" + _keccak(report_bytes).hex(),
    }
    (OUT / "passport_payload.json").write_text(json.dumps(payload, indent=2))

    print(f"Period:            {summary['period']}  ({summary['hours']} hours, SYNTHETIC)")
    print(f"Flagged hours:     {summary['flagged_hours']}  -> verifier samples only these")
    print(f"Data readiness:    {summary['readiness_pct']} %")
    print(f"Detection quality: precision {quality['precision']:.2f}, recall {quality['recall']:.2f}")
    print(f"Hidden emissions:  {summary['understatement_tco2']} tCO2e understated in flagged hours")
    print(f"Rebar intensity:   {summary['rebar_direct_t_per_t']} tCO2e/t direct, "
          f"{summary['rebar_indirect_t_per_t']} tCO2e/t indirect")
    print(f"Evidence root:     {payload['evidenceRoot']}")
    print(f"Written: {OUT}")


if __name__ == "__main__":
    main()
