"""
Reference parameters for VeriKarbon's AI layer.

Every number below is either taken from a cited public source or is clearly marked
ILLUSTRATIVE. All plant data generated from these parameters is SYNTHETIC.
"""

# --------------------------------------------------------------------------- emission factors
# Türkiye national grid emission factor, transmission-connected consumers, 2022.
# Source: T.C. Enerji ve Tabii Kaynaklar Bakanlığı, "2022 Üretim Tüketim Emisyon Faktörleri".
GRID_EF_T_PER_MWH = 0.442

# Natural gas, IPCC 2006 default CO2 emission factor (56,100 kg CO2/TJ).
NG_EF_KG_PER_GJ = 56.1

# Carbon (graphite electrodes, charge carbon) fully oxidised: 44/12 kg CO2 per kg C.
C_EF_KG_PER_KG = 44.0 / 12.0

# --------------------------------------------------------------------------- EAF meltshop (scrap route)
# Typical ranges from published EAF operating data (e.g. ACEEE 2013: 343-390 kWh/t,
# electrodes 1.2-1.75 kg/t, natural gas ~9.5 Nm3/t, carbon ~20 kg/t). Centre values used:
EAF_KWH_PER_T = 400.0        # electricity per tonne of billet
EAF_NG_GJ_PER_T = 0.36       # ~9.5 Nm3/t x 0.0376 GJ/Nm3 (burners / oxy-fuel)
ELECTRODE_KG_PER_T = 1.6
CHARGE_C_KG_PER_T = 18.0
METALLIC_YIELD = 0.90        # tonnes billet per tonne scrap (ILLUSTRATIVE, typical 0.88-0.92)
EAF_CAPACITY_T_PER_H = 120.0 # ILLUSTRATIVE mid-size Turkish EAF meltshop

# --------------------------------------------------------------------------- rolling mill (rebar)
RM_NG_GJ_PER_T = 1.2         # reheating furnace, ILLUSTRATIVE typical 1.0-1.5 GJ/t
RM_KWH_PER_T = 110.0         # ILLUSTRATIVE
RM_YIELD = 0.97              # tonnes rebar per tonne billet charged (ILLUSTRATIVE)

# --------------------------------------------------------------------------- physical plausibility bounds
# Used by the rule-based integrity layer. Wide on purpose: they catch physics violations,
# the ML layer catches subtler drift.
BOUNDS = {
    "eaf_kwh_per_t":     (300.0, 600.0),
    "yield":             (0.85, 0.95),
    "electrode_kg_per_t": (0.8, 3.0),
    "eaf_ng_gj_per_t":   (0.05, 1.0),
    "rm_ng_gj_per_t":    (0.6, 2.2),
}

# --------------------------------------------------------------------------- CBAM economics
# CBAM default value, Türkiye, bars and rods (CN 7213), direct emissions only,
# per Annex I of Implementing Regulation (EU) 2025/2621 as reported by GreenSutra.
# Verify against EUR-Lex before any real-world use.
CBAM_DEFAULT_T_PER_T = 2.31
DEFAULT_MARKUP = {2026: 0.10, 2027: 0.20, 2028: 0.30}  # mark-up on default values

# Approximate share of embedded emissions payable after the free-allocation adjustment
# (CBAM factor phase-in, per GreenSutra summary of Directive 2003/87/EC Art. 10a(1a)).
PAYABLE_SHARE = {2026: 0.025, 2027: 0.05, 2028: 0.10, 2029: 0.225, 2030: 0.485,
                 2031: 0.61, 2032: 0.735, 2033: 0.86, 2034: 1.00}

# CBAM certificate price, Q2 2026 (EUR per tCO2e).
CERT_PRICE_EUR = 75.28

# Under the CBAM definitive regime only DIRECT embedded emissions are priced for iron & steel;
# indirect (electricity) emissions are recorded on the passport for transparency.
