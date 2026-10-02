"""Fetch UN IGME child mortality estimates, the UN WPP births/population IGME uses, and CA-CODE
malaria cause fractions from the UNICEF SDMX API, for the countries in reference/countries.csv.

Raw API responses are saved verbatim to UN-IGME/raw/ alongside a fetch log (URL, UTC time).
Tidy outputs are written to UN-IGME/:
  igme_national_2023.csv       one row per country x indicator (value, lower, upper)
  igme_nigeria_states.csv      Nigerian state U5MR / NMR, all years published (series ends 2021)

Usage:  python3 scripts/fetch_igme.py                       # fetch all + tidy
        python3 scripts/fetch_igme.py --only=cacode_malaria  # fetch one query + tidy
        python3 scripts/fetch_igme.py --offline             # re-tidy from saved raw files only
"""
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "UN-IGME" / "raw"
OUT = ROOT / "UN-IGME"
BASE = "https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data"
YEAR = 2023

# CME (UN IGME estimates only). Rates are per 1,000; see README for denominators.
CME_INDICATORS = [
    "CME_MRM0",     # neonatal mortality rate (0-27 days), per 1,000 live births
    "CME_MRM1T11",  # post-neonatal (1-11 months), per 1,000 children alive at 1 month
    "CME_MRY0",     # infant mortality rate, per 1,000 live births
    "CME_MRY1T4",   # child mortality rate 1-4 (4q1), per 1,000 children alive at age 1
    "CME_MRY0T4",   # under-five mortality rate, per 1,000 live births
    "CME_TMM0",     # neonatal deaths
    "CME_TMM1T11",  # deaths 1-11 months
    "CME_TMY0",     # infant deaths
    "CME_TMY1T4",   # deaths 1-4 years
    "CME_TMY0T4",   # under-five deaths
]


