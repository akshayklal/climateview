# EPA AQS station finder

`aqs-find-stations.py` finds EPA Air Quality System (AQS) monitoring sites near locations configured in `data/stations.json`. It reports which pollutants each site monitors and can show the monitor history for ozone and PM2.5.

## Command-line options

- `--email EMAIL`: email address registered with the EPA AQS API. Required.
- `--key KEY`: AQS API key associated with the email address. Required.
- `--station STATION`: search one configured ClimateView location by its registry key, such as `san_francisco_sfo`. If omitted, the script searches every configured location.
- `--show-pocs-for POLLUTANTS`: comma-separated pollutants that a matching site must monitor and whose Parameter Occurrence Codes (POCs) should be displayed. Choices are `ozone` and `pm25`; the default is `ozone,pm25`.
- `--radius-km NUMBER`: search radius around each ClimateView location. The default is 40 km and the value must be greater than zero.
- `--max-results NUMBER`: maximum ranked AQS sites displayed per location. The default is 8 and the value must be greater than zero.
- `-h` or `--help`: display command help.

## Processing steps

1. **Load configured locations**

   Loads the ClimateView station registry from `data/stations.json`. Each location supplies a name, latitude, and longitude.

2. **Select locations**

   If `--station` is supplied, the script selects that registry entry. Otherwise, it processes every configured location.

3. **Build an AQS search area**

   Converts the requested radius into an approximate latitude/longitude bounding box centered on the location.

4. **Request monitor metadata from EPA**

   Calls the AQS `monitors/byBox` endpoint for the supported pollutant parameter codes. The monitor-history search begins in 1957 and ends on the current date. Parameter codes are split across requests because the API accepts at most five codes per request.

5. **Calculate exact distances**

   Calculates the great-circle distance from the ClimateView coordinates to every returned monitor. Records outside the requested radius are removed because the API's rectangular bounding box can include more distant sites.

6. **Group monitors into physical sites**

   Groups pollutant monitors by their AQS state, county, and site numbers, producing IDs such as `06-075-0005`. A physical site can contain multiple pollutants and multiple POCs for the same pollutant.

7. **Filter matching sites**

   Keeps only sites that monitor every pollutant requested by `--show-pocs-for`. With the default `ozone,pm25`, a site must have both ozone and PM2.5 monitors.

8. **Rank sites**

   Ranks sites by the oldest common monitor coverage for the requested pollutants, then by distance from the ClimateView location.

9. **Print results**

   Prints the AQS site ID, site name, distance, available pollutant parameters, and POC operating periods for the requested pollutants.

## Output locations

Results are printed to the terminal and are not written to a file. A selected site's `aqs_site_id`, name, and distance can then be added to its entry in `data/stations.json`.

## Examples

Find up to eight sites within 40 km of the San Francisco location that monitor both ozone and PM2.5:

```bash
.venv/bin/python scripts/aqs-find-stations.py \
  --email "<aqs-account-email>" \
  --key "<aqs-api-key>" \
  --station san_francisco_sfo
```

Find up to five sites within 60 km that monitor ozone, without requiring PM2.5:

```bash
.venv/bin/python scripts/aqs-find-stations.py \
  --email "<aqs-account-email>" \
  --key "<aqs-api-key>" \
  --station san_francisco_sfo \
  --show-pocs-for ozone \
  --radius-km 60 \
  --max-results 5
```

A run prints records in this general form:

```text
San Francisco / SFO, CA (san_francisco_sfo)
ClimateView coordinates: 37.6190, -122.3750
Search radius: 40.0 km; monitor history searched from 1957

Found <count> matching AQS site(s). Showing <count>:

  1. {'aqs_site_id': '<SS-CCC-NNNN>', 'aqs_site_name': '<site-name>', 'aqs_distance_km': <distance>} | Parameters: <pollutants>
     Ozone POCs:
       POC <number>: <open-date> to <close-date-or-present>
```

Exact sites and monitor periods depend on current EPA AQS metadata.
