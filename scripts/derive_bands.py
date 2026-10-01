"""Harmonise IHME and UN IGME/WPP onto five age bands, blend them 50:50, and apply the PfPR-ACM
malaria share to the blended all-cause probability of death.

Bands: 0-27 days, 1-5 months, 6-11 months, 12-23 months, 2-4 years (IHME's GBD bands).

IGME/WPP onto the five bands, using IHME proportions where IGME has no split (see README):
  q_all     neonatal = NMR. The 1-11 month and 1-4 year probabilities are split by IHME's share of
            the cumulative hazard H = -ln(1 - q): H_band = H_IGME x H_IHME,band / H_IHME,parent,
            q_band = 1 - exp(-H_band), which chains back exactly to the IGME parent probability.
  q_malaria CA-CODE malaria share of 1-59 month deaths, spread over the four bands in proportion
            to IHME's band malaria shares (scaled so the 1-59 month total matches CA-CODE when
            IGME deaths follow IHME's age distribution of deaths); neonatal uses IHME's share
            (CA-CODE has no neonatal malaria category). q_malaria = share x q_all.
  pop       WPP under-1 population split by IHME's under-1 age distribution; 12-23 months = WPP
            age 1; 2-4 years = WPP ages 2-4.
Blend: 0.5 x IHME + 0.5 x IGME/WPP for countries; Nigerian states use IHME only.
PfPR-ACM: q_malaria = PfPR-ACM share x blended q_all.

Inputs: IHME/ihme_2023_by_age_band.csv, UN-IGME/igme_national_2023.csv,
        PfPR-ACM/pfpr_acm_shares_2023.csv, MAP/map_pfpr_2023.csv
Output: output/burden_by_age_band_2023.csv (one row per location x band)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BANDS = ["0_27d", "1_5m", "6_11m", "12_23m", "2_4y"]
IHME_BANDS = {"0-27 days": "0_27d", "1-5 months": "1_5m", "6-11 months": "6_11m",
              "12-23 months": "12_23m", "2-4 years": "2_4y"}
BAND_LABELS = {"0_27d": "0-27 days", "1_5m": "1-5 months", "6_11m": "6-11 months",
               "12_23m": "12-23 months", "2_4y": "2-4 years"}
POSTNEONATAL = BANDS[1:]
IHME_WEIGHT = 0.5


def wide(df, value):
    return df.pivot(index="key", columns="age_band", values=value)[BANDS]


def hazard(q):
    return -np.log1p(-q)


def main():
    ihme = pd.read_csv(ROOT / "IHME" / "ihme_2023_by_age_band.csv")
    ihme["key"] = ihme["location_level"] + "|" + ihme["location_name"]
    locs = ihme.drop_duplicates("key").set_index("key")[["location_level", "iso3", "location_name"]]
    u1_pop = ihme[ihme["age_band"] == "<1 year"].set_index("key")["population"]
    b = ihme[ihme["age_band"].isin(IHME_BANDS)].assign(age_band=lambda d: d["age_band"].map(IHME_BANDS))
    ih = {m: wide(b, m) for m in ["population", "q_all", "q_malaria", "malaria_fraction",
                                  "deaths_all", "deaths_malaria"]}
    countries = locs.index[locs["location_level"] == "country"]
    iso = locs.loc[countries, "iso3"]

    g = pd.read_csv(ROOT / "UN-IGME" / "igme_national_2023.csv")
    def ind(code, scale=1.0):
        v = g[g["indicator_code"] == code].set_index("iso3")["value"] / scale
        return pd.Series(v.reindex(iso).to_numpy(), index=countries)

    # IGME all-cause q on the five bands.
    H = hazard(ih["q_all"].loc[countries])
    q = pd.DataFrame(index=countries, columns=BANDS, dtype=float)
    q["0_27d"] = ind("CME_MRM0", 1000)
    for parent, (a, c) in {"CME_MRM1T11": ("1_5m", "6_11m"), "CME_MRY1T4": ("12_23m", "2_4y")}.items():
        Hp = hazard(ind(parent, 1000))
        share = H[a] / (H[a] + H[c])
        q[a] = -np.expm1(-Hp * share)
        q[c] = -np.expm1(-Hp * (1 - share))

    # IGME malaria share on the five bands from CA-CODE 1-59 months.
    F = ind("CACODE_FRACTION_MALARIA_M1T59", 100)
    fr = ih["malaria_fraction"].loc[countries, POSTNEONATAL]
    w = ih["deaths_all"].loc[countries, POSTNEONATAL]
    w = w.div(w.sum(axis=1), axis=0)                     # IHME age distribution of 1-59m deaths
    pooled = (ih["deaths_malaria"].loc[countries, POSTNEONATAL].sum()
              / ih["deaths_all"].loc[countries, POSTNEONATAL].sum())
    no_ihme_malaria = fr.sum(axis=1) == 0                # IHME pattern undefined (Lesotho)
    pattern = fr.copy()
    pattern.loc[no_ihme_malaria] = pooled.to_numpy()
    scale = (w * pattern).sum(axis=1)
    f = pd.DataFrame(index=countries, columns=BANDS, dtype=float)
    assert (scale > 0).all()
    f[POSTNEONATAL] = pattern.mul(F / scale, axis=0)
    f["0_27d"] = ih["malaria_fraction"].loc[countries, "0_27d"]
    assert (f.max(axis=1) <= 1).all(), f[f.max(axis=1) > 1]
    for k in locs.loc[no_ihme_malaria[no_ihme_malaria].index, "location_name"]:
        print(f"  NOTE {k}: IHME malaria share is 0, so CA-CODE's {F[no_ihme_malaria].max():.1%} "
              "is spread using the pooled sub-Saharan IHME age pattern")

    # WPP population on the five bands.
    wpp_pop = pd.DataFrame(index=countries, columns=BANDS, dtype=float)
    u1 = ind("DM_POP_TOT_AGE_Y0")
    for band in ["0_27d", "1_5m", "6_11m"]:
        wpp_pop[band] = u1 * ih["population"].loc[countries, band] / u1_pop.loc[countries]
    wpp_pop["12_23m"] = ind("DM_POP_TOT_AGE_Y01")
    wpp_pop["2_4y"] = ind("DM_POP_TOT_AGE_Y02") + ind("DM_POP_TOT_AGE_Y03") + ind("DM_POP_TOT_AGE_Y04")

    # Checks: the splits reproduce the IGME/WPP parents.
    chk = {"1-11m": (1 - q["1_5m"]) * (1 - q["6_11m"]) - (1 - ind("CME_MRM1T11", 1000)),
           "1-4y": (1 - q["12_23m"]) * (1 - q["2_4y"]) - (1 - ind("CME_MRY1T4", 1000)),
           "pop<1": wpp_pop[["0_27d", "1_5m", "6_11m"]].sum(axis=1) - u1}
    for name, gap in chk.items():
        assert gap.abs().max() < 1e-9 * (1 if name != "pop<1" else 1e6), (name, gap.abs().max())
    implied = (ih["deaths_all"].loc[countries, POSTNEONATAL].sum(axis=1).pipe(lambda d: w.mul(d, axis=0))
               * f[POSTNEONATAL]).sum(axis=1) / ih["deaths_all"].loc[countries, POSTNEONATAL].sum(axis=1)
    assert (implied - F).abs().max() < 1e-9, "CA-CODE 1-59m malaria share not reproduced"

    rows = []
    for key, loc in locs.iterrows():
        is_country = loc["location_level"] == "country"
        weight = IHME_WEIGHT if is_country else 1.0
        for band in BANDS:
            r = {"location_level": loc["location_level"], "iso3": loc["iso3"],
                 "location_name": loc["location_name"], "age_band": band,
                 "age_band_label": BAND_LABELS[band]}
            for m in ih:
                r[f"ihme_{m}"] = ih[m].at[key, band]
            if is_country:
                r.update(igme_q_all=q.at[key, band], igme_malaria_fraction=f.at[key, band],
                         igme_q_malaria=q.at[key, band] * f.at[key, band],
                         wpp_population=wpp_pop.at[key, band])
            r["blend_ihme_weight"] = weight
            igme = {"q_all": r.get("igme_q_all"), "q_malaria": r.get("igme_q_malaria"),
                    "population": r.get("wpp_population")}
            for m, other in igme.items():
                own = r[f"ihme_{m}"]
                r[f"blend_{m}"] = own if weight == 1.0 else weight * own + (1 - weight) * other
            rows.append(r)
    out = pd.DataFrame(rows)

    acm = pd.read_csv(ROOT / "PfPR-ACM" / "pfpr_acm_shares_2023.csv")
    acm = acm.rename(columns={"share": "pfpracm_share", "share_lower_95": "pfpracm_share_lower_95",
                              "share_upper_95": "pfpracm_share_upper_95",
                              "pfpr_pct": "map_pfpr_2_10_pct"})
    keys = ["location_level", "iso3", "location_name", "age_band"]
    out = out.merge(acm[keys + ["map_pfpr_2_10_pct", "pfpracm_share", "pfpracm_share_lower_95",
                                "pfpracm_share_upper_95"]], on=keys, how="left")
    out["pfpracm_q_malaria"] = out["pfpracm_share"] * out["blend_q_all"]
    out.insert(0, "year", 2023)
    out.to_csv(ROOT / "output" / "burden_by_age_band_2023.csv", index=False)
    n_locs = len(out.drop_duplicates(["location_level", "location_name"]))
    print(f"Wrote {len(out)} rows ({n_locs} locations x {len(BANDS)} bands) "
          "to output/burden_by_age_band_2023.csv")


if __name__ == "__main__":
    main()
