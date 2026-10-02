"""Harmonise IHME and UN IGME/WPP onto five age bands, blend them 50:50, and apply the PfPR-ACM
malaria share to the blended all-cause probability of death.

Bands: 0-27 days, 1-5 months, 6-11 months, 12-23 months, 2-4 years (IHME's GBD bands).

IGME/WPP onto the five bands, using IHME proportions only where IGME has no split (see README):
  q_all     neonatal = NMR. The 1-11 month and 1-4 year probabilities are split by IHME's share of
            the cumulative hazard H = -ln(1 - q): H_band = H_IGME x H_IHME,band / H_IHME,parent,
            q_band = 1 - exp(-H_band), which chains back exactly to the IGME parent probability.
  q_malaria CA-CODE malaria share of 1-59 month deaths, spread over the four bands in proportion
            to IHME's band malaria shares. It is scaled so that the 1-59 month total equals
            CA-CODE's share on IGME's own deaths: IGME's 1-11 month and 1-4 year deaths, each split
            between its two bands by IHME's death shares. Neonatal uses IHME's share (CA-CODE has
            no neonatal malaria category). q_malaria = share x q_all.
  pop       WPP under-1 population split by IHME's under-1 age distribution; 12-23 months = WPP
            age 1; 2-4 years = WPP ages 2-4.
Blend: 0.5 x IHME + 0.5 x IGME/WPP for countries; Nigerian states use IHME only. Mauritius and
Seychelles (no IHME) get only the IGME/WPP values that need no IHME split, and no blend.
PfPR-ACM: q_malaria = PfPR-ACM share x blended q_all.

Inputs: IHME/ihme_2023_by_age_band.csv, UN-IGME/igme_national_2023.csv,
        PfPR-ACM/pfpr_acm_shares_2023.csv, reference/*.csv
Output: output/burden_by_age_band_2023.csv (one row per location x band, 85 locations)
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
# IGME parent band (q indicator, deaths indicator) -> the two IHME bands it splits into.
PARENTS = {("CME_MRM1T11", "CME_TMM1T11"): ("1_5m", "6_11m"),
           ("CME_MRY1T4", "CME_TMY1T4"): ("12_23m", "2_4y")}
IHME_WEIGHT = 0.5


def hazard(q):
    return -np.log1p(-q)


def locations():
    c = pd.read_csv(ROOT / "reference" / "countries.csv")
    s = pd.read_csv(ROOT / "reference" / "nigeria_states.csv")
    locs = pd.concat([
        pd.DataFrame({"location_level": "country", "iso3": c["iso3"], "location_name": c["country_name"]}),
        pd.DataFrame({"location_level": "nigeria_state", "iso3": "NGA", "location_name": s["state_name"]})])
    return locs.set_index(locs["location_level"] + "|" + locs["location_name"])


def main():
    locs = locations()
    ihme = pd.read_csv(ROOT / "IHME" / "ihme_2023_by_age_band.csv")
    ihme["key"] = ihme["location_level"] + "|" + ihme["location_name"]
    u1_pop = ihme[ihme["age_band"] == "<1 year"].set_index("key")["population"].reindex(locs.index)
    b = ihme[ihme["age_band"].isin(IHME_BANDS)].assign(age_band=lambda d: d["age_band"].map(IHME_BANDS))
    ih = {m: b.pivot(index="key", columns="age_band", values=m).reindex(index=locs.index, columns=BANDS)
          for m in ["population", "q_all", "q_malaria", "malaria_fraction", "deaths_all", "deaths_malaria"]}
    countries = locs.index[locs["location_level"] == "country"]
    has_ihme = ih["q_all"].loc[countries].notna().all(axis=1)      # False for Mauritius, Seychelles
    iso = locs.loc[countries, "iso3"]

    g = pd.read_csv(ROOT / "UN-IGME" / "igme_national_2023.csv")
    def ind(code, scale=1.0):
        v = g[g["indicator_code"] == code].set_index("iso3")["value"] / scale
        return pd.Series(v.reindex(iso).to_numpy(), index=countries)

    # IGME all-cause q on the five bands (the split bands need IHME, so are blank without it).
    H = hazard(ih["q_all"].loc[countries])
    q = pd.DataFrame(index=countries, columns=BANDS, dtype=float)
    q["0_27d"] = ind("CME_MRM0", 1000)
    for (q_code, _), (a, c) in PARENTS.items():
        Hp = hazard(ind(q_code, 1000))
        split = H[a] / (H[a] + H[c])
        q[a] = -np.expm1(-Hp * split)
        q[c] = -np.expm1(-Hp * (1 - split))

    # IGME malaria share on the five bands from CA-CODE 1-59 months.
    F = ind("CACODE_FRACTION_MALARIA_M1T59", 100)
    D = ih["deaths_all"].loc[countries]
    w = pd.DataFrame(index=countries, columns=POSTNEONATAL, dtype=float)
    for (_, d_code), (a, c) in PARENTS.items():                    # IGME deaths, IHME split within
        for band in (a, c):
            w[band] = ind(d_code) * D[band] / (D[a] + D[c])
    w = w.div(w.sum(axis=1), axis=0)
    fr = ih["malaria_fraction"].loc[countries, POSTNEONATAL]
    pooled = (ih["deaths_malaria"].loc[countries, POSTNEONATAL].sum()
              / ih["deaths_all"].loc[countries, POSTNEONATAL].sum())
    no_ihme_malaria = has_ihme & (fr.sum(axis=1) == 0)             # IHME pattern undefined (Lesotho)
    pattern = fr.copy()
    pattern.loc[no_ihme_malaria] = pooled.to_numpy()
    scale = (w * pattern).sum(axis=1, min_count=1)
    assert (scale[has_ihme] > 0).all()
    f = pd.DataFrame(index=countries, columns=BANDS, dtype=float)
    f[POSTNEONATAL] = pattern.mul(F / scale, axis=0)
    f["0_27d"] = ih["malaria_fraction"].loc[countries, "0_27d"]
    assert (f[has_ihme].max(axis=1) <= 1).all(), f[f.max(axis=1) > 1]
    assert ((w * f[POSTNEONATAL]).sum(axis=1)[has_ihme] - F[has_ihme]).abs().max() < 1e-12
    for k in no_ihme_malaria[no_ihme_malaria].index:
        print(f"  NOTE {locs.at[k, 'location_name']}: IHME malaria share is 0, so CA-CODE's "
              f"{F[k]:.1%} is spread using the pooled sub-Saharan IHME age pattern")

    # WPP population on the five bands.
    wpp_pop = pd.DataFrame(index=countries, columns=BANDS, dtype=float)
    u1 = ind("DM_POP_TOT_AGE_Y0")
    for band in ["0_27d", "1_5m", "6_11m"]:
        wpp_pop[band] = u1 * ih["population"].loc[countries, band] / u1_pop.loc[countries]
    wpp_pop["12_23m"] = ind("DM_POP_TOT_AGE_Y01")
    wpp_pop["2_4y"] = ind("DM_POP_TOT_AGE_Y02") + ind("DM_POP_TOT_AGE_Y03") + ind("DM_POP_TOT_AGE_Y04")

    # Checks: the splits reproduce the IGME/WPP parents.
    for (q_code, _), (a, c) in PARENTS.items():
        gap = (1 - q[a]) * (1 - q[c]) - (1 - ind(q_code, 1000))
        assert gap[has_ihme].abs().max() < 1e-12, (q_code, gap.abs().max())
    assert (wpp_pop[["0_27d", "1_5m", "6_11m"]].sum(axis=1) - u1)[has_ihme].abs().max() < 1e-3

    acm = pd.read_csv(ROOT / "PfPR-ACM" / "pfpr_acm_shares_2023.csv")
    acm.index = acm["location_level"] + "|" + acm["location_name"] + "|" + acm["age_band"]

    rows = []
    for key, loc in locs.iterrows():
        is_country = loc["location_level"] == "country"
        weight = IHME_WEIGHT if is_country else 1.0
        if is_country and not has_ihme[key]:
            weight = np.nan
        for band in BANDS:
            r = {"year": 2023, "location_level": loc["location_level"], "iso3": loc["iso3"],
                 "location_name": loc["location_name"], "age_band": band,
                 "age_band_label": BAND_LABELS[band]}
            for m in ih:
                r[f"ihme_{m}"] = ih[m].at[key, band]
            if is_country:
                r.update(igme_q_all=q.at[key, band], igme_malaria_fraction=f.at[key, band],
                         igme_q_malaria=q.at[key, band] * f.at[key, band],
                         wpp_population=wpp_pop.at[key, band])
            r["blend_ihme_weight"] = weight
            for m, other in {"q_all": "igme_q_all", "q_malaria": "igme_q_malaria",
                             "population": "wpp_population"}.items():
                own = r[f"ihme_{m}"]
                r[f"blend_{m}"] = own if weight == 1.0 else weight * own + (1 - weight) * r[other]
            a = acm.loc[f"{key}|{band}"] if f"{key}|{band}" in acm.index else None
            r["map_pfpr_2_10_pct"] = a["pfpr_pct"] if a is not None else np.nan
            for col in ["share", "share_lower_95", "share_upper_95", "outside_central95"]:
                r[f"pfpracm_{col}"] = a[col] if a is not None else np.nan
            r["pfpracm_q_malaria"] = r["pfpracm_share"] * r["blend_q_all"]
            rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "output" / "burden_by_age_band_2023.csv", index=False)
    print(f"Wrote {len(out)} rows ({len(locs)} locations x {len(BANDS)} bands) "
          "to output/burden_by_age_band_2023.csv")


if __name__ == "__main__":
    main()
