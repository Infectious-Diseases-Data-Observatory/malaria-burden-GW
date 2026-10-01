# Fetch WorldPop Global2 R2025A (2023, constrained, UN-adjusted, 1 km) population rasters for
# ages 0-12 months and 1-4 years, and sum them to country totals for the SSA countries in
# reference/countries.csv and to Nigerian state totals (using MAP's 202403 admin-1 boundaries,
# the same units as MAP's PfPR state estimates).
#
# Rasters are cached in .cache/worldpop/ (git-ignored, ~400 MB). Output:
#   WorldPop/worldpop_u5_2023.csv
#
# Usage:  Rscript scripts/fetch_worldpop.R
suppressPackageStartupMessages({
  library(jsonlite)
  library(terra)
  library(sf)
  library(exactextractr)
})

args <- commandArgs(trailingOnly = FALSE)
root <- normalizePath(file.path(dirname(sub("--file=", "", args[grep("--file=", args)])), ".."))
cache <- file.path(root, ".cache", "worldpop")
dir.create(cache, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(root, "WorldPop"), showWarnings = FALSE)
options(timeout = 600)

year <- "2023"
release <- "G2_CN_Age_R25A_1km"
countries <- read.csv(file.path(root, "reference", "countries.csv"), encoding = "UTF-8")
states <- read.csv(file.path(root, "reference", "nigeria_states.csv"), encoding = "UTF-8")

files_for <- function(iso3) {
  meta <- fromJSON(sprintf("https://hub.worldpop.org/rest/data/age_structures/%s?iso3=%s",
                           release, iso3))$data
  rec <- meta[meta$popyear == year, ]
  stopifnot(nrow(rec) == 1)
  f <- unlist(rec$files)
  list(doi = rec$doi,
       t00 = f[grepl("_t_00_", f)],
       t01 = f[grepl("_t_01_", f)])
}

download <- function(url) {
  dest <- file.path(cache, basename(url))
  if (!file.exists(dest)) {
    message("  downloading ", basename(url))
    download.file(url, dest, mode = "wb", quiet = TRUE)
  }
  dest
}

rows <- list()
nga_rasters <- NULL
for (iso3 in countries$iso3) {
  message(iso3)
  f <- files_for(iso3)
  stopifnot(length(f$t00) == 1, length(f$t01) == 1)
  r00 <- rast(download(f$t00))
  r01 <- rast(download(f$t01))
  s00 <- global(r00, "sum", na.rm = TRUE)$sum
  s01 <- global(r01, "sum", na.rm = TRUE)$sum
  rows[[iso3]] <- data.frame(location_level = "country", iso3 = iso3,
                             location_name = countries$country_name[countries$iso3 == iso3],
                             pop_0_11_months = s00, pop_1_4_years = s01,
                             pop_under_5 = s00 + s01, file_00 = basename(f$t00),
                             file_01 = basename(f$t01), doi = f$doi)
  if (iso3 == "NGA") nga_rasters <- list(r00 = r00, r01 = r01, doi = f$doi,
                                         f00 = basename(f$t00), f01 = basename(f$t01))
}

# Nigerian states: zonal sums over MAP admin-1 polygons (exact cell-coverage weighting).
wfs <- paste0("https://data.malariaatlas.org/geoserver/Admin_Units/ows?service=WFS&version=2.0.0",
              "&request=GetFeature&typeNames=Admin_Units:202403_Global_Admin_1",
              "&outputFormat=application/json&CQL_FILTER=iso=%27NGA%27")
shp_path <- file.path(cache, "map_202403_admin1_NGA.geojson")
if (!file.exists(shp_path)) download.file(wfs, shp_path, mode = "wb", quiet = TRUE)
adm1 <- st_read(shp_path, quiet = TRUE)
adm1 <- merge(adm1, states[, c("map_name", "state_name")], by.x = "name_1", by.y = "map_name")
stopifnot(nrow(adm1) == 37)

s00 <- exact_extract(nga_rasters$r00, adm1, "sum", progress = FALSE)
s01 <- exact_extract(nga_rasters$r01, adm1, "sum", progress = FALSE)
rows[["NGA_states"]] <- data.frame(location_level = "nigeria_state", iso3 = "NGA",
                                   location_name = adm1$state_name,
                                   pop_0_11_months = s00, pop_1_4_years = s01,
                                   pop_under_5 = s00 + s01, file_00 = nga_rasters$f00,
                                   file_01 = nga_rasters$f01, doi = nga_rasters$doi)

out <- do.call(rbind, rows)
out <- cbind(source = "WorldPop Global2 R2025A (constrained, UN-adjusted, 1 km)", year = 2023, out)
out <- out[order(out$location_level, out$location_name), ]

nat <- out$pop_under_5[out$location_level == "country" & out$iso3 == "NGA"]
st <- sum(out$pop_under_5[out$location_level == "nigeria_state"])
message(sprintf("Nigeria under-5: national raster sum %.0f; sum of states %.0f (ratio %.4f)",
                nat, st, st / nat))
write.csv(out, file.path(root, "WorldPop", "worldpop_u5_2023.csv"), row.names = FALSE,
          fileEncoding = "UTF-8")
message("Wrote ", nrow(out), " rows to WorldPop/worldpop_u5_2023.csv")
