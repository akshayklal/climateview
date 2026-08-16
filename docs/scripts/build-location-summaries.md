# Location summary builder

`build-location-summaries.py` creates concise, verified text for the location markers on the main map. It compares the earliest and latest non-overlapping 10-year periods in the processed NOAA and EPA AQS data.

## Command-line options

- `--station STATION`: build one location by its key in `data/stations.json`. If omitted, the script builds every configured location.
- `--output PATH`: write the JSON artifact to a different path. The default is `data/processed/location-summaries.json`.
- `--patterns-output PATH`: write the ranked explorable-pattern pool to a different path when building all locations. The default is `data/processed/patterns-worth-exploring.json`.
- `-h` or `--help`: display command help.

## Processing steps

1. **Load configured locations**

   Reads all locations and their NOAA and AQS identifiers from `data/stations.json`.

2. **Compare temperature periods**

   Calculates annual mean temperature from paired daily maximum and minimum values. Years require at least 300 paired observations. The first and latest consecutive 10-year periods are compared.

3. **Find the strongest seasonal temperature change**

   Compares daytime highs and nighttime lows for winter, spring, summer, and fall. The strongest change in the same direction as the overall temperature change is used in wording such as “led by warmer summer nights.”

4. **Compare precipitation periods**

   Calculates annual precipitation totals for years with at least 300 observations. The percentage difference is mentioned only when the full annual record has a statistically significant linear trend in the same direction.

5. **Compare air-quality periods**

   Calculates annual PM2.5 and ozone averages for years with at least 90 daily observations. A pollutant requires at least 20 qualifying years so its first and latest sets of 10 annual averages do not overlap; gaps are allowed because AQS sampling can be intermittent. Its change is mentioned only when the full annual record has a statistically significant trend in the same direction.

6. **Generate concise text**

   Uses deterministic sentence templates to produce one compact map-tooltip sentence. Metrics without a statistically supported change are omitted. No AI request is made.

7. **Write the summary artifact**

   Stores the tooltip line for each location in the application JSON. Supporting calculations remain in memory while the related pattern artifact is built.

8. **Build patterns worth exploring**

   On a full run, retains and ranks every supported temperature, seasonal, rainfall, and air-quality finding within its category. A diverse top 15 is marked for the landing page; no AI request is made.

## Output location

The default output is:

```text
data/processed/location-summaries.json
data/processed/patterns-worth-exploring.json
```

Each location contains only its generated `summary`; detailed intermediate calculations are not written because the application does not read them.

The patterns file contains every eligible finding with a stable ID, category, category rank, featured status, location key, destination tab, title, and concise description. Air-quality findings also identify the pollutant to select; seasonal findings identify the season. The application randomly chooses three from the entries marked `featured` once per page session.

## Examples

Build summaries for every location:

```bash
.venv/bin/python scripts/build-location-summaries.py
```

Build only Phoenix and write it to a temporary review file:

```bash
.venv/bin/python scripts/build-location-summaries.py \
  --station phoenix_sky_harbor \
  --output /tmp/phoenix-summary.json
```

A full run reports each generated summary:

```text
Wrote 29 location summaries to .../data/processed/location-summaries.json
phoenix_sky_harbor: Average temperatures are now ...
```

Run this script after rebuilding the processed NOAA or AQS CSV files so the map summaries reflect the latest data.