def fetch(url, retries=6):
    """GET url, returning text ('' on 404 = no matching data). Backs off on 429/5xx."""
    req = urllib.request.Request(url, headers={"User-Agent": "givewell-malaria-burden/0.1"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 30 * 2 ** attempt
            print(f"  HTTP {e.code}; retrying in {wait}s")
            time.sleep(wait)


def queries(iso3s):
    areas = "+".join(iso3s)
    period = f"startPeriod={YEAR}&endPeriod={YEAR}"
    return {
        "cme_national": f"{BASE}/UNICEF,CME,1.0/{areas}.{'+'.join(CME_INDICATORS)}._T._T"
                        f"?format=csv&labels=both&{period}",
        # UN WPP 2024 live births and under-5 population (as used by IGME), thousands
        "dm_births_u5pop": f"{BASE}/UNICEF,DM,1.0/{areas}.DM_BRTS+DM_POP_U5..."
                           f"?format=csv&labels=both&{period}",
        # UN WPP 2024 population by single year of age 0-4, thousands
        "wpp_pop_single_age": f"{BASE}/UNPD,UNPD_DEMOGRAPHY,1.0/{areas}.DM_POP_TOT_AGE._T._T."
                              f"Y0+Y01+Y02+Y03+Y04?format=csv&labels=both&{period}",
        # Subnational (admin-1) Nigeria: U5MR and NMR, all years, UN IGME estimates only
        "cme_subnational_nga": f"{BASE}/UNICEF,CME_SUBNATIONAL,1.0/.MRM0+MRY0T4._T._T.UN_IGME..NGA."
                               f"?format=csv&labels=both",
        # CA-CODE (WHO/UNICEF causes of death, published with UN IGME): malaria share (%) and
        # deaths for 1-59 months and under 5. CA-CODE has no neonatal malaria category.
        "cacode_malaria": f"{BASE}/UNICEF,CME_CAUSE_OF_DEATH,1.0/{areas}.FRACTION+DEATHS.MALARIA._T."
                          f"M1T59+Y0T4.?format=csv&labels=both&{period}",
    }


def fetch_all(only=None):
    RAW.mkdir(parents=True, exist_ok=True)
    iso3s = pd.read_csv(ROOT / "reference" / "countries.csv")["iso3"].tolist()
    log_path = RAW / "fetch_log.json"
    log = {e["name"]: e for e in json.loads(log_path.read_text())} if log_path.exists() else {}
    for name, url in queries(iso3s).items():
        if only and name not in only:
            continue
        print(f"Fetching {name} ...")
        text = fetch(url)
        (RAW / f"{name}.csv").write_text(text, encoding="utf-8")
        log[name] = {"name": name, "url": url,
                     "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "rows": max(text.count("\n") - 1, 0)}
        time.sleep(5)  # be polite; the API rate-limits
    log_path.write_text(json.dumps(list(log.values()), indent=2), encoding="utf-8")


def read_raw(name):
    text = (RAW / f"{name}.csv").read_text(encoding="utf-8")
    return pd.read_csv(io.StringIO(text)) if text.strip() else pd.DataFrame()


def tidy():
    countries = pd.read_csv(ROOT / "reference" / "countries.csv")[["iso3", "country_name"]]

    cme = read_raw("cme_national").rename(columns={
        "REF_AREA": "iso3", "INDICATOR": "indicator_code", "Indicator": "indicator",
        "Unit of measure": "unit", "TIME_PERIOD": "year", "OBS_VALUE": "value",
        "LOWER_BOUND": "lower", "UPPER_BOUND": "upper"})
    cme = cme[["iso3", "indicator_code", "indicator", "unit", "year", "value", "lower", "upper"]]

    # WPP 2024 births / population are published in thousands; convert to persons.
    dm = read_raw("dm_births_u5pop")
    dm = dm[(dm["SEX"] == "_T") & (dm["RESIDENCE"] == "_T")]
    wpp = read_raw("wpp_pop_single_age")
    wpp = wpp[(wpp["SEX"] == "_T") & (wpp["RESIDENCE"] == "_T")]
    wpp = wpp.assign(INDICATOR="DM_POP_TOT_AGE_" + wpp["AGE"],
                     Indicator="Population " + wpp["Current age"])
    pop = pd.concat([dm, wpp]).rename(columns={
        "REF_AREA": "iso3", "INDICATOR": "indicator_code", "Indicator": "indicator",
        "TIME_PERIOD": "year"})
    pop = pop.assign(unit="Persons", value=pop["OBS_VALUE"] * 10.0 ** pop["UNIT_MULTIPLIER"])
    pop = pop[["iso3", "indicator_code", "indicator", "unit", "year", "value"]]

    cod = read_raw("cacode_malaria")
    cod = cod.assign(indicator_code="CACODE_" + cod["INDICATOR"] + "_MALARIA_" + cod["AGE_GROUP"],
                     indicator="CA-CODE malaria " + cod["Indicator"].str.lower() + ", " +
                     cod["Age group"]).rename(columns={
        "REF_AREA": "iso3", "Unit of measure": "unit", "TIME_PERIOD": "year",
        "OBS_VALUE": "value", "LOWER_BOUND": "lower", "UPPER_BOUND": "upper"})
    cod = cod[["iso3", "indicator_code", "indicator", "unit", "year", "value", "lower", "upper"]]

    national = (pd.concat([cme, pop, cod]).merge(countries, on="iso3", how="left")
                .sort_values(["iso3", "indicator_code"]))
    national.insert(1, "country_name", national.pop("country_name"))
    assert national["country_name"].notna().all()
    national.to_csv(OUT / f"igme_national_{YEAR}.csv", index=False)

    states = pd.read_csv(ROOT / "reference" / "nigeria_states.csv")[
        ["igme_code", "state_name", "gbd_location_id"]]
    sub = read_raw("cme_subnational_nga").rename(columns={
        "REF_AREA": "igme_code", "INDICATOR": "indicator_code", "Indicator": "indicator",
        "Unit of measure": "unit", "REF_DATE": "year", "OBS_VALUE": "value",
        "LOWER_BOUND": "lower", "UPPER_BOUND": "upper", "SERIES_YEAR": "igme_round"})
    sub = sub[["igme_code", "indicator_code", "indicator", "unit", "year", "value", "lower",
               "upper", "igme_round"]].merge(states, on="igme_code", how="left")
    assert sub["state_name"].notna().all() and sub["igme_code"].nunique() == 37
    sub = sub[["igme_code", "state_name", "gbd_location_id"] + list(sub.columns[1:9])]
    sub.sort_values(["state_name", "indicator_code", "year"]).to_csv(
        OUT / "igme_nigeria_states.csv", index=False)
    print(f"Wrote {len(national)} national rows and {len(sub)} Nigeria state rows")


if __name__ == "__main__":
    only = {a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")} or None
    if "--offline" not in sys.argv:
        fetch_all(only)
    tidy()
