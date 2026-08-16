"""Shared definitions for the AQS pollutants supported by ClimateView."""


AQS_POLLUTANTS = {
    "pm25": {
        "label": "Fine-particle pollution",
        "parameter_code": "88101",
        "value_column": "value",
        "unit": "µg/m³",
        "display_scale": 1.0,
        "axis_titles": {
            "Day": "Daily fine-particle pollution (µg/m³)",
            "Month": "Monthly average fine-particle pollution (µg/m³)",
            "Year": "Annual average fine-particle pollution (µg/m³)",
        },
        "preferred_sample_durations": (
            "24-HR BLK AVG",
            "24 HOUR",
            "24-HOUR",
            "1 HOUR",
        ),
        "preferred_standard_terms": (
            "24-hour 2024",
            "24-hour 2012",
            "24-hour 2006",
            "24-hour 1997",
        ),
    },
    "ozone": {
        "label": "Ground-level ozone pollution",
        "parameter_code": "44201",
        "value_column": "daily_max",
        "unit": "ppb",
        "display_scale": 1000.0,
        "axis_titles": {
            "Day": "Daily maximum ground-level ozone pollution (ppb)",
            "Month": "Monthly average daily max ground-level ozone pollution (ppb)",
            "Year": "Annual average daily max ground-level ozone pollution (ppb)",
        },
        "preferred_sample_durations": (
            "8-HR RUN AVG BEGIN HOUR",
            "8 HOUR",
            "1 HOUR",
        ),
        "preferred_standard_terms": (
            "8-hour 2015",
            "8-Hour 2008",
            "8-Hour 1997",
            "1-hour 1979",
        ),
    },
}

AQS_POLLUTANTS_BY_CODE = {
    config["parameter_code"]: name
    for name, config in AQS_POLLUTANTS.items()
}
