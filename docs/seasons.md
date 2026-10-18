# Location-specific seasons

Each entry in `data/stations.json` can set `season_profile`:

- `northern`: Winter (Dec–Feb), Spring (Mar–May), Summer (Jun–Aug), Fall (Sep–Nov).
- `southern`: Winter (Jun–Aug), Spring (Sep–Nov), Summer (Dec–Feb), Fall (Mar–May).
- `none`, or an omitted profile: no season selector or seasonal summary findings.

All existing U.S. stations explicitly use `northern` to preserve their current
behavior. Do not infer seasons solely from latitude for tropical or polar sites.
The Month aggregation remains available when the seasonal selector is hidden;
this change does not add a separate month-of-year filter.

For a locally verified seasonal calendar, `season_months` overrides the profile:

```json
"season_months": {
  "Wet": [11, 12, 1, 2, 3],
  "Dry": [4, 5, 6, 7, 8, 9, 10]
}
```

This is a configuration example, not a definition for any particular location.
Months must be consecutive, listed in season order, and not overlap. Labels
appear in the selector; summaries use their lowercase form. Empty definitions
disable seasonal analysis. Uncovered months remain part of annual analysis.

Charts assign a cross-year season to its ending year. Period-comparison
summaries retain their existing calendar-year grouping to preserve published
U.S. results. Both use the same station-specific month definitions. The minimum
coverage remains 60 days for three-month seasons, scaled to 20 days per month
for custom seasons.

Rebuild location summaries and featured patterns after changing a station's
season configuration. Navigation resets unavailable season selections to All
year. The Render sitemap and NOAA data files do not need changes for this feature.
