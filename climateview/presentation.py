"""Shared colors and concise, human-friendly trend presentation."""

TEMPERATURE = {"primary": "#e76f51", "dark": "#d85a3a", "light": "#f3a385"}
RAINFALL = {"primary": "#4a90b8", "dark": "#2f6f95", "light": "#9bc6dc"}
AIR_QUALITY = {"primary": "#5b9279", "dark": "#3f6e58", "light": "#a9c9bb"}


def as_rgb(color: str) -> tuple[int, int, int]:
    """Convert a hexadecimal color to an RGB tuple for PyDeck."""
    return tuple(bytes.fromhex(color.removeprefix("#")))


def format_decadal_trend(
    subject: str,
    trend: float,
    start_year: int,
    unit: str,
    directions: tuple[str, str],
    *,
    unchanged_subject: str | None = None,
    qualifier: str = "",
) -> str:
    """Describe an annual slope as a rounded, plain-language decadal trend."""
    change = round(abs(trend) * 10, 1)
    if change == 0:
        subject = unchanged_subject or subject
        return f"{subject} hasn't changed much since {start_year}."

    direction = directions[0] if trend > 0 else directions[1]
    return (
        f"{subject} {direction}{qualifier}, changing about "
        f"{change:.1f}{unit} per decade since {start_year}."
    )


def render_location_summary(placeholder, summary: str) -> None:
    """Render the category-colored summary below a location title."""
    placeholder.markdown(
        f'<p class="location-context-summary">{summary}</p>',
        unsafe_allow_html=True,
    )
