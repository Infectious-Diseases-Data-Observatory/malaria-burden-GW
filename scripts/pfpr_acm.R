# PfPR-ACM malaria share of all-cause deaths by age band, from the in-house PfPR-all-cause
# mortality model (MIS/DHS malaria prevalence project, primary v9: one binomial/cloglog GAM per
# age band with a smooth in regional MAP PfPR2-10, calendar year, 17 covariates and survey,
# country and region random intercepts).
#
# For model band g at population-weighted PfPR p (percent), the share of all-cause deaths that
# would not occur at PfPR 0 is
#     share_g(p) = 1 - exp(f_g(0) - f_g(p))
# where f_g is the band's fitted PfPR smooth; every other model term cancels in the contrast.
# This is the in-house project's own calculation (R_cbh/primary/02_effects.R). 95% intervals
# use the within-fit coefficient covariance, normal on the log hazard ratio.
#
# Only the compact PfPR components (knots, 4 coefficients and covariance per band; no survey
# data) are read from the project, at $PFPR_ACM_PROJECT (default: sibling folder
# "MIS:DHS malaria prevalence"). Nothing in that project is modified.
#
# Outputs (PfPR-ACM/):
#   pfpr_acm_shares_2023.csv   share by location (countries + Nigerian states) and age band
#   pfpr_acm_curve_v9.csv      share and log HR on a 0-100% PfPR grid (0.1 steps), per model band
#   provenance.json            model version, file hashes, source commit
#
# Usage:  Rscript scripts/pfpr_acm.R
suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = FALSE)
script <- gsub("~+~", " ", sub("--file=", "", args[grep("--file=", args)]), fixed = TRUE)
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
stopifnot(file.exists(file.path(root, "reference", "countries.csv")))
project <- Sys.getenv("PFPR_ACM_PROJECT",
                      file.path(dirname(root), "MIS:DHS malaria prevalence"))
model_id <- "primary_map_regional17_dhsmics_gamma2_v9"
components_path <- file.path(project, "data/derived_cbh/models", model_id, "pfpr_components.rds")
manifest_path <- file.path(project, "results/cbh", model_id, "fit_manifest.csv")
anchors_path <- file.path(project, "results/cbh", model_id, "pfpr_attributable_fraction_anchors.csv")
stopifnot(file.exists(components_path), file.exists(manifest_path), file.exists(anchors_path))
out_dir <- file.path(root, "PfPR-ACM")
dir.create(out_dir, showWarnings = FALSE)

components <- readRDS(components_path)
manifest <- read.csv(manifest_path)
stopifnot(length(components) == 7,
          all(vapply(components, `[[`, "", "model_md5") ==
                manifest$md5[match(vapply(components, `[[`, "", "fit_id"), manifest$fit_id)]))
model_bands <- vapply(components, `[[`, "", "age_band")
stopifnot(identical(unname(model_bands), c("<1", "1-5", "6-11", "12-23", "24-35", "36-47", "48-59")))

contrast <- function(piece, pfpr_pct) {
  nd <- data.frame(pfpr_pct = pfpr_pct)
  L <- PredictMat(piece$smooth, data.frame(pfpr_pct = 0 * pfpr_pct)) - PredictMat(piece$smooth, nd)
  est <- drop(L %*% piece$coef)
  se <- sqrt(pmax(rowSums((L %*% piece$covariance) * L), 0))
  data.frame(model_band = piece$age_band, pfpr_pct = pfpr_pct, log_hr_zero_vs_current = est,
             log_hr_se = se, share = 1 - exp(est), share_lower_95 = 1 - exp(est + 1.96 * se),
             share_upper_95 = 1 - exp(est - 1.96 * se),
             outside_observed_support = pfpr_pct < piece$support[1] | pfpr_pct > piece$support[4])
}

