# Malaria burden inputs — sub-Saharan Africa, 2023

Shared burden inputs for GiveWell malaria intervention cost-effectiveness models: live births,
under-5 deaths, probability of death and population by age band, malaria cause fractions,
*P. falciparum* prevalence and under-5 population, for sub-Saharan African countries and Nigerian
states, from IHME, UN IGME, MAP and WorldPop.

**Main file:** [`output/malaria_burden_inputs_2023.csv`](output/malaria_burden_inputs_2023.csv),
one row per country (48) and per Nigerian state (37). Every column is defined in
[`output/data_dictionary.csv`](output/data_dictionary.csv). Column prefixes give the source:
`ihme_`, `igme_`, `wpp_`, `map_`, `worldpop_`.

## Coverage

- **Countries:** the 48 countries in the UN SDG "Sub-Saharan Africa" region
  ([`reference/countries.csv`](reference/countries.csv)). Sudan is not included.
  Mauritius and Seychelles have no IHME values: GBD places them outside its Sub-Saharan Africa
  super-region, so they were not in the IHME download.
- **Nigerian states:** 36 states + Federal Capital Territory
  ([`reference/nigeria_states.csv`](reference/nigeria_states.csv) maps GBD, IGME and MAP IDs).
  Note that Niger (country) and Niger State share a name; join on IDs, never names.
- **Age bands** (column suffixes): `0_27d` neonatal, `1_5m`, `6_11m`, `1_11m` post-neonatal,
  `u1`, `12_23m` (age 1), `2y`, `3y`, `4y`, `2_4y`, `1_4y`, `u5`.

## Sources

