"""
VeriKarbon dashboard
    streamlit run ai/app.py

Tabs:
  1. CBAM cost   - what one EU-bound rebar shipment costs with default values vs verified data
  2. Data integrity - which monitoring hours the AI flagged, and why
  3. On-chain    - live passports and carbon-price ledger read from the deployed contracts
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as C
import integrity as I

HERE = Path(__file__).parent
ROOT = HERE.parent
NETWORK = os.environ.get("VK_NETWORK", "sepolia")

# reference palette (light mode): categorical slots 1-2, status "critical", text & grid tokens
BLUE, ORANGE, CRITICAL = "#2a78d6", "#eb6834", "#d03b3b"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"

st.set_page_config(page_title="VeriKarbon", page_icon="🔗", layout="wide")


# --------------------------------------------------------------------------- data
@st.cache_data
def load_analysis() -> tuple[pd.DataFrame, dict, dict]:
    path = HERE / "data" / "mill_hourly.csv"
    if not path.exists():
        import simulate
        path.parent.mkdir(exist_ok=True)
        simulate.simulate().to_csv(path, index=False)
    df = pd.read_csv(path, parse_dates=["timestamp"])
    d = I.analyse(df)
    return d, I.summarise(d), I.evaluate(d)


def read_env(key: str) -> str | None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith(key + "="):
                return line.split("=", 1)[1].strip() or None
    return os.environ.get(key)


def chain_config() -> dict | None:
    for f in (HERE / "out" / f"onchain_{NETWORK}.json", ROOT / "deployments" / f"{NETWORK}.json"):
        if f.exists():
            cfg = json.loads(f.read_text())
            cfg["rpc"] = ("http://127.0.0.1:8545" if NETWORK == "localhost"
                          else read_env("SEPOLIA_RPC_URL") or "https://ethereum-sepolia-rpc.publicnode.com")
            return cfg
    return None


@st.cache_data(ttl=30, show_spinner="Reading the blockchain…")
def read_chain(cfg: dict) -> dict:
    from web3 import Web3
    abi = json.loads((HERE / "abi.json").read_text())
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 20}))
    pp = w3.eth.contract(address=Web3.to_checksum_address(cfg["CarbonPassport"]), abi=abi["CarbonPassport"])
    lg = w3.eth.contract(address=Web3.to_checksum_address(cfg["CarbonPriceLedger"]), abi=abi["CarbonPriceLedger"])
    status = {0: "Pending", 1: "Verified", 2: "Revoked"}
    rows = []
    for i in range(1, pp.functions.nextId().call()):
        p = pp.functions.getPassport(i).call()
        (operator, cn, period, qty, direct, indirect, pre, evid, att, verifier, st_, consumed, declared) = p
        rows.append({
            "Passport": i, "CN code": cn, "Year": period, "Status": status[st_],
            "Quantity (t)": qty / 1000,
            "Intensity (kgCO₂e/t)": pp.functions.intensityPerTonne(i).call(),
            "Consumed (t)": consumed / 1000, "Declared to EU (t)": declared / 1000,
            "Available (t)": pp.functions.availableKg(i).call() / 1000,
            "Evidence root": "0x" + evid.hex()[:10] + "…",
            "Attestation": ("0x" + att.hex()[:10] + "…") if int.from_bytes(att, "big") else "—",
        })
    pays = []
    for j in range(1, lg.functions.nextPaymentId().call()):
        op, period, covered, cents, claimed, _ = lg.functions.payments(j).call()
        pays.append({"Payment": j, "Year": period, "Covered (tCO₂e)": covered / 1000,
                     "Value (€)": cents / 100, "Already deducted (tCO₂e)": claimed / 1000,
                     "Remaining (tCO₂e)": (covered - claimed) / 1000})
    return {"block": w3.eth.block_number, "passports": rows, "payments": pays}


def cbam_cost(tonnes: float, intensity: float, year: int, price: float) -> float:
    """Simplified CBAM cost: embedded direct emissions x payable share x certificate price."""
    return tonnes * intensity * C.PAYABLE_SHARE[year] * price


def default_intensity(year: int, base: float) -> float:
    markup = C.DEFAULT_MARKUP.get(year, 0.30 if year > 2028 else 0.10)
    return base * (1 + markup)


def base_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=10, b=10),
        font=dict(color=TEXT, size=13), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=MUTED)),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED))
    return fig


# --------------------------------------------------------------------------- page
d, summary, quality = load_analysis()
verified_i = summary["rebar_direct_t_per_t"]

st.title("VeriKarbon")
st.caption("Tamper-evident CBAM emissions passports and once-only carbon-price deductions "
           "for Turkish exporters · Track: Carbon Markets & Emissions Transparency · "
           "**All plant data on this page is synthetic.**")

with st.sidebar:
    st.header("Shipment")
    tonnes = st.number_input("Rebar shipped to the EU (t)", 100, 200_000, 5_000, step=500)
    year = st.select_slider("Import year", options=list(C.PAYABLE_SHARE), value=2026)
    price = st.number_input("CBAM certificate price (€/tCO₂e)", 10.0, 300.0, C.CERT_PRICE_EUR, step=1.0)
    base_default = st.number_input("CBAM default value, bars & rods, Türkiye (tCO₂e/t)",
                                   0.1, 5.0, C.CBAM_DEFAULT_T_PER_T, step=0.01,
                                   help="Annex I of Implementing Regulation (EU) 2025/2621 as reported "
                                        "by GreenSutra; direct emissions only. Verify on EUR-Lex.")
    st.caption(f"Network: **{NETWORK}**")

tab_cost, tab_int, tab_chain = st.tabs(["💶 CBAM cost", "🔎 Data integrity (AI)", "⛓️ On-chain passports"])

# --------------------------------------------------------------------------- tab 1
with tab_cost:
    dflt_i = default_intensity(year, base_default)
    c_default = cbam_cost(tonnes, dflt_i, year, price)
    c_verified = cbam_cost(tonnes, verified_i, year, price)
    a, b, c = st.columns(3)
    a.metric(f"Cost with default values ({year})", f"€{c_default:,.0f}",
             help=f"{dflt_i:.2f} tCO₂e/t incl. mark-up")
    b.metric(f"Cost with VeriKarbon-verified data ({year})", f"€{c_verified:,.0f}",
             help=f"{verified_i:.3f} tCO₂e/t direct embedded emissions")
    c.metric("Saved by proving actual emissions", f"€{c_default - c_verified:,.0f}",
             f"{(1 - c_verified / c_default) * 100:.0f}% lower")

    st.subheader("Cost of this shipment as CBAM phases in")
    years = list(C.PAYABLE_SHARE)
    yd = [cbam_cost(tonnes, default_intensity(y, base_default), y, price) for y in years]
    yv = [cbam_cost(tonnes, verified_i, y, price) for y in years]
    fig = go.Figure()
    fig.add_scatter(x=years, y=yd, name="Default values", mode="lines+markers",
                    line=dict(color=ORANGE, width=2), marker=dict(size=8),
                    hovertemplate="€%{y:,.0f}")
    fig.add_scatter(x=years, y=yv, name="Verified actual data", mode="lines+markers",
                    line=dict(color=BLUE, width=2), marker=dict(size=8),
                    hovertemplate="€%{y:,.0f}")
    for series, color, name in ((yd, MUTED, "Default values"), (yv, MUTED, "Verified data")):
        fig.add_annotation(x=years[-1], y=series[-1], text=f"{name}: €{series[-1]:,.0f}",
                           showarrow=False, xanchor="right", yshift=14, font=dict(color=TEXT, size=12))
    fig.update_yaxes(title_text="€ per shipment", tickprefix="€", tickformat=",.0f")
    fig.update_xaxes(dtick=1)
    st.plotly_chart(base_layout(fig), width="stretch")
    st.caption(
        "Simplified model: cost = tonnes × embedded direct emissions × payable share × certificate price. "
        "Payable share rises from 2.5% (2026) to 100% (2034) as EU free allocation is phased out. "
        "Default values carry a 10% (2026), 20% (2027) and 30% (2028+) mark-up. For iron & steel only "
        "direct emissions are priced; indirect emissions are recorded on the passport for transparency. "
        "Verified intensity is computed from the AI-cleaned synthetic plant data.")

# --------------------------------------------------------------------------- tab 2
with tab_int:
    a, b, c, e = st.columns(4)
    a.metric("Hours checked", f"{summary['hours']:,}")
    b.metric("Hours flagged for the verifier", f"{summary['flagged_hours']:,}",
             f"{100 - summary['readiness_pct']:.1f}% of all hours", delta_color="off")
    c.metric("Detection (synthetic test)", f"{quality['recall'] * 100:.0f}% caught",
             f"precision {quality['precision'] * 100:.0f}%", delta_color="off")
    e.metric("Hidden emissions found", f"{summary['understatement_tco2']:,.0f} tCO₂e")

    st.subheader("EAF electricity per tonne of billet, hourly")
    view = d[d["producing"]]
    flagged = view[view["flag"]]
    fig = go.Figure()
    fig.add_scatter(x=view["timestamp"], y=view["eaf_kwh_per_t"], name="Reported (kWh/t)",
                    mode="lines", line=dict(color=BLUE, width=1.2),
                    hovertemplate="%{y:.0f} kWh/t<extra></extra>")
    fig.add_scatter(x=flagged["timestamp"], y=flagged["eaf_kwh_per_t"], name="⚠ Flagged by AI",
                    mode="markers", marker=dict(color=CRITICAL, size=8, symbol="x-thin",
                                                line=dict(width=2, color=CRITICAL)),
                    customdata=flagged["detected_by"],
                    hovertemplate="⚠ flagged by %{customdata}: %{y:.0f} kWh/t<extra></extra>")
    lo, hi = C.BOUNDS["eaf_kwh_per_t"]
    for v in (lo, hi):
        fig.add_hline(y=v, line=dict(color=MUTED, width=1, dash="dot"),
                      annotation_text=f"physics limit {v:.0f}", annotation_font_color=MUTED)
    fig.update_yaxes(title_text="kWh per tonne")
    st.plotly_chart(base_layout(fig, 360), width="stretch")

    left, right = st.columns([1, 2])
    with left:
        st.markdown("**Which layer caught it**")
        by = d.loc[d["flag"], "detected_by"].value_counts().rename_axis("Detector").reset_index(name="Hours")
        st.dataframe(by, hide_index=True, width="stretch")
        st.markdown("**Recall by manipulation type**")
        st.dataframe(pd.DataFrame(
            [{"Type": k.replace("_", " "), "Caught": f"{v * 100:.0f}%"} for k, v in quality["recall_by_type"].items()]),
            hide_index=True, width="stretch")
    with right:
        st.markdown("**Verifier sampling list** (only these hours need a manual check)")
        show = d.loc[d["flag"], ["timestamp", "detected_by", "rule_reasons", "eaf_kwh_per_t", "yield", "understatement_t"]].copy()
        show["rule_reasons"] = show["rule_reasons"].apply(lambda r: "; ".join(r) if r else "statistical outlier")
        show.columns = ["Hour", "Detected by", "Reason", "kWh/t", "Yield", "Understated tCO₂e"]
        st.dataframe(show.round({"kWh/t": 0, "Yield": 3, "Understated tCO₂e": 2}), hide_index=True, width="stretch", height=300)
    st.caption("Ground-truth labels of the injected manipulations are used only to score the detector, "
               "never to train it. Detection runs two layers: EAF physics limits and an Isolation Forest "
               "on intensity ratios.")

# --------------------------------------------------------------------------- tab 3
with tab_chain:
    cfg = chain_config()
    if not cfg:
        st.info(f"No deployment found for network '{NETWORK}'. Run scripts/deploy.js first.")
    else:
        try:
            data = read_chain(cfg)
        except Exception as ex:  # network problems should not break the rest of the dashboard
            st.error(f"Could not reach the blockchain: {ex}")
            data = None
        if data:
            link = (lambda a: f"https://sepolia.etherscan.io/address/{a}") if NETWORK == "sepolia" else (lambda a: a)
            st.markdown(f"Live from **{NETWORK}**, block {data['block']:,} · "
                        f"[CarbonPassport]({link(cfg['CarbonPassport'])}) · "
                        f"[CarbonPriceLedger]({link(cfg['CarbonPriceLedger'])})")
            st.subheader("Emissions passports")
            st.dataframe(pd.DataFrame(data["passports"]), hide_index=True, width="stretch")
            st.subheader("Carbon price paid in Türkiye (deductible once)")
            st.dataframe(pd.DataFrame(data["payments"]), hide_index=True, width="stretch")
            st.caption("Each passport stores only hashes of the plant's monitoring data (evidence root) and of the "
                       "verifier's integrity report (attestation). The ledger contract rejects any deduction "
                       "beyond the remaining amount, so one Turkish carbon payment cannot be deducted twice.")
