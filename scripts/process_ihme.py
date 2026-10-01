"""Tidy the IHME GBD 2023 downloads in IHME/ and derive death counts and malaria fractions.

IHME/ downloads hold population, live births and probability of death (q) for All causes and
Malaria, but no death counts. Derivations (see README "Methods"):

  annual death rate      m = -ln(1 - q) / n          (n = band width in years; constant hazard)
  all-cause deaths       D = population x m
  malaria fraction       f = q_malaria / q_all        (= malaria deaths / all-cause deaths
                                                       under proportional hazards in the band)
  malaria deaths         D_malaria = D x f

Composite bands (1-11 months, <1 year, 1-4 years, <5 years) sum deaths and population over the
component bands and chain all-cause q as 1 - prod(1 - q). Cause-specific q does not chain, so
composite malaria q = f x q_all, except for <1 and <5 where IHME's own published malaria q is used.

Output: IHME/ihme_2023_by_age_band.csv, one row per location x age band.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IHME = ROOT / "IHME"

# Component bands with q in the download, and their widths in years. GBD's "1-5 months" runs
# from 28 days to 6 months, so the three infant bands sum to exactly one year.
BANDS = {
    "0-27 days": ("<28 days", 28 / 365.25),
    "1-5 months": ("1-5 months", 0.5 - 28 / 365.25),
    "6-11 months": ("6-11 months", 6 / 12),
    "12-23 months": ("12-23 months", 1.0),
    "2-4 years": ("2-4 years", 3.0),
}
COMPOSITES = {
    "1-11 months": ["1-5 months", "6-11 months"],
    "<1 year": ["0-27 days", "1-5 months", "6-11 months"],
    "1-4 years": ["12-23 months", "2-4 years"],
    "<5 years": ["0-27 days", "1-5 months", "6-11 months", "12-23 months", "2-4 years"],
}
# Population-only single-year ages (no q published for these).
POP_ONLY = {"2": "2 years", "3": "3 years", "4": "4 years"}


def load(name):
    return pd.read_csv(IHME / f"IHME-GBD_2023_DATA-{name}.csv", encoding="utf-8")


def locations():
    countries = pd.read_csv(ROOT / "reference" / "countries.csv")
    states = pd.read_csv(ROOT / "reference" / "nigeria_states.csv")
    return pd.concat([
        pd.DataFrame({"gbd_location_id": countries["gbd_location_id"], "iso3": countries["iso3"],
                      "location_name": countries["country_name"], "location_level": "country"}),
        pd.DataFrame({"gbd_location_id": states["gbd_location_id"], "iso3": "NGA",
                      "location_name": states["state_name"], "location_level": "nigeria_state"}),
    ])


def main():
    locs = locations()
    pop = load("population").rename(columns={"location_id": "gbd_location_id"})
    q = load("probability-death").rename(columns={"location_id": "gbd_location_id"})
    births = load("live-births").rename(columns={"location_id": "gbd_location_id"})

    rows = []
    for band, (age_name, n) in BANDS.items():
        p = pop[pop["age_name"] == age_name].set_index("gbd_location_id")
        qa = q[(q["age_name"] == age_name) & (q["cause_name"] == "All causes")].set_index("gbd_location_id")["val"]
        qm = q[(q["age_name"] == age_name) & (q["cause_name"] == "Malaria")].set_index("gbd_location_id")["val"]
        df = pd.DataFrame({"population": p["val"], "population_lower": p["lower"],
                           "population_upper": p["upper"], "q_all": qa, "q_malaria": qm})
        df["deaths_all"] = df["population"] * -np.log1p(-df["q_all"]) / n
        df["malaria_fraction"] = df["q_malaria"] / df["q_all"]
        df["deaths_malaria"] = df["deaths_all"] * df["malaria_fraction"]
        rows.append(df.assign(age_band=band, band_width_years=n))
    comp = pd.concat(rows).reset_index()

    for band, parts in COMPOSITES.items():
        g = comp[comp["age_band"].isin(parts)].groupby("gbd_location_id")
        df = g[["population", "deaths_all", "deaths_malaria"]].sum()
        # Population bounds are not additive; leave them blank for composites.
        df["q_all"] = 1 - g["q_all"].apply(lambda s: np.prod(1 - s))
        df["malaria_fraction"] = df["deaths_malaria"] / df["deaths_all"]
        df["q_malaria"] = df["q_all"] * df["malaria_fraction"]
        df["band_width_years"] = comp[comp["age_band"].isin(parts)].drop_duplicates("age_band")["band_width_years"].sum()
        if band in ("<1 year", "<5 years"):
            # Chained all-cause q should reproduce IHME's own value; use IHME's malaria q directly.
            ref = q[(q["age_name"] == band) & (q["cause_name"] == "All causes")].set_index("gbd_location_id")["val"]
            gap = (df["q_all"] - ref.reindex(df.index)).abs().max()
            assert gap < 1e-6, f"{band}: chained q differs from IHME by {gap}"
            ref_mal = q[(q["age_name"] == band) & (q["cause_name"] == "Malaria")].set_index("gbd_location_id")["val"]
            df["q_malaria"] = ref_mal.reindex(df.index)
        rows.append(df.assign(age_band=band).reset_index())

    for age_name, band in POP_ONLY.items():
        p = pop[pop["age_name"] == age_name]
        rows.append(pd.DataFrame({"gbd_location_id": p["gbd_location_id"], "population": p["val"],
                                  "population_lower": p["lower"], "population_upper": p["upper"],
                                  "age_band": band}))

    b = births[births["age_name"] == "10-54 years"]  # all maternal ages
    rows.append(pd.DataFrame({"gbd_location_id": b["gbd_location_id"], "live_births": b["val"],
                              "live_births_lower": b["lower"], "live_births_upper": b["upper"],
                              "age_band": "live births"}))

    out = pd.concat([r.reset_index(drop=True) if "gbd_location_id" in r.columns else r.reset_index()
                     for r in rows], ignore_index=True)
    out = locs.merge(out, on="gbd_location_id", how="inner")  # drops stray aggregates in download
    order = ["live births", "0-27 days", "1-5 months", "6-11 months", "1-11 months", "<1 year",
             "12-23 months", "2 years", "3 years", "4 years", "2-4 years", "1-4 years", "<5 years"]
    out["age_band"] = pd.Categorical(out["age_band"], order, ordered=True)
    cols = ["location_level", "iso3", "location_name", "gbd_location_id", "age_band",
            "band_width_years", "live_births", "live_births_lower", "live_births_upper",
            "population", "population_lower", "population_upper", "q_all", "q_malaria",
            "deaths_all", "malaria_fraction", "deaths_malaria"]
    out = out[cols].sort_values(["location_level", "location_name", "age_band"])
    out.insert(0, "source", "IHME GBD 2023")
    out.insert(1, "year", 2023)
    out.to_csv(IHME / "ihme_2023_by_age_band.csv", index=False)
    n_locs = out["gbd_location_id"].nunique()
    print(f"Wrote {len(out)} rows for {n_locs} locations to IHME/ihme_2023_by_age_band.csv")


if __name__ == "__main__":
    main()
