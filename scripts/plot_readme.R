# README figures: probability of dying from malaria before age 5, 2023, from the cause-assigned
# estimates with the x 1.6 indirect-death adjustment (blend_q_malaria_adj) and from PfPR-ACM.
#   countries        IHME/IGME blend x 1.6 vs PfPR-ACM
#   Nigerian states  IHME x 1.6 vs PfPR-ACM (states use IHME only)
# Each row also marks the combined estimate (the average of the two) with a tick; the bracket in
# each label is MAP PfPR2-10.
#
# Cumulative probability before 5 from the five band probabilities (competing risks):
#     q_malaria_u5 = sum_b S_b x q_malaria_b,   S_b = prod_{j<b} (1 - q_all_j)
# using blend_q_all for survival in both series. PfPR-ACM band q = pfpracm_share x blend_q_all.
#
# Outputs (figures/): u5_malaria_probability_{countries,nigeria_states}_{light,dark}.png and
# u5_malaria_probability_blend_vs_pfpracm.csv (also carrying the unadjusted blend and the
# combined estimate).
# Usage:  Rscript scripts/plot_readme.R
suppressPackageStartupMessages(library(ggplot2))

args <- commandArgs(trailingOnly = FALSE)
script <- gsub("~+~", " ", sub("--file=", "", args[grep("--file=", args)]), fixed = TRUE)
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
out_dir <- file.path(root, "figures")
dir.create(out_dir, showWarnings = FALSE)

bands <- c("0_27d", "1_5m", "6_11m", "12_23m", "2_4y")
full <- read.csv(file.path(root, "output", "malaria_burden_inputs_2023.csv"), encoding = "UTF-8")
q_all <- as.matrix(full[paste0("blend_q_all_", bands)])
survival <- cbind(1, t(apply(1 - q_all, 1, cumprod)))[, seq_along(bands)]
cumulative <- function(prefix) rowSums(survival * as.matrix(full[paste0(prefix, bands)]))
res <- data.frame(location_level = full$location_level, iso3 = full$iso3,
                  name = ifelse(full$location_level == "country", full$country_name, full$state_name),
                  pfpr_2_10 = full$map_pfpr_2_10, all_cause_q_u5 = 1 - apply(1 - q_all, 1, prod),
                  blend_direct = cumulative("blend_q_malaria_"),
                  blend = cumulative("blend_q_malaria_adj_"),            # x 1.6 for indirect deaths
                  pfpracm = cumulative("pfpracm_q_malaria_"),
                  combined = cumulative("combined_q_malaria_"))
stopifnot(!anyNA(res[c("pfpr_2_10", "blend", "pfpracm")]))
csv <- data.frame(res[c("location_level", "iso3", "name", "pfpr_2_10", "all_cause_q_u5")],
                  blend_direct_per_1000 = 1000 * res$blend_direct,
                  blend_indirect_adjusted_per_1000 = 1000 * res$blend,
                  pfpracm_per_1000 = 1000 * res$pfpracm,
                  combined_per_1000 = 1000 * res$combined,
                  ratio_pfpracm_to_adjusted_blend = res$pfpracm / res$blend)
write.csv(csv[order(csv$location_level, -csv$pfpracm_per_1000), ],
          file.path(out_dir, "u5_malaria_probability_blend_vs_pfpracm.csv"), row.names = FALSE)

themes <- list(
  light = list(surface = "#fcfcfb", ink = "#0b0b0b", ink2 = "#52514e", muted = "#898781",
               grid = "#e1e0d9", connector = "#c3c2b7", series = c("#2a78d6", "#eb6834")),
  dark = list(surface = "#1a1a19", ink = "#ffffff", ink2 = "#c3c2b7", muted = "#898781",
              grid = "#2c2c2a", connector = "#383835", series = c("#3987e5", "#d95926")))

short_names <- c("Democratic Republic of the Congo" = "DR Congo",
                 "United Republic of Tanzania" = "Tanzania")      # figure labels only
average_label <- "Average of the two"

