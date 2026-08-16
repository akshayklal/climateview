# NOAA data download scripts

The NOAA download entry points are:

- `noaa-download-temperature-data.py`, which downloads daily maximum and minimum temperatures (`TMAX` and `TMIN`).
- `noaa-download-precipitation-data.py`, which downloads daily precipitation (`PRCP`).

Both entry points use the shared implementation in `noaa-download.py`.

## Command-line options

Both entry points accept the same options:

- `--station STATION`: download one configured NOAA station. The value must match a `noaa_station_id` in `data/stations.json`. If omitted, the script processes every configured station.
- `--overwrite`: download the data again even when the corresponding raw JSON file already exists.
- `-h` or `--help`: display command help.

The scripts require a NOAA API token in the `NOAA_TOKEN` environment variable.

## Processing steps

1. **Select the data type**

   The temperature entry point requests `TMAX` and `TMIN`. The precipitation entry point requests `PRCP`.

2. **Read command-line options and the API token**

   The shared downloader reads `--station` and `--overwrite`, then obtains the NOAA API token from `NOAA_TOKEN`. It stops with an error if the token is missing.

3. **Select configured stations**

   If `--station` is supplied, the script finds the matching entry in `data/stations.json`. Otherwise, it processes every station in that registry.

4. **Determine the year range**

   For each station, the download begins with its configured `noaa_start_year` and ends with the previous calendar year. The current year is excluded because it is incomplete.

5. **Check for an existing output file**

   The script creates one raw JSON file for each station, year, and measurement type. It skips an existing file unless `--overwrite` is supplied.

6. **Request data from NOAA**

   Each year is split into two API requests: January through June and July through December. This keeps each response within the API's 1,000-record limit. The requests use NOAA's GHCN-Daily (`GHCND`) dataset and standard units.

7. **Write raw JSON data**

   The two half-year responses are combined and written as an indented JSON array. If NOAA returns no records, the script reports that condition and does not create a file.

8. **Continue through all years and stations**

   The downloader pauses briefly between requests, then continues with the next measurement, year, or station.

## Output locations

Temperature files are written under:

```text
data/raw/noaa-temperature/<station-id>/
```

Their names follow this pattern:

```text
noaa-temperature-<TMAX-or-TMIN>-GHCND_<station-id>-<year>.json
```

Precipitation files are written under:

```text
data/raw/noaa-precipitation/<station-id>/
```

Their names follow this pattern:

```text
noaa-precipitation-PRCP-GHCND_<station-id>-<year>.json
```

## Examples

Download temperature data for one configured station:

```bash
NOAA_TOKEN="<your-token>" .venv/bin/python \
  scripts/noaa-download-temperature-data.py \
  --station USW00023234
```

Download precipitation data for every configured station, replacing existing files:

```bash
NOAA_TOKEN="<your-token>" .venv/bin/python \
  scripts/noaa-download-precipitation-data.py \
  --overwrite
```

A typical run reports the station and year range, followed by a message for every downloaded or skipped file:

```text
Using San Francisco / SFO, CA (USW00023234) from 1945 through 2025
Skipping existing file: data/raw/noaa-temperature/USW00023234/noaa-temperature-TMAX-GHCND_USW00023234-1945.json
Downloading TMIN for GHCND:USW00023234, year 1945
Wrote <record-count> records to data/raw/noaa-temperature/USW00023234/noaa-temperature-TMIN-GHCND_USW00023234-1945.json
```

The exact station name, years, record counts, and skip/download messages depend on the station registry, existing files, and NOAA API results.
