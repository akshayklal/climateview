# EPA AQS processed-data builder

`aqs-build-processed-data.py` converts raw EPA AQS monitor metadata and daily summaries into one continuous daily CSV for each physical site and pollutant. It resolves changing or overlapping POCs and removes duplicate daily regulatory-standard rows.

## Command-line options

- `--station STATION`: process one configured location by its NOAA station ID, such as `USC00111577`. If omitted, the script processes every entry in `data/stations.json`.
- `--pollutant CODE`: select the AQS pollutant parameter code. Required. Supported values are `44201` for ozone and `88101` for PM2.5.
- `-h` or `--help`: display command help.

## Processing steps

1. **Select the pollutant and stations**

   Converts the requested parameter code to the project pollutant name. If `--station` is supplied, it is matched against `noaa_station_id` values in `data/stations.json`; otherwise, every configured station is processed.

2. **Read the configured AQS site**

   Gets each location's physical `aqs_site_id` from `data/stations.json`. Locations without an AQS site ID are skipped.

3. **Load monitor metadata**

   Loads the pollutant's monitor metadata created by `aqs-download.py`, including each POC's opening and closing dates. A missing or empty metadata file causes that station and pollutant to be skipped.

4. **Load all raw yearly rows**

   Finds every raw JSON file for the physical site and pollutant, then combines their records. Rows for other AQS parameter codes or rows without a valid local date are discarded.

5. **Group rows by date**

   Groups the remaining daily-summary rows by `date_local` while initially retaining every POC, sample duration, and regulatory standard.

6. **Rank active POCs for each date**

   Uses monitor opening and closing dates to determine which POCs were active on that date. Active POCs are ranked oldest first, so the earliest monitor remains preferred until it closes.

7. **Select a POC with data**

   Uses rows from the oldest active POC when available. If that POC has no row for the date, the processor falls back to the next-oldest active POC that does have data. Dates with no active monitor or no data from any active POC are skipped.

8. **Choose one daily regulatory row**

   A selected POC can still have multiple rows for different sample durations or regulatory standards. The processor chooses one using pollutant-specific sample-duration and standard preferences, followed by validity, presence of a mean, observation completeness, observation count, and method code.

9. **Reduce the output columns**

   Every row keeps `date` and `aqi`. Ozone uses `first_max_value` as `daily_max`, while PM2.5 uses `arithmetic_mean` as `value`.

10. **Write the processed CSV**

   Writes one chronologically ordered CSV per AQS site and pollutant, replacing any existing processed file. It also reports counts for fallback POC use and skipped dates when applicable.

## Output locations

Processed files are written under:

```text
data/processed/aqs/
```

Ozone output follows this pattern:

```text
aqs-ozone-<aqs-site-id>.csv
date,aqi,daily_max
```

PM2.5 output follows this pattern:

```text
aqs-pm25-<aqs-site-id>.csv
date,aqi,value
```

For example:

```text
data/processed/aqs/aqs-ozone-06-075-0005.csv
data/processed/aqs/aqs-pm25-06-075-0005.csv
```

## Examples

Build an ozone time series for one configured location:

```bash
.venv/bin/python scripts/aqs-build-processed-data.py \
  --station USW00023234 \
  --pollutant 44201
```

Build PM2.5 time series for every configured location:

```bash
.venv/bin/python scripts/aqs-build-processed-data.py \
  --pollutant 88101
```

A run reports the output row count and any exceptional date handling:

```text
Wrote <row-count> daily Ozone records for San Francisco / SFO, CA to data/processed/aqs/aqs-ozone-06-075-0005.csv
  Dates skipped with no active monitor: <count>
  Dates using fallback active POC: <count>
  Dates skipped because no active POC had a row: <count>
```

The three date-count lines are printed only when their counts are nonzero. Exact counts depend on the downloaded AQS monitor metadata and daily summaries.
