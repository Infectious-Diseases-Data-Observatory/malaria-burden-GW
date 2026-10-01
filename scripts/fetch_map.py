"""Fetch Malaria Atlas Project (MAP) P. falciparum parasite rate (PfPR, ages 2-10) for 2023,
pre-aggregated by MAP to admin-0 (country) and admin-1 (state), from the API behind
https://data.malariaatlas.org/trends .

Raw JSON-stat responses are saved verbatim to MAP/raw/ with a fetch log. Tidy output:
  MAP/map_pfpr_2023.csv   SSA countries (admin-0) + Nigerian states (admin-1): mean, lci, uci

Usage:  python3 scripts/fetch_map.py            # fetch + tidy
        python3 scripts/fetch_map.py --offline  # re-tidy from saved raw files only
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "MAP" / "raw"
OUT = ROOT / "MAP"
VERSION = "202608"     # MAP release (Aug 2026): annual surfaces 2000-2025
YEAR = 2023
API = "https://data.malariaatlas.org/map-platform-app-backend/api/v1/trends/malaria"
META = "https://data.malariaatlas.org/admin-unit-metadata/admin-units"
STATS = ["mean", "lci", "uci"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "givewell-malaria-burden/0.1"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("utf-8")


def requests():
    reqs = {f"pfpr_{level}_{stat}": f"{API}/Pf_PR-rate/{level}/{stat}?version={VERSION}"
            for level in ["admin0", "admin1"] for stat in STATS}
    reqs["admin1_units"] = f"{META}/ADMIN1?mapAdmin=2023_mg_5k"
    return reqs


def fetch_all():
    RAW.mkdir(parents=True, exist_ok=True)
    log = []
    for name, url in requests().items():
        print(f"Fetching {name} ...")
        (RAW / f"{name}.json").write_text(get(url), encoding="utf-8")
        log.append({"name": name, "url": url,
                    "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        time.sleep(2)
    (RAW / "fetch_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


def jsonstat_to_frame(path):
    """Flatten a 2-D JSON-stat 2.0 dataset (unit x year) to long form."""
    j = json.loads(path.read_text(encoding="utf-8"))
    unit_dim, year_dim = j["id"]
    units = j["dimension"][unit_dim]["category"]["index"]
    years = j["dimension"][year_dim]["category"]["index"]
    n_years = j["size"][1]
    values = j["value"]
    items = values.items() if isinstance(values, dict) else enumerate(values)
    rows = [(units[int(k) // n_years], int(years[int(k) % n_years]), v)
            for k, v in items if v is not None]
    return pd.DataFrame(rows, columns=["unit", "year", "value"])


def load_level(level):
    frames = [jsonstat_to_frame(RAW / f"pfpr_{level}_{s}.json").set_index(["unit", "year"])
              .rename(columns={"value": s}) for s in STATS]
    return pd.concat(frames, axis=1).reset_index()


def tidy():
    countries = pd.read_csv(ROOT / "reference" / "countries.csv")
    states = pd.read_csv(ROOT / "reference" / "nigeria_states.csv")

    a0 = load_level("admin0")
    a0 = a0[(a0["year"] == YEAR) & a0["unit"].isin(countries["iso3"])]
    a0 = a0.merge(countries[["iso3", "country_name"]], left_on="unit", right_on="iso3")
    a0 = a0.assign(location_level="country", location_name=a0["country_name"], map_admin_id=pd.NA)

    units = pd.DataFrame(json.loads((RAW / "admin1_units.json").read_text(encoding="utf-8")))
    nga = units[units["iso3"] == "NGA"][["id", "name"]].rename(columns={"id": "map_admin_id",
                                                                        "name": "map_name"})
    a1 = load_level("admin1")
    a1 = a1[a1["year"] == YEAR].merge(nga, left_on="unit", right_on="map_admin_id")
    a1 = a1.merge(states[["map_name", "state_name"]], on="map_name", how="left")
    assert len(a1) == 37 and a1["state_name"].notna().all(), a1[a1["state_name"].isna()]
    a1 = a1.assign(location_level="nigeria_state", iso3="NGA", location_name=a1["state_name"])

    cols = ["location_level", "iso3", "location_name", "map_admin_id", "year", "mean", "lci", "uci"]
    out = pd.concat([a0[cols], a1[cols]]).rename(columns={
        "mean": "pfpr_2_10", "lci": "pfpr_2_10_lower", "uci": "pfpr_2_10_upper"})
    out.insert(0, "source", f"MAP {VERSION} release")
    out.to_csv(OUT / f"map_pfpr_{YEAR}.csv", index=False)
    missing = sorted(set(countries["iso3"]) - set(a0["iso3"]))
    print(f"Wrote {len(out)} rows; countries without MAP PfPR: {missing or 'none'}")


if __name__ == "__main__":
    if "--offline" not in sys.argv:
        fetch_all()
    tidy()