# Check against the project's own published anchors (PfPR 10, 20, 30, 50%).
anchors <- read.csv(anchors_path)
check <- do.call(rbind, lapply(components, function(p) contrast(p, c(10, 20, 30, 50))))
j <- match(paste(anchors$age_band, anchors$pfpr_pct), paste(check$model_band, check$pfpr_pct))
gap <- max(abs(check$share[j] - anchors$attributable_fraction),
           abs(check$share_lower_95[j] - anchors$lower_95),
           abs(check$share_upper_95[j] - anchors$upper_95))
stopifnot(!anyNA(j), gap < 1e-10)
message("Reproduces the project's published attributable-fraction anchors (max gap ", signif(gap, 2), ")")

curve <- do.call(rbind, lapply(components, contrast, pfpr_pct = round(seq(0, 100, by = 0.1), 1)))
write.csv(curve, file.path(out_dir, "pfpr_acm_curve_v9.csv"), row.names = FALSE)

# Shares at each location's 2023 MAP PfPR2-10 (population-weighted admin-0 / admin-1 means).
map <- read.csv(file.path(root, "MAP", "map_pfpr_2023.csv"), encoding = "UTF-8")
map$pfpr_pct <- 100 * map$pfpr_2_10
by_model <- do.call(rbind, lapply(components, function(p) {
  z <- contrast(p, map$pfpr_pct)
  cbind(map[c("location_level", "iso3", "location_name")], z)
}))

# Output bands: model bands 1-4 map one-to-one; 2-4 years averages the three yearly model
# bands, i.e. deaths split equally across ages 2, 3 and 4 (the in-house burden convention).
# No interval for 2-4 years: cross-band covariance is not estimated.
target <- c("<1" = "0_27d", "1-5" = "1_5m", "6-11" = "6_11m", "12-23" = "12_23m")
single <- by_model[by_model$model_band %in% names(target), ]
single$age_band <- unname(target[single$model_band])
older <- by_model[by_model$model_band %in% c("24-35", "36-47", "48-59"), ]
older <- aggregate(share ~ location_level + iso3 + location_name + pfpr_pct, data = older, FUN = mean)
older$age_band <- "2_4y"
older$model_band <- "24-35, 36-47, 48-59 (mean)"
older$share_lower_95 <- older$share_upper_95 <- NA_real_
older$outside_observed_support <- NA
cols <- c("location_level", "iso3", "location_name", "pfpr_pct", "age_band", "model_band", "share",
          "share_lower_95", "share_upper_95", "outside_observed_support")
shares <- rbind(single[cols], older[cols])
shares <- shares[order(shares$location_level, shares$location_name,
                       match(shares$age_band, c("0_27d", "1_5m", "6_11m", "12_23m", "2_4y"))), ]
shares <- cbind(source = paste("PfPR-ACM", model_id), year = 2023, shares)
write.csv(shares, file.path(out_dir, "pfpr_acm_shares_2023.csv"), row.names = FALSE,
          fileEncoding = "UTF-8")

commit <- tryCatch(system2("git", c("-C", shQuote(project), "rev-parse", "HEAD"), stdout = TRUE),
                   error = function(e) NA_character_)
write_json(list(
  model = model_id,
  source_project = basename(project),
  source_commit = commit,
  components_md5 = unname(tools::md5sum(components_path)),
  fit_md5 = setNames(as.list(manifest$md5), manifest$fit_id),
  knots = setNames(lapply(components, function(p) p$smooth$xp), model_bands),
  pfpr_support_min_p025_p975_max = setNames(lapply(components, `[[`, "support"), model_bands),
  exposure = "MAP 202608 PfPR2-10, 2023, population-weighted admin-0/admin-1 means",
  created_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")),
  file.path(out_dir, "provenance.json"), auto_unbox = TRUE, pretty = TRUE, digits = NA)

neg <- shares[is.finite(shares$share) & shares$share < 0, ]
message("Wrote ", nrow(shares), " location-band shares for ", length(unique(paste(shares$location_level,
        shares$location_name))), " locations; negative shares: ", nrow(neg))
