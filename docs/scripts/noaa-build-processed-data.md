# NOAA processed-data builders

The NOAA processing entry points are:

- `noaa-build-processed-temperature-data.py`, which builds daily temperature CSV files from raw `TMAX` and `TMIN` JSON files.
- `noaa-build-processed-precipitation-data.py`, which builds daily precipitation CSV files from raw `PRCP` JSON files.

Both entry points use the shared implementation in `noaa-build-processed-data.py`.

## Command-line options

Both entry points accept the same options:

- `--station STATION`: process one configured location by its NOAA station ID. If omitted, the script processes every entry in `data/stations.json`.
- `-h` or `--help`: display command help.

## Processing steps

1. **Select the metric**

   The temperature entry point processes `TMAX` and `TMIN`. The precipitation entry point processes `PRCP`.

2. **Select configured stations**

   If `--station` is supplied, the shared processor matches it against `noaa_station_id` values in `data/stations.json`. Otherwise, it processes every configured station.

3. **Determine the processing period**

   Processing starts one year after the configured `noaa_start_year`, which avoids a potentially incomplete first calendar year. It ends with the previous calendar year, excluding the incomplete current year.

4. **Load yearly raw JSON files**

   For every year, the processor loads the files created by the NOAA download scripts. Missing files are reported and represented as empty data for that measurement.

5. **Normalize individual measurements**

   Converts NOAA date strings into dates, converts measurement values to numbers, keeps the date and relevant value column, removes duplicate dates, and sorts the rows chronologically.

6. **Combine measurements by date**

   Temperature processing outer-joins `TMAX` and `TMIN` on the date, so a day can remain in the result when only one measurement is available. Precipitation processing has only the `PRCP` series.

7. **Combine all years**

   Adds the clean NOAA station ID to every row, concatenates the yearly tables, sorts them by date, and removes duplicate station/date rows.

8. **Write the processed CSV**

   Writes one CSV per station and metric. Existing processed CSV files are replaced.

## Output locations

Temperature CSV files are written under:

```text
data/processed/noaa-temperature/
```

Their names and columns follow these patterns:

```text
<station-id>_daily_temperature.csv
station_id,date,tmax_f,tmin_f
```

Precipitation CSV files are written under:

```text
data/processed/noaa-precipitation/
```

Their names and columns follow these patterns:

```text
<station-id>_daily_precipitation.csv
station_id,date,prcp_in
```

## Examples

Build temperature data for one configured station:

```bash
.venv/bin/python scripts/noaa-build-processed-temperature-data.py \
  --station USW00023234
```

Build precipitation data for every configured station:

```bash
.venv/bin/python scripts/noaa-build-processed-precipitation-data.py
```

A run reports the station, processing period, missing raw files, and resulting CSV:

```text
Processing San Francisco / SFO, CA (USW00023234) from 1946 through 2025
Missing raw file, skipping: data/raw/noaa-temperature/USW00023234/noaa-temperature-TMAX-GHCND_USW00023234-<year>.json
Wrote <row-count> rows to data/processed/noaa-temperature/USW00023234_daily_temperature.csv
```

Exact years, missing-file messages, and row counts depend on `data/stations.json` and the downloaded raw data.