dumbbell <- function(r, stub, title, unit, legend_label, short_label, caption) {
  r <- r[order(r$pfpracm), ]
  name <- ifelse(r$name %in% names(short_names), short_names[r$name], r$name)
  labels <- sprintf("%s (PfPR %.0f%%)", name, 100 * r$pfpr_2_10)
  r$label <- factor(labels, levels = labels)
  series <- c(legend_label, "PfPR-ACM", average_label)
  long <- rbind(data.frame(label = r$label, value = 1000 * r$blend, series = series[1]),
                data.frame(label = r$label, value = 1000 * r$pfpracm, series = series[2]),
                data.frame(label = r$label, value = 1000 * r$combined, series = series[3]))
  long$series <- factor(long$series, levels = series)  # average drawn last, on top of the dots
  top <- r[nrow(r), ]                        # direct labels on the top row, outward from the pair
  left_is_blend <- top$blend < top$pfpracm
  for (mode in names(themes)) {
    th <- themes[[mode]]
    p <- ggplot(long, aes(x = value, y = label)) +
      geom_segment(data = r, aes(x = 1000 * blend, xend = 1000 * pfpracm, y = label, yend = label),
                   inherit.aes = FALSE, colour = th$connector, linewidth = 0.7) +
      geom_point(aes(fill = series, shape = series, colour = series, size = series), stroke = 0.7) +
      annotate("text", x = 1000 * min(top$blend, top$pfpracm) - 0.8, y = nrow(r),
               label = if (left_is_blend) short_label else "PfPR-ACM", hjust = 1, size = 3.1,
               colour = th$ink2) +
      annotate("text", x = 1000 * max(top$blend, top$pfpracm) + 0.8, y = nrow(r),
               label = if (left_is_blend) "PfPR-ACM" else short_label, hjust = 0, size = 3.1,
               colour = th$ink2) +
      annotate("text", x = 1000 * top$combined, y = nrow(r) + 0.55, label = "Average",
               vjust = 0, size = 2.8, colour = th$ink2) +
      scale_fill_manual(values = c(th$series, th$ink), name = NULL) +
      scale_colour_manual(values = c(th$surface, th$surface, th$ink), name = NULL) +
      scale_shape_manual(values = c(21, 23, 124), name = NULL) +
      scale_size_manual(values = c(2.9, 2.9, 3.2), name = NULL) +
      scale_x_continuous(expand = expansion(mult = c(0.02, 0.04)), limits = c(0, NA),
                         breaks = scales::breaks_width(10)) +
      coord_cartesian(clip = "off") +
      labs(title = title,
           subtitle = sprintf(paste("Deaths per 1,000 live births. The tick on each line is the average",
                                    "of the two; %s ordered by the PfPR-ACM estimate."), unit),
           x = "Deaths per 1,000 live births", y = NULL, caption = caption) +
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
    ggsave(file.path(out_dir, sprintf("u5_malaria_probability_%s_%s.png", stub, mode)), p,
           width = 7.5, height = 2 + nrow(r) / 6, dpi = 200, bg = th$surface)
  }
  message("Wrote ", stub, " figures (", nrow(r), " rows)")
}

dumbbell(res[res$location_level == "country", ], "countries",
         "Probability of dying from malaria before age 5, sub-Saharan Africa, 2023", "countries",
         "IHME/IGME blend × 1.6", "IHME/IGME × 1.6",
         paste("IHME/IGME malaria probabilities are multiplied by 1.6 to include indirect malaria",
               "deaths; PfPR-ACM\n(deaths that would not occur at PfPR 0) already includes them.",
               "Both series use the IHME/IGME blended\nall-cause probabilities for survival between",
               "age bands. PfPR is MAP's 2023 population-weighted PfPR2-10."))
dumbbell(res[res$location_level == "nigeria_state", ], "nigeria_states",
         "Probability of dying from malaria before age 5, Nigerian states, 2023", "states",
         "IHME × 1.6", "IHME × 1.6",
         paste("IHME malaria probabilities are multiplied by 1.6 to include indirect malaria deaths;",
               "PfPR-ACM (deaths\nthat would not occur at PfPR 0) already includes them. Both",
               "series use IHME all-cause probabilities for\nsurvival between age bands. PfPR is MAP's",
               "2023 state (admin-1) estimate."))
