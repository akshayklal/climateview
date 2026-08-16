# NOAA station finder

`noaa-find-stations.py` finds NOAA GHCN-Daily stations with current, long-running temperature and precipitation records. It combines station metadata with measurement availability and prints the qualifying stations to the terminal.

## Command-line options

- `--state STATE`: filter by a two-letter U.S. state code, such as `CA`.
- `--country COUNTRY`: filter by the two-character GHCN country prefix, such as `US`, `CA`, `MX`, or `IN`.
- `--require-elements ELEMENTS`: require a comma-separated set of measurements. The default is `TMAX,TMIN,PRCP`.
- `--limit NUMBER`: set the maximum number of stations displayed. The default is `20`; use `0` to display every match.
- `--refresh`: download fresh NOAA metadata instead of reusing the local files.
- `-h` or `--help`: display command help.

## Processing steps

1. **Parse filters**

   Reads options such as state, country, required measurements, result limit, and whether to refresh NOAA metadata.

2. **Obtain NOAA metadata**

   Downloads or reuses two files:

   - `ghcnd-stations.txt`: one row per station, containing its ID, name, coordinates, elevation, and location information.
   - `ghcnd-inventory.txt`: one row per station and measurement type, containing the measurement code—such as `TMAX`, `TMIN`, or `PRCP`—and the first and last years available.

3. **Load station details**

   Parses station IDs, names, and state codes.

4. **Load measurement coverage**

   Parses the available measurements and year ranges for each station.

5. **Apply location filters**

   Processes each station and skips it immediately if it does not match the requested state or country.

6. **Look up and filter measurement coverage**

   Looks up the remaining station's measurement coverage in the inventory using its station ID. The station is kept only if it contains every required measurement and each required measurement has data through at least the previous calendar year.

   The script also finds the years during which all required measurements overlap. For example:

   ```text
   TMAX: 1940–2025
   TMIN: 1950–2025
   PRCP: 1930–2025
   ```

   The common period is `1950–2025`, because 1950 is the latest starting year among the three. If any measurement ended before 2025, the station would be excluded when running in 2026.

7. **Rank results**

   Sorts qualifying stations by the earliest common starting year, then by station ID.

8. **Print results**

   Displays the matching stations and measurement ranges in the terminal.

## Output locations

The filtered station results are printed to the terminal and are not saved to a file.

The downloaded NOAA source metadata is cached under:

```text
data/meta/ghcnd-stations.txt
data/meta/ghcnd-inventory.txt
```

`ghcnd-stations.txt` describes the stations, while `ghcnd-inventory.txt` describes the measurements and available year ranges at each station.

## Examples

### California

To find up to 20 California stations that have `TMAX`, `TMIN`, and `PRCP` records continuing through at least the previous calendar year, run:

```bash
.venv/bin/python scripts/noaa-find-stations.py --state CA
```

Output from a run on August 15, 2026:

```text
Using existing metadata file: data/meta/ghcnd-inventory.txt
Using existing metadata file: data/meta/ghcnd-stations.txt
Loading NOAA metadata...
Stations in station metadata: 132,500
Unique stations in inventory: 132,437

Station                        Station ID   ST  TMAX        TMIN        PRCP        Common      Years
-------------------------------------------------------------------------------------------------------
FT BIDWELL                     USC00043157  CA  1870-2026   1870-2026   1867-2026   1870-2026   157
SACRAMENTO 5 ESE              USW00023271  CA  1877-2025   1877-2025   1877-2025   1877-2025   149
DAVIS 2 WSW EXP FARM          USC00042294  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
JULIAN CDF                     USC00044412  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
NAPA STATE HOSPITAL           USC00046074  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
NEVADA CITY                    USC00046136  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
PASADENA                       USC00046719  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
PETALUMA AP                    USC00046826  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
SAN JOSE                       USC00047821  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
SANTA BARBARA                  USC00047902  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
SONOMA                         USC00048351  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
YREKA                          USC00049866  CA  1893-2026   1893-2026   1893-2026   1893-2026   134
CEDARVILLE                     USC00041614  CA  1894-2026   1894-2026   1894-2026   1894-2026   133
INDIO FIRE STN                USC00044259  CA  1894-2026   1894-2026   1894-2026   1894-2026   133
PASO ROBLES                    USC00046730  CA  1894-2026   1894-2026   1894-2026   1894-2026   133
SAN RAFAEL-CIVIC CTR          USC00047880  CA  1894-2026   1894-2026   1894-2026   1894-2026   133
TURLOCK #2                     USC00049073  CA  1894-2026   1894-2026   1893-2026   1894-2026   133
BISHOP AP                      USW00023157  CA  1895-2026   1895-2026   1895-2026   1895-2026   132
BODIE CALIFORNIA ST HISTORIC P USC00040943  CA  1895-2026   1895-2026   1895-2026   1895-2026   132
FT BRAGG 5 N                  USC00043161  CA  1895-2026   1895-2026   1895-2026   1895-2026   132

Matching stations: 317
Displayed stations: 20
```
