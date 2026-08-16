"""Shared AQS constants and normalization helpers for data scripts."""

from datetime import date, datetime

from climateview.aqs_config import AQS_POLLUTANTS


AQS_API_BASE_URL = "https://aqs.epa.gov/data/api"
AQS_PARAMETERS = {
    "carbon_monoxide": ("42101", "Carbon monoxide"),
    "lead": ("14129", "Lead"),
    "nitrogen_dioxide": ("42602", "Nitrogen dioxide"),
    "pm10": ("81102", "PM10"),
    "sulfur_dioxide": ("42401", "Sulfur dioxide"),
    **{
        name: (config["parameter_code"], config["label"])
        for name, config in AQS_POLLUTANTS.items()
    },
}
AQS_PARAMETER_KEYS_BY_CODE = {
    code: name for name, (code, _display_name) in AQS_PARAMETERS.items()
}


def parse_aqs_date(value: object) -> date | None:
    """Parse either date representation returned by AQS."""
    if value in (None, ""):
        return None

    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(str(value), date_format).date()
        except ValueError:
            continue
    return None


def poc_sort_value(value: object) -> tuple[int, object]:
    """Return a stable ordering key for numeric and textual POC values."""
    text = str(value or "")
    return (0, int(text)) if text.isdigit() else (1, text)
