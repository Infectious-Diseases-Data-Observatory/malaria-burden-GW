"""Build the wide files: one row per sub-Saharan African country and per Nigerian state.

The full file has the blended (IHME : IGME/WPP, 50:50) and PfPR-ACM estimates first, then the
source values on the five age bands, then the sources as published. The main file is a copy of
the headline columns of the full file (MAIN_COLUMNS). Each has a data dictionary.

Age bands (column suffixes): 0_27d, 1_5m, 6_11m, 12_23m, 2_4y.

Inputs (produced by the other scripts in scripts/):
  output/burden_by_age_band_2023.csv (derive_bands.py), IHME/ihme_2023_by_age_band.csv,
  UN-IGME/igme_national_2023.csv, MAP/map_pfpr_2023.csv, WorldPop/worldpop_u5_2023.csv
Outputs:
  output/malaria_burden_main_2023.csv, output/malaria_burden_main_2023_dictionary.csv
  output/malaria_burden_inputs_2023.csv, output/data_dictionary.csv (full)
"""
from pathlib import Path

import pandas as pd

from derive_bands import INDIRECT_MULTIPLIER

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
BANDS = ["0_27d", "1_5m", "6_11m", "12_23m", "2_4y"]
LABEL = {"0_27d": "0-27 days (neonatal)", "1_5m": "1-5 months", "6_11m": "6-11 months",
         "12_23m": "12-23 months", "2_4y": "2-4 years", "u5": "under 5 years"}
Q_DESC = "within {band}, conditional on survival to the start of the band"
IHME_WEIGHT = 0.5
MAIN_IDS = ["location_level", "iso3", "country_name", "state_name"]
MAIN_COLUMNS = ["blend_live_births", "blend_deaths_all_u5", "blend_deaths_all_{b}",
                "blend_q_all_{b}", "blend_q_malaria_adj_{b}", "blend_pop_{b}",
                "blend_malaria_fraction_adj_{b}", "map_pfpr_2_10", "pfpracm_share_{b}",
                "pfpracm_share_u5", "combined_q_malaria_{b}"]

SRC_BLEND = "Derived: 50:50 IHME and UN IGME/WPP (Nigerian states: IHME only); see README"
SRC_ACM = ("Derived: in-house PfPR-ACM model (MIS/DHS project, primary v9) at MAP 2023 PfPR2-10; "
           "see README and PfPR-ACM/provenance.json")
SRC_COMBINED = ("Derived: 50:50 indirect-adjusted blended (IHME : IGME) and PfPR-ACM malaria "
                "probability; see README")
SRC_IHME = "IHME GBD 2023 (IHME/ downloads)"
SRC_IGME5 = "Derived from UN IGME 2025 round and CA-CODE 2026, split with IHME proportions; see README"
SRC_IGME = "UN IGME 2025 round (released March 2026), UNICEF SDMX API dataflow UNICEF,CME,1.0"
SRC_CACODE = "CA-CODE 2026 (WHO/UNICEF, with UN IGME), UNICEF SDMX API dataflow UNICEF,CME_CAUSE_OF_DEATH,1.0"
SRC_WPP = "UN World Population Prospects 2024 (as used by UN IGME), via UNICEF SDMX API"
SRC_MAP = "Malaria Atlas Project, 202608 release, admin-0/admin-1 aggregates"
SRC_WP = "WorldPop Global2 R2025A, constrained, UN-adjusted, 1 km (DOI 10.5258/SOTON/WP00842)"


class Columns:
    """Collects columns and their dictionary entries in output order."""
    def __init__(self, index):
        self.index = index
        self.values = {}
        self.dictionary = []

    def add(self, name, values, source, description, unit):
        assert name not in self.values, name
        self.values[name] = values
        self.dictionary.append((name, source, description, unit))

    @property
    def data(self):
        return pd.DataFrame(self.values, index=self.index)


