"""Merge IHME, UN IGME (+ UN WPP), MAP and WorldPop 2023 inputs into one wide CSV with one row
per sub-Saharan African country and one row per Nigerian state, plus a data dictionary.

Inputs (produced by the other scripts in scripts/):
  IHME/ihme_2023_by_age_band.csv, UN-IGME/igme_national_2023.csv,
  UN-IGME/igme_nigeria_states.csv, MAP/map_pfpr_2023.csv, WorldPop/worldpop_u5_2023.csv
Outputs:
  output/malaria_burden_inputs_2023.csv
  output/data_dictionary.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"

BAND_CODES = {"0-27 days": "0_27d", "1-5 months": "1_5m", "6-11 months": "6_11m",
              "1-11 months": "1_11m", "<1 year": "u1", "12-23 months": "12_23m",
              "2 years": "2y", "3 years": "3y", "4 years": "4y", "2-4 years": "2_4y",
              "1-4 years": "1_4y", "<5 years": "u5"}
BAND_LABELS = {v: k for k, v in BAND_CODES.items()}
BAND_LABELS.update({"0_27d": "0-27 days (neonatal)", "1_11m": "1-11 months (post-neonatal)",
                    "u1": "under 1 year", "u5": "under 5 years", "12_23m": "12-23 months (age 1)",
                    "2y": "age 2", "3y": "age 3", "4y": "age 4"})

IHME_METRICS = {
    "population": ("ihme_pop", "Population aged {band}", "persons"),
    "q_all": ("ihme_q_all", "Probability of death from all causes within {band}, conditional "
              "on survival to the start of the band", "probability (0-1)"),
    "q_malaria": ("ihme_q_malaria", "Probability of death from malaria within {band}, "
                  "conditional on survival to the start of the band", "probability (0-1)"),
    "deaths_all": ("ihme_deaths_all", "All-cause deaths at age {band} (derived; see README)",
                   "deaths per year"),
    "deaths_malaria": ("ihme_deaths_malaria", "Malaria deaths at age {band} (derived; see "
                       "README)", "deaths per year"),
    "malaria_fraction": ("ihme_malaria_fraction", "Share of all-cause deaths at age {band} "
                         "attributed to malaria (derived as q_malaria / q_all)", "proportion (0-1)"),
}

IGME_CODES = {
    "CME_MRM0": ("igme_q_0_27d", "Neonatal mortality: probability of dying in the first 28 days",
                 "probability (0-1); IGME publishes per 1,000 live births"),
    "CME_MRM1T11": ("igme_q_1_11m", "Post-neonatal mortality: probability of dying between 1 "
                    "and 11 months, conditional on survival to 1 month",
                    "probability (0-1); IGME publishes per 1,000 children aged 1 month"),
    "CME_MRY0": ("igme_q_u1", "Infant mortality: probability of dying before age 1",
                 "probability (0-1); IGME publishes per 1,000 live births"),
    "CME_MRY1T4": ("igme_q_1_4y", "Child mortality: probability of dying between exact ages 1 "
                   "and 5, conditional on survival to age 1 (4q1)",
                   "probability (0-1); IGME publishes per 1,000 children aged 1"),
    "CME_MRY0T4": ("igme_q_u5", "Under-five mortality: probability of dying before age 5",
                   "probability (0-1); IGME publishes per 1,000 live births"),
    "CME_TMM0": ("igme_deaths_0_27d", "Neonatal deaths (0-27 days)", "deaths per year"),
    "CME_TMM1T11": ("igme_deaths_1_11m", "Post-neonatal deaths (1-11 months)", "deaths per year"),
    "CME_TMY0": ("igme_deaths_u1", "Infant deaths (under 1 year)", "deaths per year"),
    "CME_TMY1T4": ("igme_deaths_1_4y", "Child deaths (ages 1-4)", "deaths per year"),
    "CME_TMY0T4": ("igme_deaths_u5", "Under-five deaths", "deaths per year"),
}
WPP_CODES = {
    "DM_BRTS": ("wpp_live_births", "Live births (UNICEF DM dataflow; see README caution for Togo)"),
    "DM_POP_TOT_AGE_Y0": ("wpp_pop_u1", "Population under 1 year"),
    "DM_POP_TOT_AGE_Y01": ("wpp_pop_12_23m", "Population age 1"),
    "DM_POP_TOT_AGE_Y02": ("wpp_pop_2y", "Population age 2"),
    "DM_POP_TOT_AGE_Y03": ("wpp_pop_3y", "Population age 3"),
    "DM_POP_TOT_AGE_Y04": ("wpp_pop_4y", "Population age 4"),
}
SINGLE_AGES = ["wpp_pop_u1", "wpp_pop_12_23m", "wpp_pop_2y", "wpp_pop_3y", "wpp_pop_4y"]

SRC_IHME = "IHME GBD 2023 (IHME/ downloads)"
SRC_IGME = "UN IGME 2025 round (released March 2026), UNICEF SDMX API dataflow UNICEF,CME,1.0"
SRC_IGME_SUB = ("UN IGME 2021-round subnational estimates (estimates to 2021), UNICEF SDMX API "
                "dataflow UNICEF,CME_SUBNATIONAL,1.0")
SRC_WPP = "UN World Population Prospects 2024 (as used by UN IGME), via UNICEF SDMX API"
SRC_MAP = "Malaria Atlas Project, 202608 release, admin-0/admin-1 aggregates"
SRC_WP = "WorldPop Global2 R2025A, constrained, UN-adjusted, 1 km (DOI 10.5258/SOTON/WP00842)"


def locations():
    c = pd.read_csv(ROOT / "reference" / "countries.csv")
    s = pd.read_csv(ROOT / "reference" / "nigeria_states.csv")
    countries = pd.DataFrame({"location_level": "country", "iso3": c["iso3"],
                              "country_name": c["country_name"], "state_name": pd.NA,
                              "gbd_location_id": c["gbd_location_id"], "igme_code": c["iso3"]})
    states = pd.DataFrame({"location_level": "nigeria_state", "iso3": "NGA",
                           "country_name": "Nigeria", "state_name": s["state_name"],
                           "gbd_location_id": s["gbd_location_id"], "igme_code": s["igme_code"]})
    return pd.concat([countries.sort_values("country_name"), states.sort_values("state_name")],
                     ignore_index=True)


def ihme_wide(dictionary):
    d = pd.read_csv(ROOT / "IHME" / "ihme_2023_by_age_band.csv")
    births = d[d["age_band"] == "live births"].set_index("gbd_location_id")[
        ["live_births", "live_births_lower", "live_births_upper"]].add_prefix("ihme_")
    for col, desc in [("ihme_live_births", "Live births (all maternal ages)"),
                      ("ihme_live_births_lower", "Live births, lower 95% UI"),
                      ("ihme_live_births_upper", "Live births, upper 95% UI")]:
        dictionary.append((col, SRC_IHME, desc, "births per year"))
    parts = [births]
    for metric, (prefix, template, unit) in IHME_METRICS.items():
        w = d[d["age_band"] != "live births"].pivot(index="gbd_location_id", columns="age_band",
                                                    values=metric)
        w = w[[b for b in BAND_CODES if b in w.columns and w[b].notna().any()]]
        w.columns = [f"{prefix}_{BAND_CODES[b]}" for b in w.columns]
        for col in w.columns:
            band = col[len(prefix) + 1:]
            desc = template.format(band=BAND_LABELS[band])
            if metric == "q_malaria" and band in ("1_11m", "1_4y"):
                desc += " (derived as q_all x malaria fraction; see README)"
            elif metric == "q_all" and band in ("1_11m", "1_4y"):
                desc += " (derived by chaining component bands; see README)"
            dictionary.append((col, SRC_IHME, desc, unit))
        parts.append(w)
    return pd.concat(parts, axis=1).reset_index()


def igme_wide(dictionary):
    d = pd.read_csv(ROOT / "UN-IGME" / "igme_national_2023.csv")
    cols = {}
    for code, (name, desc, unit) in IGME_CODES.items():
        r = d[d["indicator_code"] == code].set_index("iso3")
        scale = 1000.0 if name.startswith("igme_q_") else 1.0
        cols[name] = r["value"] / scale
        cols[f"{name}_lower"] = r["lower"] / scale
        cols[f"{name}_upper"] = r["upper"] / scale
        dictionary.append((name, SRC_IGME, desc, unit))
        dictionary.append((f"{name}_lower", SRC_IGME, f"{desc}, lower 90% uncertainty bound", unit))
        dictionary.append((f"{name}_upper", SRC_IGME, f"{desc}, upper 90% uncertainty bound", unit))
    for code, (name, desc) in WPP_CODES.items():
        cols[name] = d[d["indicator_code"] == code].set_index("iso3")["value"]
        unit = "births per year" if name == "wpp_live_births" else "persons"
        dictionary.append((name, SRC_WPP, desc, unit))
    out = pd.DataFrame(cols)

    # Under-5 population from the single-age series. The DM dataflow's own DM_POP_U5 disagrees
    # with it for Togo (~15% lower); everywhere else they agree to rounding.
    out["wpp_pop_u5"] = out[SINGLE_AGES].sum(axis=1)
    dictionary.append(("wpp_pop_u5", SRC_WPP, "Population under 5 years (sum of single ages 0-4)",
                       "persons"))
    dm_u5 = d[d["indicator_code"] == "DM_POP_U5"].set_index("iso3")["value"]
    gap = (dm_u5 / out["wpp_pop_u5"] - 1).abs()
    for iso3 in gap[gap > 0.005].index:
        print(f"  CAUTION {iso3}: DM_POP_U5 {dm_u5[iso3]:,.0f} vs single-age sum "
              f"{out.at[iso3, 'wpp_pop_u5']:,.0f}; using the single-age sum")
    # IGME deaths should equal births x q; flag countries where the DM births disagree.
    implied = out["igme_deaths_0_27d"] / out["igme_q_0_27d"]
    gap = (out["wpp_live_births"] / implied - 1).abs()
    for iso3 in gap[gap > 0.03].index:
        print(f"  CAUTION {iso3}: wpp_live_births {out.at[iso3, 'wpp_live_births']:,.0f} vs "
              f"births implied by IGME neonatal deaths / NMR {implied[iso3]:,.0f}")
    return out.rename_axis("igme_code").reset_index()


def igme_states_wide(dictionary):
    d = pd.read_csv(ROOT / "UN-IGME" / "igme_nigeria_states.csv")
    year = int(d["year"].max())
    d = d[d["year"] == year]
    cols = {}
    for code, name, desc in [("MRY0T4", f"igme_state_q_u5_{year}", "Under-five mortality"),
                             ("MRM0", f"igme_state_q_0_27d_{year}", "Neonatal mortality")]:
        r = d[d["indicator_code"] == code].set_index("igme_code")
        for suffix, field in [("", "value"), ("_lower", "lower"), ("_upper", "upper")]:
            cols[name + suffix] = r[field] / 1000.0
            bound = {"": "", "_lower": ", lower 90% uncertainty bound",
                     "_upper": ", upper 90% uncertainty bound"}[suffix]
            dictionary.append((name + suffix, SRC_IGME_SUB,
                               f"{desc} probability in {year} (latest year IGME publishes for "
                               f"Nigerian states; NOT 2023, and from an earlier estimation round "
                               f"than the national igme_ columns){bound}", "probability (0-1)"))
    return pd.DataFrame(cols).rename_axis("igme_code").reset_index()


def map_wide(dictionary):
    d = pd.read_csv(ROOT / "MAP" / "map_pfpr_2023.csv")
    d["key"] = d["location_level"] + "|" + d["location_name"]
    for col, desc in [("pfpr_2_10", "P. falciparum parasite rate in children aged 2-10 "
                       "(population-weighted mean over the unit)"),
                      ("pfpr_2_10_lower", "PfPR2-10, lower 95% credible interval"),
                      ("pfpr_2_10_upper", "PfPR2-10, upper 95% credible interval")]:
        dictionary.append(("map_" + col, SRC_MAP, desc, "proportion (0-1)"))
    out = d.set_index("key")[["map_admin_id", "pfpr_2_10", "pfpr_2_10_lower", "pfpr_2_10_upper"]]
    out["map_admin_id"] = out["map_admin_id"].astype("Int64")
    return out.rename(columns=lambda c: c if c == "map_admin_id" else "map_" + c)


def worldpop_wide(dictionary):
    d = pd.read_csv(ROOT / "WorldPop" / "worldpop_u5_2023.csv")
    d["key"] = d["location_level"] + "|" + d["location_name"]
    names = {"pop_0_11_months": ("worldpop_pop_u1", "Population aged 0-11 months"),
             "pop_1_4_years": ("worldpop_pop_1_4y", "Population aged 1-4 years"),
             "pop_under_5": ("worldpop_pop_u5", "Population under 5 years")}
    for col, (name, desc) in names.items():
        dictionary.append((name, SRC_WP, desc + " (sum of grid cells over the unit; Nigerian "
                           "states use MAP 202403 admin-1 boundaries; WorldPop applies one "
                           "national under-1 share to every grid cell)", "persons"))
    return d.set_index("key")[list(names)].rename(columns={k: v[0] for k, v in names.items()})


def main():
    OUT.mkdir(exist_ok=True)
    dictionary = [
        ("location_level", "", "'country' or 'nigeria_state'", ""),
        ("iso3", "", "ISO 3166-1 alpha-3 code of the country (NGA for Nigerian states)", ""),
        ("country_name", "", "Country name", ""),
        ("state_name", "", "Nigerian state name (blank for country rows)", ""),
        ("gbd_location_id", SRC_IHME, "GBD location_id (join key for IHME data)", ""),
        ("igme_code", SRC_IGME, "UN IGME / UNICEF area code (ISO3, or NGA-k_1 for states)", ""),
        ("map_admin_id", SRC_MAP, "MAP admin-1 unit ID (Nigerian states only)", ""),
    ]
    df = locations()
    df["key"] = df["location_level"] + "|" + df["state_name"].fillna(df["country_name"])
    df = df.merge(ihme_wide(dictionary), on="gbd_location_id", how="left")
    df = df.merge(igme_wide(dictionary), on="igme_code", how="left")
    df = df.merge(igme_states_wide(dictionary), on="igme_code", how="left")
    df = df.merge(map_wide(dictionary), left_on="key", right_index=True, how="left")
    df = df.merge(worldpop_wide(dictionary), left_on="key", right_index=True, how="left")
    df = df.drop(columns="key")

    order = [c[0] for c in dictionary]
    assert sorted(order) == sorted(df.columns), set(order) ^ set(df.columns)
    df = df[order]
    df.insert(4, "year", 2023)
    dictionary.insert(4, ("year", "", "Reference year of the estimates (see igme_state_* "
                          "columns for the one exception)", ""))
    assert len(df) == 85 and not df.duplicated(["location_level", "iso3", "state_name"]).any()

    df.to_csv(OUT / "malaria_burden_inputs_2023.csv", index=False)
    pd.DataFrame(dictionary, columns=["column", "source", "description", "unit"]).to_csv(
        OUT / "data_dictionary.csv", index=False)
    print(f"Wrote {len(df)} rows x {df.shape[1]} columns to output/malaria_burden_inputs_2023.csv")


if __name__ == "__main__":
    main()
