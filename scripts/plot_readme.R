# README figure: probability of dying from malaria before age 5 by country, 2023, from the
# IHME/IGME blend with the x 1.6 indirect-death adjustment (blend_q_malaria_adj) and from PfPR-ACM.
#
# Cumulative probability before 5 from the five band probabilities (competing risks):
#     q_malaria_u5 = sum_b S_b x q_malaria_b,   S_b = prod_{j<b} (1 - q_all_j)
# using blend_q_all for survival in both series. PfPR-ACM band q = pfpracm_share x blend_q_all.
# The CSV also carries the unadjusted blend and the combined (average) estimate.
#
# Outputs (figures/): u5_malaria_probability_{light,dark}.png and the plotted values as CSV.
# Usage:  Rscript scripts/plot_readme.R
suppressPackageStartupMessages(library(ggplot2))

args <- commandArgs(trailingOnly = FALSE)
script <- gsub("~+~", " ", sub("--file=", "", args[grep("--file=", args)]), fixed = TRUE)
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
out_dir <- file.path(root, "figures")
dir.create(out_dir, showWarnings = FALSE)

bands <- c("0_27d", "1_5m", "6_11m", "12_23m", "2_4y")
d <- read.csv(file.path(root, "output", "malaria_burden_inputs_2023.csv"), encoding = "UTF-8")
d <- d[d$location_level == "country", ]
q_all <- as.matrix(d[paste0("blend_q_all_", bands)])
survival <- cbind(1, t(apply(1 - q_all, 1, cumprod)))[, seq_along(bands)]
cumulative <- function(prefix) rowSums(survival * as.matrix(d[paste0(prefix, bands)]))
res <- data.frame(iso3 = d$iso3, country = d$country_name, pfpr_2_10 = d$map_pfpr_2_10,
                  blend_direct = cumulative("blend_q_malaria_"),
                  blend = cumulative("blend_q_malaria_adj_"),           # x 1.6 for indirect deaths
                  pfpracm = cumulative("pfpracm_q_malaria_"),
                  combined = cumulative("combined_q_malaria_"),
                  all_cause = 1 - apply(1 - q_all, 1, prod))
res <- res[complete.cases(res), ]
res <- res[order(res$pfpracm), ]
csv <- data.frame(res[c("iso3", "country", "pfpr_2_10")],
                  all_cause_q_u5 = res$all_cause,
                  blend_direct_per_1000 = 1000 * res$blend_direct,
                  blend_indirect_adjusted_per_1000 = 1000 * res$blend,
                  pfpracm_per_1000 = 1000 * res$pfpracm,
                  combined_per_1000 = 1000 * res$combined,
                  ratio_pfpracm_to_adjusted_blend = res$pfpracm / res$blend)
write.csv(csv[order(-csv$pfpracm_per_1000), ],
          file.path(out_dir, "u5_malaria_probability_blend_vs_pfpracm.csv"), row.names = FALSE)

blend_label <- "IHME/IGME blend × 1.6"
res$label <- sprintf("%s (%.0f%%)", res$country, 100 * res$pfpr_2_10)
res$label <- factor(res$label, levels = res$label)
long <- rbind(data.frame(label = res$label, value = 1000 * res$blend, series = blend_label),
              data.frame(label = res$label, value = 1000 * res$pfpracm, series = "PfPR-ACM"))
long$series <- factor(long$series, levels = c(blend_label, "PfPR-ACM"))

themes <- list(
  light = list(surface = "#fcfcfb", ink = "#0b0b0b", ink2 = "#52514e", muted = "#898781",
               grid = "#e1e0d9", connector = "#c3c2b7", series = c("#2a78d6", "#eb6834")),
  dark = list(surface = "#1a1a19", ink = "#ffffff", ink2 = "#c3c2b7", muted = "#898781",
              grid = "#2c2c2a", connector = "#383835", series = c("#3987e5", "#d95926")))

top <- res[nrow(res), ]                      # direct labels on the top row
for (mode in names(themes)) {
  th <- themes[[mode]]
  p <- ggplot(long, aes(x = value, y = label)) +
    geom_segment(data = res, aes(x = 1000 * blend, xend = 1000 * pfpracm, y = label, yend = label),
                 inherit.aes = FALSE, colour = th$connector, linewidth = 0.7) +
    geom_point(aes(fill = series, shape = series), size = 2.9, stroke = 0.7, colour = th$surface) +
    annotate("text", x = 1000 * min(top$blend, top$pfpracm) - 0.8, y = nrow(res),
             label = ifelse(top$blend < top$pfpracm, "IHME/IGME × 1.6", "PfPR-ACM"), hjust = 1,
             size = 3.1, colour = th$ink2) +
    annotate("text", x = 1000 * max(top$blend, top$pfpracm) + 0.8, y = nrow(res),
             label = ifelse(top$blend < top$pfpracm, "PfPR-ACM", "IHME/IGME × 1.6"), hjust = 0,
             size = 3.1, colour = th$ink2) +
    scale_fill_manual(values = th$series, name = NULL) +
    scale_shape_manual(values = c(21, 23), name = NULL) +
    scale_x_continuous(expand = expansion(mult = c(0.02, 0.04)), limits = c(0, NA)) +
    coord_cartesian(clip = "off") +
    labs(title = "Probability of dying from malaria before age 5, 2023",
         subtitle = paste("Deaths per 1,000 live births. MAP PfPR2-10 in brackets; countries",
                          "ordered by the PfPR-ACM estimate."),
         x = "Deaths per 1,000 live births", y = NULL,
         caption = paste("IHME/IGME malaria probabilities are multiplied by 1.6 to include indirect",
                         "malaria deaths; PfPR-ACM\n(deaths that would not occur at PfPR 0) already",
                         "includes them. Both series use the IHME/IGME blended all-cause\nprobabilities",
                         "for survival between age bands. Lesotho, Mauritius and Seychelles have no",
                         "PfPR-ACM estimate.")) +
    theme_minimal(base_size = 10.5) +
    theme(plot.background = element_rect(fill = th$surface, colour = NA),
          panel.background = element_rect(fill = th$surface, colour = NA),
          panel.grid.major.y = element_blank(), panel.grid.minor = element_blank(),
          panel.grid.major.x = element_line(colour = th$grid, linewidth = 0.3),
          axis.text.y = element_text(colour = th$ink2, size = 8.5),
          axis.text.x = element_text(colour = th$muted), axis.title.x = element_text(colour = th$ink2),
          plot.title = element_text(colour = th$ink, face = "bold", size = 12.5),
          plot.subtitle = element_text(colour = th$ink2, size = 9.5),
          plot.caption = element_text(colour = th$muted, size = 8, hjust = 0),
          plot.title.position = "plot", plot.caption.position = "plot",
          legend.position = "top", legend.justification = "left", legend.location = "plot",
          legend.text = element_text(colour = th$ink2), legend.key = element_blank(),
          legend.margin = margin(0, 0, 0, 0), plot.margin = margin(12, 60, 10, 10))
  ggsave(file.path(out_dir, sprintf("u5_malaria_probability_%s.png", mode)), p,
         width = 7.5, height = 9.5, dpi = 200, bg = th$surface)
}
message("Wrote figures for ", nrow(res), " countries to figures/")