def locations():
    c = pd.read_csv(ROOT / "reference" / "countries.csv")
    c = c[c["in_outputs"]]          # Lesotho, Mauritius and Seychelles are left out
    s = pd.read_csv(ROOT / "reference" / "nigeria_states.csv")
    countries = pd.DataFrame({"location_level": "country", "iso3": c["iso3"],
                              "country_name": c["country_name"], "state_name": pd.NA,
                              "gbd_location_id": c["gbd_location_id"], "igme_code": c["iso3"]})
    states = pd.DataFrame({"location_level": "nigeria_state", "iso3": "NGA",
                           "country_name": "Nigeria", "state_name": s["state_name"],
                           "gbd_location_id": s["gbd_location_id"], "igme_code": s["igme_code"]})
    df = pd.concat([countries.sort_values("country_name"), states.sort_values("state_name")],
                   ignore_index=True)
    df.index = df["location_level"] + "|" + df["state_name"].fillna(df["country_name"])
    return df


def igme_indicators(index, iso3):
    g = pd.read_csv(ROOT / "UN-IGME" / "igme_national_2023.csv")
    def get(code, field="value", scale=1.0):
        v = g[g["indicator_code"] == code].set_index("iso3")[field] / scale
        return pd.Series(v.reindex(iso3).to_numpy(), index=index)
    return get


