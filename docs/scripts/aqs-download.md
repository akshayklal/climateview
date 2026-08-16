# EPA AQS data downloader

`aqs-download.py` downloads raw daily pollutant summaries and monitor metadata from the EPA Air Quality System (AQS) API. It downloads every POC at the configured physical AQS site so `aqs-build-processed-data.py` can select and combine monitors later.

## Command-line options

- `--station STATION`: download one configured location by its NOAA station ID, such as `USC00111577`. If omitted, the script processes every entry in `data/stations.json`.
- `--pollutant CODE`: five-digit AQS pollutant parameter code. Required. Common examples are `44201` for ozone and `88101` for PM2.5.
- `--overwrite`: replace existing raw yearly data and monitor-metadata files. Without this option, existing files are reused or skipped.
- `--email EMAIL`: EPA AQS account email address. Required.
- `--key KEY`: EPA AQS API key associated with the email address. Required.
- `-h` or `--help`: display command help.

## Processing steps

1. **Read the pollutant and credentials**

   Reads the AQS parameter code, account email, API key, station selection, and overwrite setting. Known parameter codes are converted to project pollutant names such as `ozone` or `pm25`.

2. **Select configured locations**

   If `--station` is supplied, the script matches it against `noaa_station_id` values in `data/stations.json`. Otherwise, it processes every configured location.

3. **Read the configured AQS site**

   Gets the location's `aqs_site_id` from the registry and splits it into the EPA state, county, and site components. Locations without an AQS site ID are skipped.

4. **Discover every monitor and POC**

   Calls the AQS `monitors/bySite` endpoint for the selected pollutant and physical site. The metadata search starts on January 1, 1950 and ends on the current date. Duplicate monitor records are removed and the remaining monitors are sorted by opening date and POC.

5. **Save monitor metadata**

   Writes the monitor metadata as JSON, including POC opening and closing dates. An existing metadata file is reused unless `--overwrite` is supplied, although the API is still queried to discover the current monitor set and year range.

6. **Determine the download period**

   Uses the earliest monitor opening year as the first year and the previous calendar year as the last year. The current year is excluded because it is incomplete.

7. **Download yearly daily summaries**

   Calls the AQS `dailyData/bySite` endpoint once per year. The request does not filter by POC, so all POCs and all returned regulatory-standard rows are retained in the raw data.

8. **Write raw JSON data**

   Sorts records by local date, POC, sample duration, and pollutant standard, then writes one JSON file per site, pollutant, and year. Existing yearly files are skipped unless `--overwrite` is supplied. Years with no data do not produce a file.

9. **Handle temporary API failures**

   Retries network errors, rate-limit responses, and server errors up to three times with increasing delays. The script also detects errors reported inside otherwise successful AQS JSON responses.

## Output locations

All files are written beneath the configured physical AQS site ID:

```text
data/raw/aqs/<aqs-site-id>/
```

Monitor metadata follows this pattern:

```text
aqs-monitors-<pollutant>-<aqs-site-id>.json
```

Yearly daily summaries follow this pattern:

```text
aqs-<pollutant>-<aqs-site-id>-<year>.json
```

For example, ozone data for site `06-075-0005` may produce:

```text
data/raw/aqs/06-075-0005/aqs-monitors-ozone-06-075-0005.json
data/raw/aqs/06-075-0005/aqs-ozone-06-075-0005-2025.json
```

## Examples

Download ozone data for the configured location whose NOAA station ID is `USW00023234`:

```bash
.venv/bin/python scripts/aqs-download.py \
  --email "<aqs-account-email>" \
  --key "<aqs-api-key>" \
  --station USW00023234 \
  --pollutant 44201
```

Download PM2.5 data for every configured location and replace existing files:

```bash
.venv/bin/python scripts/aqs-download.py \
  --email "<aqs-account-email>" \
  --key "<aqs-api-key>" \
  --pollutant 88101 \
  --overwrite
```

A run reports monitor discovery, selected POCs and year range, and the status of each output file:

```text
Discovering Ozone for San Francisco / SFO, CA (06-075-0005)
Wrote <count> monitor records to data/raw/aqs/06-075-0005/aqs-monitors-ozone-06-075-0005.json
Using San Francisco / SFO, CA for Ozone with POCs [<pocs>], start year <year>, end year 2025
Skipping existing file: data/raw/aqs/06-075-0005/aqs-ozone-06-075-0005-<year>.json
```

Exact monitors, years, record counts, and messages depend on `data/stations.json`, existing files, and current EPA AQS results.