| Prefix | Source | Version | Year | Countries | Nigerian states | Licence |
|---|---|---|---|---|---|---|
| `ihme_` | IHME Global Burden of Disease | GBD 2023 (files in `IHME/`, downloaded manually from the GBD Results Tool) | 2023 | ✓ (46) | ✓ | IHME free-of-charge non-commercial user agreement |
| `igme_` | UN Inter-agency Group for Child Mortality Estimation | 2025 round (released March 2026), UNICEF SDMX API `UNICEF,CME,1.0` | 2023 | ✓ | — | CC BY 3.0 IGO |
| `igme_state_` | UN IGME subnational estimates | `UNICEF,CME_SUBNATIONAL,1.0` | **2021** (latest published) | — | ✓ (U5MR and NMR only) | CC BY 3.0 IGO |
| `wpp_` | UN World Population Prospects 2024 (the births/population IGME uses) | via UNICEF SDMX API `UNICEF,DM,1.0` and `UNPD,UNPD_DEMOGRAPHY,1.0` | 2023 | ✓ | — | CC BY 3.0 IGO |
| `map_` | Malaria Atlas Project | 202608 release, admin-0/admin-1 aggregates from data.malariaatlas.org | 2023 | ✓ (45) | ✓ | CC BY 3.0 |
| `worldpop_` | WorldPop Global2 | R2025A, constrained, UN-adjusted, 1 km ([DOI 10.5258/SOTON/WP00842](https://doi.org/10.5258/SOTON/WP00842)) | 2023 | ✓ | ✓ | CC BY 4.0 |

Raw API responses are saved under each source's `raw/` folder with a `fetch_log.json`
recording the exact URL and UTC time of each request. The UNICEF API serves only the current
IGME round, so later re-runs may return revised values.

## Methods

### IHME (`scripts/process_ihme.py`)
The IHME downloads contain population, live births and probability of death (*q*) for all
causes and malaria, but no death counts. These are derived:

| Quantity | Formula | Notes |
|---|---|---|
| All-cause deaths in a band | population × [−ln(1 − *q*) / *n*] | *n* = band width in years (28/365.25, 0.5 − 28/365.25, 0.5, 1, 3). Converts *q* to an annual death rate assuming a constant rate within the band. |
| Malaria fraction | *q*<sub>malaria</sub> / *q*<sub>all</sub> | Equals malaria deaths / all-cause deaths in the band when malaria's share of the death rate is constant within the band. |
| Malaria deaths | all-cause deaths × malaria fraction | |
| Composite bands (1–11 months, <1, 1–4, <5) | deaths and population summed; *q* = 1 − ∏(1 − *q*<sub>band</sub>) | Chained *q* reproduces IHME's own <1 and <5 values to 10⁻⁶ (checked in the script). |

Why not population × *q*? *q* is a probability over the whole band for someone entering it,
while population is a point-in-time headcount. For Nigeria, population × *q* gives about 18,000
neonatal deaths, against about 240,000 here and 241,907 from live births × *q*<sub>neonatal</sub>. It also
overstates 2–4-year deaths about 3× and under-5 deaths about 5×.

Derived deaths and malaria fractions have no uncertainty intervals, because the IHME *q*
download has none.

### UN IGME / WPP (`scripts/fetch_igme.py`)
Rates are converted from per-1,000 to probabilities (0–1). Denominators differ by indicator:
neonatal, infant and under-5 rates are per live birth; the 1–11 month rate is conditional on
survival to 1 month; the 1–4 rate (4q1) is conditional on survival to age 1. IGME bounds are
**90%** uncertainty intervals (IHME and MAP use 95%). WPP values are converted from thousands
to persons.

### MAP (`scripts/fetch_map.py`)
PfPR for ages 2–10, aggregated by MAP to country and state. MAP publishes no all-age PfPR
product. Lesotho, Mauritius and Seychelles have no MAP PfPR (no endemic *P. falciparum*
transmission) and are left blank rather than set to zero.

### WorldPop (`scripts/fetch_worldpop.R`)
Grid-cell sums of the 0–12 month and 1–4 year rasters, over each country's raster, and over
MAP's 202403 admin-1 boundaries for Nigerian states (exact cell-coverage weighting, the same
units as MAP's state PfPR). The 37 states sum to 99.9% of the national raster total.

## Known gaps and cautions

- **Single-year death probabilities for ages 2, 3 and 4 are not published by either source.**
  IHME publishes 12–23 months and 2–4 years; IGME publishes 1–4 years only. Population is
  available for single years.
- **IGME publishes no 2023 Nigerian state estimates**, and no state death counts or
  1–11 month / 1–4 rates. The `igme_state_*_2021` columns hold the latest (2021) values and are
  not 2023.
- **IHME and IGME differ materially.** For example, Nigeria 2023 under-5 deaths are 715,000
  (IHME, derived) against 857,000 (IGME); births are 8.50 million (IHME) against 7.51 million
  (WPP). Choose one source consistently within a model rather than mixing.
- IHME's uncertainty intervals for population and births are not carried to composite bands,
  because bounds do not add.

## Reproducing

Requires Python 3 with pandas and numpy, and R with terra, sf, exactextractr and jsonlite.

```bash
python3 scripts/fetch_igme.py      # UNICEF SDMX API (about 5 requests)
python3 scripts/fetch_map.py       # MAP data API
Rscript scripts/fetch_worldpop.R   # downloads ~130 MB of rasters to .cache/ (git-ignored)
python3 scripts/process_ihme.py    # IHME/ downloads -> IHME/ihme_2023_by_age_band.csv
python3 scripts/build_merged.py    # -> output/
```

`fetch_igme.py` and `fetch_map.py` accept `--offline` to re-tidy from the saved raw files
without network access.

## Citations

- GBD 2023 Collaborators. Global Burden of Disease Study 2023 (GBD 2023) Results. Seattle:
  Institute for Health Metrics and Evaluation (IHME).
- United Nations Inter-agency Group for Child Mortality Estimation (UN IGME). *Levels and
  Trends in Child Mortality: Report 2025.* New York: UNICEF, 2026.
- United Nations, Department of Economic and Social Affairs, Population Division (2024).
  *World Population Prospects 2024.*
- Malaria Atlas Project. data.malariaatlas.org, 202608 release.
- Bondarenko M. et al. (2025). Global2 R2025A age and sex structures, 1 km. WorldPop,
  University of Southampton. DOI: 10.5258/SOTON/WP00842.