def main():
    OUT.mkdir(exist_ok=True)
    locs = locations()
    is_country = locs["location_level"] == "country"
    iso3 = locs["iso3"].where(is_country)
    cols = Columns(locs.index)
    for name, desc in [("location_level", "'country' or 'nigeria_state'"),
                       ("iso3", "ISO 3166-1 alpha-3 country code (NGA for Nigerian states)"),
                       ("country_name", "Country name"),
                       ("state_name", "Nigerian state name (blank for country rows)")]:
        cols.add(name, locs[name], "", desc, "")
    cols.add("year", 2023, "", "Reference year of all estimates", "")
    cols.add("gbd_location_id", locs["gbd_location_id"], SRC_IHME, "GBD location_id", "")
    cols.add("igme_code", locs["igme_code"], SRC_IGME, "UN IGME / UNICEF area code", "")
    mp = pd.read_csv(ROOT / "MAP" / "map_pfpr_2023.csv")
    mp.index = mp["location_level"] + "|" + mp["location_name"]
    cols.add("map_admin_id", mp["map_admin_id"].reindex(locs.index).astype("Int64"), SRC_MAP,
             "MAP admin-1 unit ID (Nigerian states only)", "")

    long = pd.read_csv(ROOT / "output" / "burden_by_age_band_2023.csv")
    long.index = long["location_level"] + "|" + long["location_name"]
    def band(metric):
        w = long.pivot_table(index=long.index, columns="age_band", values=metric, dropna=False)
        return w.reindex(index=locs.index, columns=BANDS)

    igme = igme_indicators(locs.index, iso3)
    ihme = pd.read_csv(ROOT / "IHME" / "ihme_2023_by_age_band.csv")
    ihme.index = ihme["location_level"] + "|" + ihme["location_name"]
    ihme_births = ihme[ihme["age_band"] == "live births"].reindex(locs.index)
    ihme_u5 = ihme[ihme["age_band"] == "<5 years"].reindex(locs.index)
    wpp_births = igme("DM_BRTS")

    # --- Blended estimates -------------------------------------------------------------------
    weight = band("blend_ihme_weight")["0_27d"]
    cols.add("blend_ihme_weight", weight, SRC_BLEND, "Weight on IHME in the blended columns (0.5 "
             "for countries; 1.0 for Nigerian states, which use IHME only)", "weight (0-1)")
    births = ihme_births["live_births"].where(~is_country,
                                              IHME_WEIGHT * ihme_births["live_births"] + (1 - IHME_WEIGHT) * wpp_births)
    cols.add("blend_live_births", births.where(weight.notna()), SRC_BLEND,
             "Live births, blended IHME and WPP", "births per year")
    for metric, prefix, desc, unit in [
            ("blend_population", "blend_pop", "Population aged {band}, blended", "persons"),
            ("blend_q_all", "blend_q_all", "Probability of death from all causes " + Q_DESC +
             ", blended", "probability (0-1)"),
            ("blend_q_malaria", "blend_q_malaria", "Probability of death from malaria " + Q_DESC +
             ", blended (IHME malaria q and CA-CODE-based IGME malaria q)", "probability (0-1)"),
            ("blend_malaria_fraction", "blend_malaria_fraction", "Share of all-cause deaths at "
             "{band} assigned to malaria, blended (average of the IHME and CA-CODE-based IGME "
             "shares)", "proportion (0-1)"),
            ("blend_q_malaria_adj", "blend_q_malaria_adj", "Probability of death from malaria " +
             Q_DESC + ", blended, including indirect malaria deaths: {multiplier} x "
             "blend_q_malaria", "probability (0-1)"),
            ("blend_malaria_fraction_adj", "blend_malaria_fraction_adj", "Share of all-cause "
             "deaths at {band} due to malaria, blended, including indirect malaria deaths: "
             "{multiplier} x blend_malaria_fraction", "proportion (0-1)")]:
        w = band(metric)
        for b in BANDS:
            cols.add(f"{prefix}_{b}", w[b], SRC_BLEND,
                     desc.format(band=LABEL[b], multiplier=INDIRECT_MULTIPLIER), unit)
    blend_deaths = band("blend_deaths_all")
    cols.add("blend_deaths_all_u5", blend_deaths.sum(axis=1, min_count=len(BANDS)), SRC_BLEND,
             "All-cause deaths under 5 years, blended (sum of the five bands)", "deaths per year")
    for b in BANDS:
        cols.add(f"blend_deaths_all_{b}", blend_deaths[b], SRC_BLEND, f"All-cause deaths at "
                 f"{LABEL[b]}, blended (IHME derived deaths and IGME deaths split by IHME death "
                 "shares)", "deaths per year")

    # --- PfPR-ACM ----------------------------------------------------------------------------
    share, lo, hi = band("pfpracm_share"), band("pfpracm_share_lower_95"), band("pfpracm_share_upper_95")
    for b in BANDS:
        cols.add(f"pfpracm_share_{b}", share[b], SRC_ACM, f"Share of all-cause deaths at {LABEL[b]} "
                 "attributable to malaria (deaths that would not occur at PfPR 0, including indirect "
                 "deaths)" + (": mean of the model's 24-35, 36-47 and 48-59 month bands" if b == "2_4y"
                              else ""), "proportion")
        if b != "2_4y":
            cols.add(f"pfpracm_share_{b}_lower", lo[b], SRC_ACM, f"PfPR-ACM share at {LABEL[b]}, "
                     "lower 95% interval (model hazard-ratio uncertainty only)", "proportion")
            cols.add(f"pfpracm_share_{b}_upper", hi[b], SRC_ACM, f"PfPR-ACM share at {LABEL[b]}, "
                     "upper 95% interval (model hazard-ratio uncertainty only)", "proportion")
    cols.add("pfpracm_share_u5", (share * blend_deaths).sum(axis=1, min_count=len(BANDS))
             / blend_deaths.sum(axis=1, min_count=len(BANDS)), SRC_ACM,
             "Share of all-cause deaths under 5 attributable to malaria: band shares weighted by "
             "the blended all-cause deaths (blend_deaths_all_*)", "proportion")
    q_acm = band("pfpracm_q_malaria")
    for b in BANDS:
        cols.add(f"pfpracm_q_malaria_{b}", q_acm[b], SRC_ACM, f"PfPR-ACM probability of malaria "
                 f"death {Q_DESC.format(band=LABEL[b])}: pfpracm_share x blend_q_all",
                 "probability (0-1)")
    q_comb = band("combined_q_malaria")
    for b in BANDS:
        cols.add(f"combined_q_malaria_{b}", q_comb[b], SRC_COMBINED, f"Probability of malaria "
                 f"death {Q_DESC.format(band=LABEL[b])}: 0.5 x blend_q_malaria_adj + 0.5 x "
                 f"pfpracm_q_malaria, i.e. 0.5 x ({INDIRECT_MULTIPLIER} x IHME/IGME blend) + "
                 "0.5 x PfPR-ACM (Nigerian states: IHME in place of the blend)", "probability (0-1)")
    flag = band("pfpracm_outside_central95").astype(float)
    cols.add("pfpracm_outside_central95", flag.max(axis=1, skipna=True).map({1.0: True, 0.0: False}),
             SRC_ACM, "TRUE if the location's PfPR is outside the central 95% of the PfPR values the "
             "model was fitted on, for any model age band (shares there rest on sparse data)", "flag")

    # --- MAP ---------------------------------------------------------------------------------
    for c, desc in [("pfpr_2_10", "P. falciparum parasite rate in children aged 2-10, "
                     "population-weighted mean over the unit (the PfPR-ACM exposure)"),
                    ("pfpr_2_10_lower", "PfPR2-10, lower 95% interval"),
                    ("pfpr_2_10_upper", "PfPR2-10, upper 95% interval")]:
        cols.add(f"map_{c}", mp[c].reindex(locs.index), SRC_MAP, desc, "proportion (0-1)")

    # --- IHME on the five bands --------------------------------------------------------------
    for c, desc in [("live_births", "Live births (all maternal ages)"),
                    ("live_births_lower", "Live births, lower 95% UI"),
                    ("live_births_upper", "Live births, upper 95% UI")]:
        cols.add(f"ihme_{c}", ihme_births[c], SRC_IHME, desc, "births per year")
    ihme_metrics = [
        ("population", "ihme_pop", "Population aged {band}", "persons"),
        ("q_all", "ihme_q_all", "Probability of death from all causes " + Q_DESC, "probability (0-1)"),
        ("q_malaria", "ihme_q_malaria", "Probability of death from malaria " + Q_DESC, "probability (0-1)"),
        ("malaria_fraction", "ihme_malaria_fraction", "Share of all-cause deaths at {band} assigned "
         "to malaria (q_malaria / q_all; under 5: malaria deaths / all-cause deaths summed over "
         "the bands)", "proportion (0-1)"),
        ("deaths_all", "ihme_deaths_all", "All-cause deaths at {band} (derived; see README)", "deaths per year"),
        ("deaths_malaria", "ihme_deaths_malaria", "Malaria deaths at {band} (derived; see README)", "deaths per year")]
    for metric, prefix, desc, unit in ihme_metrics:
        w = band(f"ihme_{metric}")
        for b in BANDS:
            cols.add(f"{prefix}_{b}", w[b], SRC_IHME, desc.format(band=LABEL[b]), unit)
        cols.add(f"{prefix}_u5", ihme_u5[metric], SRC_IHME, desc.format(band=LABEL["u5"]), unit)

    # --- UN IGME / WPP on the five bands -----------------------------------------------------
    how_q = {"0_27d": "IGME neonatal mortality rate",
             "1_5m": "IGME 1-11 month rate split by IHME hazard shares",
             "6_11m": "IGME 1-11 month rate split by IHME hazard shares",
             "12_23m": "IGME 1-4 year rate (4q1) split by IHME hazard shares",
             "2_4y": "IGME 1-4 year rate (4q1) split by IHME hazard shares"}
    how_f = {b: "CA-CODE 1-59 month share spread by IHME's age pattern of malaria shares, scaled "
                "to CA-CODE's total on IGME's deaths" for b in BANDS[1:]}
    how_f["0_27d"] = "IHME's share (CA-CODE has no neonatal malaria category)"
    how_pop = {b: "WPP under-1 population split by IHME's under-1 age distribution"
               for b in BANDS[:3]}
    how_pop.update({"12_23m": "WPP age 1", "2_4y": "WPP ages 2, 3 and 4 summed"})
    for metric, prefix, desc, how, unit, src in [
            ("igme_q_all", "igme_q_all", "Probability of death from all causes " + Q_DESC, how_q,
             "probability (0-1)", SRC_IGME5),
            ("igme_malaria_fraction", "igme_malaria_fraction", "Share of all-cause deaths at {band} "
             "assigned to malaria", how_f, "proportion (0-1)", SRC_IGME5),
            ("igme_q_malaria", "igme_q_malaria", "Probability of death from malaria " + Q_DESC,
             {b: "igme_malaria_fraction x igme_q_all" for b in BANDS}, "probability (0-1)", SRC_IGME5),
            ("igme_deaths_all", "igme_deaths_all", "All-cause deaths at {band}",
             {b: ("IGME neonatal deaths" if b == "0_27d" else "IGME 1-11 month or 1-4 year deaths "
                  "split by IHME death shares") for b in BANDS}, "deaths per year", SRC_IGME5),
            ("wpp_population", "wpp_pop", "Population aged {band}", how_pop, "persons", SRC_WPP)]:
        w = band(metric)
        for b in BANDS:
            band_src = {"igme_q_all_0_27d": SRC_IGME, "igme_deaths_all_0_27d": SRC_IGME,
                        "igme_malaria_fraction_0_27d": SRC_IHME}.get(f"{prefix}_{b}", src)
            cols.add(f"{prefix}_{b}", w[b], band_src, f"{desc.format(band=LABEL[b])} ({how[b]})", unit)
    cols.add("wpp_live_births", wpp_births, SRC_WPP, "Live births (UNICEF DM dataflow; see README "
             "caution for Togo)", "births per year")

    # --- Sources as published ----------------------------------------------------------------
    published = {"CME_MRM0": ("q_0_27d", "Neonatal mortality rate (0-27 days)"),
                 "CME_MRM1T11": ("q_1_11m", "Mortality rate 1-11 months, conditional on survival to 1 month"),
                 "CME_MRY0": ("q_u1", "Infant mortality rate"),
                 "CME_MRY1T4": ("q_1_4y", "Child mortality rate 1-4 years (4q1), conditional on survival to age 1"),
                 "CME_MRY0T4": ("q_u5", "Under-five mortality rate"),
                 "CME_TMM0": ("deaths_0_27d", "Neonatal deaths"),
                 "CME_TMM1T11": ("deaths_1_11m", "Deaths at 1-11 months"),
                 "CME_TMY0": ("deaths_u1", "Infant deaths"),
                 "CME_TMY1T4": ("deaths_1_4y", "Deaths at 1-4 years"),
                 "CME_TMY0T4": ("deaths_u5", "Under-five deaths")}
    for code, (name, desc) in published.items():
        rate = name.startswith("q_")
        unit = "probability (0-1); published per 1,000" if rate else "deaths per year"
        for field, suffix, extra in [("value", "", ""), ("lower", "_lower", ", lower 90% bound"),
                                     ("upper", "_upper", ", upper 90% bound")]:
            cols.add(f"igme_published_{name}{suffix}", igme(code, field, 1000.0 if rate else 1.0),
                     SRC_IGME, desc + extra, unit)
    for field, suffix, extra in [("value", "", ""), ("lower", "_lower", ", lower bound as published"),
                                 ("upper", "_upper", ", upper bound as published")]:
        cols.add(f"cacode_malaria_fraction_1_59m{suffix}",
                 igme("CACODE_FRACTION_MALARIA_M1T59", field, 100.0), SRC_CACODE,
                 "Malaria share of deaths at 1-59 months" + extra, "proportion (0-1)")
    cols.add("cacode_malaria_fraction_u5", igme("CACODE_FRACTION_MALARIA_Y0T4", "value", 100.0),
             SRC_CACODE, "Malaria share of under-five deaths (CA-CODE assigns no neonatal deaths "
             "to malaria)", "proportion (0-1)")
    cols.add("cacode_malaria_deaths_1_59m", igme("CACODE_DEATHS_MALARIA_M1T59"), SRC_CACODE,
             "Malaria deaths at 1-59 months (on CA-CODE's own all-cause total)", "deaths per year")
    single = ["DM_POP_TOT_AGE_Y0", "DM_POP_TOT_AGE_Y01", "DM_POP_TOT_AGE_Y02", "DM_POP_TOT_AGE_Y03",
              "DM_POP_TOT_AGE_Y04"]
    wpp_u5 = sum(igme(c) for c in single)
    cols.add("wpp_pop_u1", igme("DM_POP_TOT_AGE_Y0"), SRC_WPP, "Population under 1 year", "persons")
    cols.add("wpp_pop_u5", wpp_u5, SRC_WPP, "Population under 5 years (sum of single ages 0-4)", "persons")

    # Source consistency cautions (see README).
    dm_u5 = igme("DM_POP_U5")
    for k in dm_u5.index[(dm_u5 / wpp_u5 - 1).abs() > 0.005]:
        print(f"  CAUTION {locs.at[k, 'iso3']}: DM_POP_U5 {dm_u5[k]:,.0f} vs single-age sum "
              f"{wpp_u5[k]:,.0f}; using the single-age sum")
    implied = igme("CME_TMM0") / igme("CME_MRM0", scale=1000.0)
    for k in implied.index[(wpp_births / implied - 1).abs() > 0.03]:
        print(f"  CAUTION {locs.at[k, 'iso3']}: wpp_live_births {wpp_births[k]:,.0f} vs births "
              f"implied by IGME neonatal deaths / NMR {implied[k]:,.0f}")

    # --- WorldPop ----------------------------------------------------------------------------
    wp = pd.read_csv(ROOT / "WorldPop" / "worldpop_u5_2023.csv")
    wp.index = wp["location_level"] + "|" + wp["location_name"]
    for c, name, desc in [("pop_0_11_months", "worldpop_pop_u1", "Population aged 0-11 months"),
                          ("pop_1_4_years", "worldpop_pop_1_4y", "Population aged 1-4 years"),
                          ("pop_under_5", "worldpop_pop_u5", "Population under 5 years")]:
        cols.add(name, wp[c].reindex(locs.index), SRC_WP, desc + " (sum of grid cells over the "
                 "unit; Nigerian states use MAP 202403 admin-1 boundaries; WorldPop applies one "
                 "national under-1 share to every grid cell)", "persons")

    df = cols.data.reset_index(drop=True)
    assert len(df) == len(locs) and not df.duplicated(["location_level", "iso3", "state_name"]).any()
    assert df.columns.is_unique and len(cols.dictionary) == df.shape[1]
    df.to_csv(OUT / "malaria_burden_inputs_2023.csv", index=False)
    dictionary = pd.DataFrame(cols.dictionary, columns=["column", "source", "description", "unit"])
    dictionary.to_csv(OUT / "data_dictionary.csv", index=False)
    print(f"Wrote {len(df)} rows x {df.shape[1]} columns to output/malaria_burden_inputs_2023.csv")

    main_cols = MAIN_IDS + [c.format(b=b) if "{b}" in c else c for c in MAIN_COLUMNS
                            for b in (BANDS if "{b}" in c else [None])]
    df[main_cols].to_csv(OUT / "malaria_burden_main_2023.csv", index=False)
    dictionary.set_index("column").loc[main_cols].reset_index().to_csv(
        OUT / "malaria_burden_main_2023_dictionary.csv", index=False)
    print(f"Wrote {len(df)} rows x {len(main_cols)} columns to output/malaria_burden_main_2023.csv")


if __name__ == "__main__":
    main()
